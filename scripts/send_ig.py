#!/usr/bin/env python3 
"""
send_ig.py — posts to Instagram with processed images committed to a separate branch (PROCESSED_BRANCH)
Drop-in replacement. Commits processed images to PROCESSED_BRANCH (default: processed-images)
so the main content branch (GITHUB_BRANCH, e.g. staging) does not get noisy commits.
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

PERMANENT_CAPTION = "Read the full article: https://www.seechuragro.in/articles.html\n(Link also in bio 👆)"

IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "v24.0")

MAX_SIDE = int(os.environ.get("MAX_SIDE", "1080"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "30"))
DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", "3"))
SLEEP_BETWEEN_RETRIES = int(os.environ.get("SLEEP_BETWEEN_RETRIES", "2"))

HEADERS_GITHUB = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

HASHTAG_MAX = int(os.environ.get("HASHTAG_MAX", "30"))
HASHTAG_MIN_WORD_LEN = int(os.environ.get("HASHTAG_MIN_WORD_LEN", "3"))
EXTRA_HASHTAGS = os.environ.get("EXTRA_HASHTAGS", "")

COMMON_STOPWORDS = {
    "the","and","for","that","with","this","from","have","are","was","were","will",
    "but","not","you","your","our","who","what","when","where","how","why","which",
    "their","they","them","been","had","has","about","into","over","through","also",
    "more","other","these","those","there","such","may","can","its","it's","a","an",
    "in","on","of","to","by","as"
}

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
    path = path.lstrip("/")
    return f"{raw_base_for(branch)}/{path}"

def download_bytes(url, retries=DOWNLOAD_RETRIES):
    exc = None
    for i in range(retries):
        try:
            r = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True, headers={"User-Agent":"SeechurAgroBot/1.0"})
            r.raise_for_status()
            return r.content
        except Exception as e:
            exc = e
            time.sleep(SLEEP_BETWEEN_RETRIES * (i+1))
    raise RuntimeError(f"download failed for {url}: {exc}")

def process_to_jpeg_bytes(bts):
    im = Image.open(BytesIO(bts))
    if im.mode in ("RGBA","LA") or (im.mode == "P" and "transparency" in im.info):
        bg = Image.new("RGB", im.size, (255,255,255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    else:
        im = im.convert("RGB")
    w,h = im.size
    maxside = max(w,h)
    if maxside > MAX_SIDE:
        scale = MAX_SIDE / float(maxside)
        im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    out = BytesIO()
    im.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()

# -------------------------
# GitHub helpers
# -------------------------
def github_get_file(path, branch=None):
    branch = branch or PROCESSED_BRANCH
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    params = {"ref": branch}
    r = requests.get(url, headers=HEADERS_GITHUB, params=params)
    if r.status_code == 200:
        j = r.json()
        return {"sha": j.get("sha")}
    if r.status_code == 404:
        return None
    raise RuntimeError(f"github_get_file failed for {path} (branch={branch}): {r.status_code} {r.text}")

def github_put_file(path, content_bytes, message, branch=None, sha=None):
    branch = branch or PROCESSED_BRANCH
    if sha is None:
        existing = github_get_file(path, branch=branch)
        sha = existing["sha"] if existing else None

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    b64 = base64.b64encode(content_bytes).decode("ascii")
    body = {"message": message, "content": b64, "branch": branch}
    if sha:
        body["sha"] = sha

    r = requests.put(url, headers=HEADERS_GITHUB, json=body)
    if r.status_code not in (200,201):
        raise RuntimeError(f"github_put_file failed (path={path}, branch={branch}): {r.status_code} {r.text}")
    return r.json()

def ensure_processed_branch_exists():
    ref_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/ref/heads/{PROCESSED_BRANCH}"
    r = requests.get(ref_url, headers=HEADERS_GITHUB)
    if r.status_code == 200:
        return True

    src_ref_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/ref/heads/{GITHUB_BRANCH}"
    r2 = requests.get(src_ref_url, headers=HEADERS_GITHUB)
    src_sha = r2.json()["object"]["sha"]

    create_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/refs"
    requests.post(create_url, headers=HEADERS_GITHUB,
                  json={"ref": f"refs/heads/{PROCESSED_BRANCH}", "sha": src_sha})
    return True

# -------------------------
# ensure processed URL
# -------------------------
def ensure_processed_url_for(original_url):
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set")

    bts = download_bytes(original_url)
    jb = process_to_jpeg_bytes(bts)

    parsed = urllib.parse.urlparse(original_url)
    base = os.path.basename(parsed.path) or "img"
    name = _slugify(base)

    h = hashlib.sha256(jb).hexdigest()[:10]
    final_name = f"{h}-{name}"
    target_repo_path = f"{PROCESSED_DIR}/{final_name}"

    ensure_processed_branch_exists()
    github_put_file(
        target_repo_path,
        jb,
        f"chore: add/update processed image {target_repo_path}",
        branch=PROCESSED_BRANCH,
    )

    return make_raw_url(target_repo_path, branch=PROCESSED_BRANCH)

# -------------------------
# Graph API helpers
# -------------------------
def create_image_container(image_url, is_carousel_item=False):
    params = {"image_url": image_url, "access_token": IG_ACCESS_TOKEN}
    if is_carousel_item:
        params["is_carousel_item"] = "true"
    return requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media",
        data=params,
        timeout=30,
    )

def create_parent_container(creation_ids, caption=""):
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(creation_ids),
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }
    return requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media",
        data=params,
        timeout=30,
    )

def publish_parent_container(parent_id):
    params = {"creation_id": parent_id, "access_token": IG_ACCESS_TOKEN}
    return requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media_publish",
        data=params,
        timeout=30,
    )

def wait_for_media_ready(cid, timeout=120, poll_interval=2):
    waited = 0
    while waited < timeout:
        r = requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{cid}",
            params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN},
            timeout=20,
        )
        sc = r.json().get("status_code")
        if isinstance(sc, str) and sc.upper() == "FINISHED":
            return True
        time.sleep(poll_interval)
        waited += poll_interval
    return False

# -------------------------
# Main logic
# -------------------------
def main():
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        sys.exit(2)

    json_path = os.environ.get("IG_POST_JSON", "social_new.json")
    raw = json.loads(Path(json_path).read_text(encoding="utf-8"))

    images = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for i in x: walk(i)
        elif isinstance(x, str):
            low = x.lower()
            if low.startswith(("http://","https://")) and low.endswith((".jpg",".jpeg",".png",".webp")):
                images.append(x)
    walk(raw)

    images = images[:4]
    caption = (raw.get("title") or raw.get("excerpt") or "").strip()

    if PERMANENT_CAPTION not in caption:
        caption += "\n\n" + PERMANENT_CAPTION

    # 🔒 HASHTAGS DISABLED — DO NOT CHANGE
    tags = []

    child_ids = []
    for url in images:
        processed = ensure_processed_url_for(url)
        r = create_image_container(processed, is_carousel_item=True)
        cid = r.json().get("id")
        if not cid:
            sys.exit(1)
        if not wait_for_media_ready(cid):
            sys.exit(1)
        child_ids.append(cid)

    parent = create_parent_container(child_ids, caption=caption)
    parent_id = parent.json().get("id")
    if not parent_id:
        sys.exit(1)

    publish_parent_container(parent_id)
    print("Instagram post published successfully.")

if __name__ == "__main__":
    sys.exit(main() or 0)
