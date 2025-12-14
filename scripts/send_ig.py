#!/usr/bin/env python3
"""
send_ig.py — FINAL AUTHORITATIVE VERSION (NO HASHTAGS, THREADS-SAFE)

- Carousel posting only
- Processed images committed to PROCESSED_BRANCH
- NO hashtags anywhere (caption or comments)
- Threads inherits clean caption
- Deterministic, retry-safe
"""

import os, sys, time, json, base64, hashlib, urllib.parse
from io import BytesIO
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image
import re

# -------------------------
# CONFIG
# -------------------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "seechu13/seechuragro.github.io")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "staging")
PROCESSED_BRANCH = os.environ.get("PROCESSED_BRANCH", "processed-images")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RAW_BASE_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{branch}"
GITHUB_API_BASE = "https://api.github.com"

PROCESSED_DIR = "assets/processed"
PROCESSED_MAP = f"{PROCESSED_DIR}/processed_map.json"

PERMANENT_CAPTION = (
    "Read the full article: https://www.seechuragro.in/articles.html\n"
    "(Link also in bio 👆)"
)

IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "v24.0")

MAX_SIDE = int(os.environ.get("MAX_SIDE", "1080"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "30"))
DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", "3"))
SLEEP_BETWEEN_RETRIES = int(os.environ.get("SLEEP_BETWEEN_RETRIES", "2"))

HEADERS_GITHUB = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# -------------------------
# Helpers
# -------------------------
def _slugify(n):
    n = urllib.parse.unquote(n.strip())
    keep = []
    for ch in n:
        if ch.isalnum() or ch in "-_.":
            keep.append(ch)
        else:
            keep.append("_")
    s = "".join(keep)
    if not s.lower().endswith(".jpg"):
        s = os.path.splitext(s)[0] + ".jpg"
    return s

def raw_base_for(branch):
    return RAW_BASE_TEMPLATE.format(repo=GITHUB_REPO, branch=branch)

def make_raw_url(path, branch=PROCESSED_BRANCH):
    return f"{raw_base_for(branch)}/{path.lstrip('/')}"

# -------------------------
# Image helpers
# -------------------------
def download_bytes(url):
    for i in range(DOWNLOAD_RETRIES):
        try:
            r = requests.get(
                url,
                timeout=DOWNLOAD_TIMEOUT,
                headers={"User-Agent": "SeechurAgroBot/1.0"},
                stream=True,
            )
            r.raise_for_status()
            return r.content
        except Exception:
            time.sleep(SLEEP_BETWEEN_RETRIES * (i + 1))
    raise RuntimeError(f"Download failed for {url}")

def process_to_jpeg_bytes(bts):
    im = Image.open(BytesIO(bts))
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / float(max(w, h))
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out = BytesIO()
    im.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()

# -------------------------
# GitHub helpers
# -------------------------
def github_get_file(path, branch):
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    r = requests.get(url, headers=HEADERS_GITHUB, params={"ref": branch})
    if r.status_code == 200:
        j = r.json()
        return {"sha": j["sha"], "text": base64.b64decode(j["content"]).decode()}
    return None

def github_put_file(path, content_bytes, message, branch, sha=None):
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=HEADERS_GITHUB, json=body)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)

def ensure_processed_branch():
    ref = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/ref/heads/{PROCESSED_BRANCH}"
    r = requests.get(ref, headers=HEADERS_GITHUB)
    if r.status_code == 200:
        return
    src = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/ref/heads/{GITHUB_BRANCH}"
    r2 = requests.get(src, headers=HEADERS_GITHUB)
    sha = r2.json()["object"]["sha"]
    requests.post(
        f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/refs",
        headers=HEADERS_GITHUB,
        json={"ref": f"refs/heads/{PROCESSED_BRANCH}", "sha": sha},
    )

def ensure_processed_url(original_url):
    ensure_processed_branch()
    bts = download_bytes(original_url)
    jpeg = process_to_jpeg_bytes(bts)

    h = hashlib.sha256(jpeg).hexdigest()[:10]
    base = os.path.basename(urllib.parse.urlparse(original_url).path) or "img.jpg"
    name = _slugify(base)
    final = f"{h}-{name}"

    path = f"{PROCESSED_DIR}/{final}"
    existing = github_get_file(path, PROCESSED_BRANCH)
    sha = existing["sha"] if existing else None

    github_put_file(
        path,
        jpeg,
        f"chore: add processed image {path}",
        PROCESSED_BRANCH,
        sha=sha,
    )
    return make_raw_url(path)

# -------------------------
# Graph helpers
# -------------------------
def ig_post(endpoint, data):
    return requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{endpoint}",
        data=data,
        timeout=30,
    )

def ig_get(endpoint, params):
    return requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{endpoint}",
        params=params,
        timeout=20,
    )

def wait_ready(cid, timeout=120):
    waited = 0
    while waited < timeout:
        r = ig_get(cid, {"fields": "status_code", "access_token": IG_ACCESS_TOKEN})
        status = r.json().get("status_code")
        if isinstance(status, str) and status.upper() in ("FINISHED", "PUBLISHED"):
            return True
        time.sleep(5)
        waited += 5
    return False

# -------------------------
# MAIN
# -------------------------
def main():
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        sys.exit("Missing IG credentials")

    json_path = os.environ.get("IG_POST_JSON", "social_new.json")
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))

    images = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for i in x: walk(i)
        elif isinstance(x, str) and x.startswith("http") and x.lower().endswith((".jpg",".jpeg",".png",".webp")):
            images.append(x)
    walk(data)

    images = images[:4]
    if not images:
        sys.exit("No images found")

    title = data.get("title","")
    excerpt = data.get("excerpt","")
    caption = (title or excerpt).strip()
    caption += "\n\n" + PERMANENT_CAPTION

    child_ids = []
    for img in images:
        purl = ensure_processed_url(img)
        r = ig_post(
            f"{IG_USER_ID}/media",
            {"image_url": purl, "is_carousel_item": "true", "access_token": IG_ACCESS_TOKEN}
        )
        cid = r.json().get("id")
        if not cid:
            raise RuntimeError("No child container ID returned")
        if not wait_ready(cid):
            raise RuntimeError("Media not ready")
        child_ids.append(cid)

    parent = ig_post(
        f"{IG_USER_ID}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }
    )

    pid = parent.json().get("id")
    if not pid:
        raise RuntimeError("No parent container ID")

    pub = ig_post(
        f"{IG_USER_ID}/media_publish",
        {"creation_id": pid, "access_token": IG_ACCESS_TOKEN}
    )

    print("Instagram published:", pub.json())

if __name__ == "__main__":
    main()
