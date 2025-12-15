#!/usr/bin/env python3
import os
import sys
import json
import time
import hashlib
import base64
import requests
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO

# ---------------- CONFIG ----------------

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ.get("GITHUB_REPOSITORY")  # owner/repo
PROCESSED_BRANCH = os.environ.get("PROCESSED_BRANCH", "processed-images")

IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

SITE_URL_BASE = os.environ.get("SITE_URL_BASE", "").rstrip("/")

HEADERS_GH = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

GRAPH_BASE = "https://graph.facebook.com/v19.0"

# ---------------- HELPERS ----------------

def log(msg):
    print(msg, flush=True)

def download_image(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def process_image(img_bytes):
    im = Image.open(BytesIO(img_bytes)).convert("RGB")
    im.thumbnail((1350, 1350))
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

def hash_name(url):
    h = hashlib.sha1(url.encode()).hexdigest()[:10]
    name = os.path.basename(urlparse(url).path)
    return f"{h}-{name}".replace(" ", "-")

def gh_get_sha(path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.get(
        url,
        headers=HEADERS_GH,
        params={"ref": PROCESSED_BRANCH},
        timeout=20,
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

    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.put(url, headers=HEADERS_GH, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)

    return r.json()["content"]["download_url"]

# ---------------- INSTAGRAM ----------------

def create_image_container(image_url, is_carousel_item=False):
    data = {
        "image_url": image_url,
        "is_carousel_item": "true" if is_carousel_item else "false",
        "access_token": IG_ACCESS_TOKEN,
    }
    r = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media",
        data=data,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]

def create_carousel(children):
    data = {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "access_token": IG_ACCESS_TOKEN,
    }
    r = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media",
        data=data,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]

def publish_container(container_id):
    data = {
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN,
    }
    r = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media_publish",
        data=data,
        timeout=30,
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

        images = data.get("images", [])
        if not images:
            log("No images found, skipping")
            continue

        processed_urls = []

        for img in images:
            src_url = img if img.startswith("http") else f"{SITE_URL_BASE}{img}"
            log(f"Downloading {src_url}")
            raw = download_image(src_url)
            processed = process_image(raw)

            fname = hash_name(src_url)
            gh_path = f"assets/processed/{fname}"

            log(f"Uploading processed image: {gh_path}")
            url = gh_put_file(
                gh_path,
                processed,
                f"IG processed image {fname}",
            )
            processed_urls.append(url)

        # --- Instagram posting ---
        if len(processed_urls) == 1:
            cid = create_image_container(processed_urls[0])
            time.sleep(10)
            res = publish_container(cid)
            log(f"Published IG single image: {res}")
        else:
            children = []
            for u in processed_urls:
            cid = create_image_container(u, is_carousel_item=True)
            children.append(cid)
            time.sleep(10)  # IMPORTANT: allow IG to process each child

              time.sleep(25)  # IMPORTANT: allow all children to be ready
            parent = create_carousel(children)

            res = publish_container(parent)
            log(f"Published IG carousel: {res}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
