#!/usr/bin/env python3
import os
import sys
import json
import time
import hashlib
import base64
import requests
from urllib.parse import urlparse
from io import BytesIO
from PIL import Image

# ---------------- CONFIG ----------------

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
PROCESSED_BRANCH = os.environ.get("PROCESSED_BRANCH", "processed-images")

IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

SITE_URL_BASE = os.environ.get("SITE_URL_BASE", "").rstrip("/")
GRAPH_BASE = "https://graph.facebook.com/v19.0"

HEADERS_GH = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# ---------------- HELPERS ----------------

def log(msg):
    print(msg, flush=True)

def download_image(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def process_image(img_bytes):
    im = Image.open(BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side))
    im = im.resize((1080, 1080))
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue()

def hash_name(url):
    h = hashlib.sha1(url.encode()).hexdigest()[:10]
    ts = int(time.time())  # avoid IG caching
    name = os.path.basename(urlparse(url).path)
    return f"{h}-{ts}-{name}".replace(" ", "-")

def gh_get_sha(path):
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{path}",
        headers=HEADERS_GH,
        params={"ref": PROCESSED_BRANCH},
    )
    if r.status_code == 200:
        return r.json().get("sha")
    if r.status_code == 404:
        return None
    r.raise_for_status()

def gh_put_file(path, content_bytes, message):
    sha = gh_get_sha(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch": PROCESSED_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{path}",
        headers=HEADERS_GH,
        json=payload,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)

    return r.json()["content"]["download_url"]

# ---------------- INSTAGRAM ----------------

def create_child_container(image_url):
    data = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": IG_ACCESS_TOKEN,
    }
    for _ in range(5):
        r = requests.post(f"{GRAPH_BASE}/{IG_USER_ID}/media", data=data)
        if r.status_code == 200:
            return r.json()["id"]
        time.sleep(10)
    raise RuntimeError(f"Failed to create IG child: {r.text}")

def create_carousel_parent(children):
    data = {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "access_token": IG_ACCESS_TOKEN,
    }
    r = requests.post(f"{GRAPH_BASE}/{IG_USER_ID}/media", data=data)
    r.raise_for_status()
    return r.json()["id"]

def wait_until_ready(container_id):
    for _ in range(12):  # ~2 minutes
        r = requests.get(
            f"{GRAPH_BASE}/{container_id}",
            params={
                "fields": "status",
                "access_token": IG_ACCESS_TOKEN,
            },
        )
        r.raise_for_status()
        status = r.json().get("status", "")
        log(f"IG container status: {status}")

        # Instagram now returns descriptive strings, not just FINISHED
        if status.upper().startswith("FINISHED"):
            return

        time.sleep(10)

    raise RuntimeError("IG container never became FINISHED")

def publish_container(container_id):
    wait_until_ready(container_id)
    r = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": IG_ACCESS_TOKEN,
        },
    )
    r.raise_for_status()
    return r.json()

# ---------------- MAIN ----------------

def main():
    json_files = sys.argv[1:]
    if not json_files:
        log("No JSON files supplied")
        return 0

    for jf in json_files:
        log(f"Processing {jf}")
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)

        processed_urls = []

        for img in data.get("images", []):
            src = img if img.startswith("http") else f"{SITE_URL_BASE}{img}"
            raw = download_image(src)
            processed = process_image(raw)
            fname = hash_name(src)
            gh_path = f"assets/processed/{fname}"
            url = gh_put_file(gh_path, processed, f"IG processed {fname}")
            processed_urls.append(url)

        if len(processed_urls) == 1:
            cid = create_child_container(processed_urls[0])
            res = publish_container(cid)
            log(f"Published IG single image: {res}")
        else:
            children = []
            for u in processed_urls:
                children.append(create_child_container(u))
                time.sleep(5)

            parent = create_carousel_parent(children)
            res = publish_container(parent)
            log(f"Published IG carousel: {res}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
