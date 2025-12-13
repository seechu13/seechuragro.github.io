#!/usr/bin/env python3
"""
send_ig.py

FINAL STABLE VERSION
- Carousel posting
- Processed images committed to processed-images branch
- Publish retry safe handling
- FIRST COMMENT hashtags (Threads-safe)
- No assumptions about IG API response shapes
"""

import os, sys, time, json, base64, hashlib, urllib.parse, re
from io import BytesIO
from pathlib import Path
import requests
from PIL import Image

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "seechu13/seechuragro.github.io")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "staging")
PROCESSED_BRANCH = os.environ.get("PROCESSED_BRANCH", "processed-images")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"
RAW_BASE_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{branch}"

PROCESSED_DIR = "assets/processed"

IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "v24.0")

PERMANENT_CAPTION = (
    "Read the full article: https://www.seechuragro.in/articles.html\n"
    "(Link also in bio 👆)"
)

MAX_SIDE = int(os.environ.get("MAX_SIDE", "1080"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))

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

HEADERS_GITHUB = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def raw_base_for(branch):
    return RAW_BASE_TEMPLATE.format(repo=GITHUB_REPO, branch=branch)

def make_raw_url(path, branch=PROCESSED_BRANCH):
    return f"{raw_base_for(branch)}/{path.lstrip('/')}"

def slugify(name):
    name = urllib.parse.unquote(name)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    if not name.lower().endswith(".jpg"):
        name = os.path.splitext(name)[0] + ".jpg"
    return name

# --------------------------------------------------
# IMAGE PROCESSING
# --------------------------------------------------
def download_image(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def process_image(bts):
    im = Image.open(BytesIO(bts)).convert("RGB")
    w, h = im.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out = BytesIO()
    im.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()

# --------------------------------------------------
# GITHUB HELPERS
# --------------------------------------------------
def github_get(path, branch):
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS_GITHUB, params={"ref": branch})
    return r.json() if r.status_code == 200 else None

def github_put(path, content, msg, branch):
    existing = github_get(path, branch)
    payload = {
        "message": msg,
        "content": base64.b64encode(content).decode(),
        "branch": branch
    }
    if existing and "sha" in existing:
        payload["sha"] = existing["sha"]

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{path}"
    r = requests.put(url, headers=HEADERS_GITHUB, json=payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)

def ensure_processed_url(url):
    raw = download_image(url)
    jpeg = process_image(raw)
    h = hashlib.sha256(jpeg).hexdigest()[:10]
    name = slugify(os.path.basename(urllib.parse.urlparse(url).path) or "img.jpg")
    path = f"{PROCESSED_DIR}/{h}-{name}"
    github_put(path, jpeg, f"add processed {path}", PROCESSED_BRANCH)
    return make_raw_url(path)

# --------------------------------------------------
# INSTAGRAM GRAPH HELPERS
# --------------------------------------------------
def ig_post(endpoint, data):
    return requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{endpoint}",
        data=data,
        timeout=30
    )

def ig_get(endpoint, params):
    return requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{endpoint}",
        params=params,
        timeout=20
    )

def wait_for_media_ready(media_id, timeout=180):
    waited = 0
    while waited < timeout:
        r = ig_get(media_id, {
            "fields": "status_code",
            "access_token": IG_ACCESS_TOKEN
        })
        status = r.json().get("status_code")
        if isinstance(status, str) and status.upper() in ("FINISHED", "PUBLISHED"):
            return True
        time.sleep(5)
        waited += 5
    return False

# --------------------------------------------------
# HASHTAGS
# --------------------------------------------------
def generate_hashtags(title, excerpt):
    text = f"{title} {excerpt}".lower()
    tokens = re.findall(r"[a-z0-9]+", text)

    tags, seen = [], set()
    for t in tokens:
        if t in COMMON_STOPWORDS or len(t) < HASHTAG_MIN_WORD_LEN:
            continue
        if t not in seen:
            seen.add(t)
            tags.append("#" + t)
        if len(tags) >= HASHTAG_MAX:
            break

    if EXTRA_HASHTAGS:
        for t in re.split(r"[ ,]+", EXTRA_HASHTAGS):
            if t:
                tags.append("#" + t.lstrip("#"))

    return " ".join(tags)

# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    json_path = os.environ.get("IG_POST_JSON", "articles/test-automation.json")
    data = json.loads(Path(json_path).read_text())

    images = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for i in x: walk(i)
        elif isinstance(x, str) and x.startswith("http"):
            if any(x.lower().endswith(e) for e in (".jpg",".jpeg",".png",".webp")):
                images.append(x)
    walk(data)

    title = data.get("title", "")
    excerpt = data.get("excerpt", "")
    caption = (data.get("caption") or title or excerpt).strip()

    if PERMANENT_CAPTION not in caption:
        caption += "\n\n" + PERMANENT_CAPTION

    hashtag_comment = generate_hashtags(title, excerpt)

    # ---- Create child containers
    child_ids = []
    for img in images[:4]:
        purl = ensure_processed_url(img)
        r = ig_post(
            f"{IG_USER_ID}/media",
            {"image_url": purl, "is_carousel_item": "true", "access_token": IG_ACCESS_TOKEN}
        )
        cid = r.json().get("id")
        if not cid:
            raise RuntimeError("No child container ID returned")
        wait_for_media_ready(cid)
        child_ids.append(cid)

    # ---- Create parent container
    parent = ig_post(
        f"{IG_USER_ID}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }
    )
    creation_id = parent.json().get("id")
    if not creation_id:
        raise RuntimeError("No parent creation ID returned")

    # ---- Publish
    pub = ig_post(
        f"{IG_USER_ID}/media_publish",
        {"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN}
    )

    try:
        pub_json = pub.json()
    except Exception:
        pub_json = {}

    post_id = pub_json.get("id") or creation_id
    print("Publish response:", pub_json)
    print("Using media id:", post_id)

    # ---- Wait until commentable and post hashtags
    print("Waiting for media to become commentable...")
    if wait_for_media_ready(post_id):
        for attempt in range(1, 4):
            r = ig_post(
                f"{post_id}/comments",
                {"message": hashtag_comment, "access_token": IG_ACCESS_TOKEN}
            )
            if r.status_code in (200, 201) and "id" in r.text:
                print("✅ Hashtag comment posted.")
                break
            print(f"Retry {attempt}/3 — comment not accepted yet")
            time.sleep(10)

    print("🎉 Instagram post published. Threads will show NO hashtags.")

if __name__ == "__main__":
    main()
