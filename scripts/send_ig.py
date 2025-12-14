#!/usr/bin/env python3
"""
send_ig.py — FINAL STABLE VERSION

- Instagram carousel only
- NO hashtags
- NO comments
- Processes images and commits to processed-images branch
- Binary-safe (no UTF-8 decoding of images)
- One image failure = hard stop (correct behavior)
"""

import os, sys, time, json, base64, hashlib, urllib.parse
from io import BytesIO
from pathlib import Path
import requests
from PIL import Image

# -------------------------
# CONFIG
# -------------------------
GITHUB_REPO = os.environ["GITHUB_REPO"]
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "staging")
PROCESSED_BRANCH = os.environ.get("PROCESSED_BRANCH", "processed-images")

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "v24.0")

PROCESSED_DIR = "assets/processed"
MAX_SIDE = 1080
JPEG_QUALITY = 85

PERMANENT_CAPTION = (
    "Read the full article: https://www.seechuragro.in/articles.html\n"
    "(Link also in bio 👆)"
)

HEADERS_GH = {"Authorization": f"token {GITHUB_TOKEN}"}

# -------------------------
# IMAGE HELPERS
# -------------------------
def download_image(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def process_image(img_bytes):
    im = Image.open(BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out = BytesIO()
    im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()

def commit_image(jpeg_bytes, name):
    sha = hashlib.sha256(jpeg_bytes).hexdigest()[:10]
    filename = f"{sha}-{name}"
    path = f"{PROCESSED_DIR}/{filename}"

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": f"add processed image {filename}",
        "content": base64.b64encode(jpeg_bytes).decode("ascii"),
        "branch": PROCESSED_BRANCH,
    }

    r = requests.put(url, headers=HEADERS_GH, json=payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)

    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{PROCESSED_BRANCH}/{path}"

# -------------------------
# INSTAGRAM HELPERS
# -------------------------
def ig_post(endpoint, data):
    return requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{endpoint}",
        data=data,
        timeout=30,
    )

def wait_ready(cid, timeout=120):
    waited = 0
    while waited < timeout:
        r = requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{cid}",
            params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN},
            timeout=20,
        )
        if r.json().get("status_code") == "FINISHED":
            return True
        time.sleep(5)
        waited += 5
    return False

# -------------------------
# MAIN
# -------------------------
def main():
    json_path = os.environ.get("IG_POST_JSON", "social_new.json")
    data = json.loads(Path(json_path).read_text())

    images = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for i in x: walk(i)
        elif isinstance(x, str) and x.lower().endswith((".jpg",".jpeg",".png",".webp")):
            images.append(x)

    walk(data)
    images = images[:4]

    caption = (data.get("title") or data.get("excerpt") or "").strip()
    caption += "\n\n" + PERMANENT_CAPTION

    child_ids = []

    for url in images:
        raw = download_image(url)
        jpeg = process_image(raw)
        name = os.path.basename(urllib.parse.urlparse(url).path)
        processed_url = commit_image(jpeg, name)

        r = ig_post(
            f"{IG_USER_ID}/media",
            {
                "image_url": processed_url,
                "is_carousel_item": "true",
                "access_token": IG_ACCESS_TOKEN,
            },
        )

        cid = r.json().get("id")
        if not cid or not wait_ready(cid):
            raise RuntimeError("Child container failed")

        child_ids.append(cid)

    parent = ig_post(
        f"{IG_USER_ID}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN,
        },
    )

    pid = parent.json().get("id")
    if not pid:
        raise RuntimeError("Parent container failed")

    ig_post(
        f"{IG_USER_ID}/media_publish",
        {"creation_id": pid, "access_token": IG_ACCESS_TOKEN},
    )

    print("✅ Instagram carousel published successfully")

if __name__ == "__main__":
    sys.exit(main())
