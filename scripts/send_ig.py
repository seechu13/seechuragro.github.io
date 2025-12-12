#!/usr/bin/env python3
"""
send_ig.py — fixed to avoid 422 'sha wasn't supplied' when committing processed images.
Minimal behavioral change: if a target repo file exists, fetch its sha and pass to the GitHub PUT call.
Everything else left intact (image processing, processed_map handling, IG posting).
"""
import os, sys, time, json, base64, hashlib, urllib.parse
from io import BytesIO
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image
import re

# ===========================
# CONFIG / CONSTANTS
# ===========================
GITHUB_REPO = os.environ.get("GITHUB_REPO", "seechu13/seechuragro.github.io")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "staging")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_API_BASE = "https://api.github.com"
PROCESSED_DIR = "assets/processed"
PROCESSED_MAP = f"{PROCESSED_DIR}/processed_map.json"

PERMANENT_CAPTION = "Read the full article: https://www.seechuragro.in/articles.html\n(Link also in bio 👆)"
PERMANENT_WEBSITE = "https://www.seechuragro.in/articles.html"

IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "v24.0")

MAX_SIDE = int(os.environ.get("MAX_SIDE", "1080"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "30"))
DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", "3"))
SLEEP_BETWEEN_RETRIES = int(os.environ.get("SLEEP_BETWEEN_RETRIES", "2"))

HEADERS_GITHUB = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# Hashtag config
HASHTAG_MAX = int(os.environ.get("HASHTAG_MAX", "30"))
HASHTAG_MIN_WORD_LEN = int(os.environ.get("HASHTAG_MIN_WORD_LEN", "3"))
EXTRA_HASHTAGS = os.environ.get("EXTRA_HASHTAGS", "")

COMMON_STOPWORDS = {
    "the","and","for","that","with","this","from","have","are","was","were","will",
    "but","not","you","your","our","who","what","when","where","how","why","which",
    "their","they","them","been","had","has","about","into","over","through","also",
    "more","other","these","those","there","such","may","can","its","it's","a","an","in","on","of","to","by","as"
}

# ===========================
# Helpers
# ===========================
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

def make_raw_url(path):
    path = path.lstrip("/")
    return f"{RAW_BASE}/{path}"

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

# GitHub helpers (fixed)
def github_get_file(path):
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    params = {"ref": GITHUB_BRANCH}
    r = requests.get(url, headers=HEADERS_GITHUB, params=params)
    if r.status_code == 200:
        j = r.json()
        return {"sha": j.get("sha"), "content_b64": j.get("content"), "text": base64.b64decode(j.get("content")).decode("utf-8", errors="ignore")}
    if r.status_code in (404,):
        return None
    raise RuntimeError(f"github_get_file failed for {path}: {r.status_code} {r.text}")

def github_put_file(path, content_bytes, message, sha=None):
    """
    Creates or updates a file in the repo.
    If sha not provided, attempt to fetch the existing file sha (if any) and use it.
    This prevents 422 errors when updating an existing file.
    """
    # If sha not provided, try to see if file exists and get its sha
    if sha is None:
        try:
            existing = github_get_file(path)
            sha = existing["sha"] if existing else None
        except Exception as e:
            # If we couldn't fetch existing file (maybe network issue), continue without sha;
            # GitHub will accept create requests (no sha) for new files.
            sha = None

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    b64 = base64.b64encode(content_bytes).decode("ascii")
    body = {"message": message, "content": b64, "branch": GITHUB_BRANCH}
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=HEADERS_GITHUB, json=body)
    if r.status_code not in (200,201):
        raise RuntimeError(f"github_put_file failed: {r.status_code} {r.text}")
    return r.json()

def load_processed_map_local():
    p = Path(PROCESSED_MAP)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def load_processed_map_remote():
    raw_url = make_raw_url(PROCESSED_MAP)
    r = requests.get(raw_url, timeout=10)
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return None
    return None

def update_processed_map_and_commit(mapobj, commit_message="chore: update processed_map"):
    content = json.dumps(mapobj, indent=2, ensure_ascii=False).encode("utf-8")
    existing = github_get_file(PROCESSED_MAP)
    sha = existing["sha"] if existing else None
    res = github_put_file(PROCESSED_MAP, content, commit_message, sha=sha)
    return res

def commit_processed_image_and_map(image_bytes, target_repo_path, processed_map):
    # Try to PUT image; github_put_file now auto-fetches sha if needed
    try:
        github_put_file(target_repo_path, image_bytes, f"chore: add/update processed image {target_repo_path}")
    except Exception as e:
        raise RuntimeError(f"failed to commit image to {target_repo_path}: {e}")
    update_processed_map_and_commit(processed_map, commit_message=f"chore: update processed_map for {target_repo_path}")
    return True

def ensure_processed_url_for(original_url):
    map_local = load_processed_map_local()
    if map_local and original_url in map_local:
        return map_local[original_url].get("processed")
    map_remote = load_processed_map_remote()
    if map_remote and original_url in map_remote:
        return map_remote[original_url].get("processed")
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set; cannot commit processed image automatically.")
    bts = download_bytes(original_url)
    jb = process_to_jpeg_bytes(bts)
    parsed = urllib.parse.urlparse(original_url)
    base = os.path.basename(parsed.path) or "img"
    name = _slugify(base) if '_slugify' in globals() else base
    if not name:
        keep = []
        for ch in base:
            if ch.isalnum() or ch in "-_.":
                keep.append(ch)
            else:
                keep.append("_")
        s = "".join(keep)
        name = s if s else "image.jpg"
    h = hashlib.sha256(jb).hexdigest()[:10]
    final_name = f"{h}-{name}"
    target_repo_path = f"{PROCESSED_DIR}/{final_name}"
    raw_url = make_raw_url(target_repo_path)
    width, height = Image.open(BytesIO(jb)).size
    entry = {
        "processed": raw_url,
        "variants": {"default": raw_url},
        "sha256": hashlib.sha256(jb).hexdigest(),
        "width": width,
        "height": height,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "repo_path": target_repo_path
    }
    newmap = load_processed_map_remote() or load_processed_map_local() or {}
    newmap[original_url] = entry
    commit_processed_image_and_map(jb, target_repo_path, newmap)
    return raw_url

# Graph helpers (unchanged)
def create_image_container(image_url, is_carousel_item=False):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media"
    params = {"image_url": image_url, "access_token": IG_ACCESS_TOKEN}
    if is_carousel_item:
        params["is_carousel_item"] = "true"
    r = requests.post(url, data=params, timeout=30)
    return r

def create_parent_container(creation_id_list, caption=""):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media"
    children = ",".join(creation_id_list)
    params = {"media_type": "CAROUSEL", "children": children, "caption": caption, "access_token": IG_ACCESS_TOKEN}
    r = requests.post(url, data=params, timeout=30)
    return r

def publish_parent_container(parent_id):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media_publish"
    params = {"creation_id": parent_id, "access_token": IG_ACCESS_TOKEN}
    r = requests.post(url, data=params, timeout=30)
    return r

# Hashtag generation (unchanged)
def make_candidate_tokens(text):
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens = [t for t in tokens if len(t) >= HASHTAG_MIN_WORD_LEN]
    return tokens

def generate_hashtags(title, excerpt, max_tags=HASHTAG_MAX):
    tokens_title = make_candidate_tokens(title)
    tokens_excerpt = make_candidate_tokens(excerpt)
    seq = tokens_title + tokens_excerpt
    seen = set()
    tags = []
    for t in seq:
        if t in COMMON_STOPWORDS:
            continue
        if t.isdigit():
            continue
        if t in seen:
            continue
        seen.add(t)
        tags.append("#" + t)
        if len(tags) >= max_tags:
            break
    if EXTRA_HASHTAGS:
        extras = [x.strip().lower() for x in EXTRA_HASHTAGS.split(",") if x.strip()]
        for e in extras:
            e_clean = re.sub(r"[^a-z0-9]", "", e)
            if not e_clean or e_clean in seen:
                continue
            tags.append("#" + e_clean)
            seen.add(e_clean)
            if len(tags) >= max_tags:
                break
    return tags[:max_tags]

# Main flow (unchanged from your original, aside from using the fixed helpers)
def main():
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("ERROR: IG_USER_ID or IG_ACCESS_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    print("IG_USER_ID in environment:", IG_USER_ID)
    json_path = os.environ.get("IG_POST_JSON", "articles/test-automation.json")
    raw = None
    try:
        raw_text = Path(json_path).read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except Exception:
        raw = None

    images = []
    caption = ""
    title_text = ""
    excerpt_text = ""
    if raw:
        def walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for x in obj:
                    walk(x)
            elif isinstance(obj, str):
                low = obj.lower()
                if low.startswith("http://") or low.startswith("https://"):
                    if any(low.endswith(ext) for ext in (".jpg",".jpeg",".png",".webp")):
                        images.append(obj)
        walk(raw)
        if isinstance(raw, dict):
            caption = raw.get("caption") or raw.get("title") or raw.get("excerpt") or ""
            title_text = raw.get("title") or ""
            excerpt_text = raw.get("excerpt") or raw.get("summary") or ""
    else:
        env_imgs = os.environ.get("IMAGES")
        if env_imgs:
            images = [x.strip() for x in env_imgs.split(",") if x.strip()]
            caption = os.environ.get("CAPTION","")
            title_text = os.environ.get("TITLE","")
            excerpt_text = os.environ.get("EXCERPT","")

    if not images:
        print("No images found to post.", file=sys.stderr)
        sys.exit(0)

    images = images[:4]
    print("Posting to IG with images:", images)

    processed_urls = []
    for u in images:
        try:
            purl = ensure_processed_url_for(u)
            print("USING PROCESSED URL:", purl)
            processed_urls.append(purl)
        except Exception as e:
            print("ERROR preparing image:", u, e, file=sys.stderr)
            sys.exit(1)

    caption = (caption or "").strip()
    if PERMANENT_CAPTION not in caption:
        if caption:
            caption = caption + "\n\n" + PERMANENT_CAPTION
        else:
            caption = PERMANENT_CAPTION

    try:
        tags = generate_hashtags(title_text, excerpt_text, max_tags=HASHTAG_MAX)
    except Exception as e:
        print("Hashtag generation failed, continuing without hashtags:", e, file=sys.stderr)
        tags = []

    if tags:
        caption = caption.rstrip() + "\n\n" + " ".join(tags)

    print("\nFinal caption preview:\n", caption, "\n")

    # Post logic (same)
    if len(processed_urls) == 1:
        single_url = processed_urls[0]
        print("Creating SINGLE image container for:", single_url)
        resp = requests.post(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media",
            data={
                "image_url": single_url,
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN
            },
            timeout=30
        )
        print("Single image CREATE returned", resp.status_code, "->", resp.text)
        if resp.status_code not in (200, 201):
            print("Single image creation failed:", resp.status_code, resp.text, file=sys.stderr)
            sys.exit(1)
        creation_id = resp.json().get("id")
        if not creation_id:
            print("Could not get creation_id for single image:", resp.text, file=sys.stderr)
            sys.exit(1)
        pub_resp = requests.post(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{IG_USER_ID}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": IG_ACCESS_TOKEN
            },
            timeout=30
        )
        print("Publish response:", pub_resp.status_code, pub_resp.text)
        if pub_resp.status_code not in (200, 201):
            print("Publish failed:", pub_resp.status_code, pub_resp.text, file=sys.stderr)
            sys.exit(1)
        pub_json = pub_resp.json()
        published_post_id = pub_json.get("id") or pub_json.get("post_id") or json.dumps(pub_json)
        print("Published IG SINGLE image post id:", published_post_id)
        return 0

    child_ids = []
    for pu in processed_urls:
        print("Creating child container for:", pu)
        resp = create_image_container(pu, is_carousel_item=True)
        print("CREATE child returned", resp.status_code, "->", resp.text)
        if resp.status_code not in (200, 201):
            print("create_image_container failed:", resp.status_code, resp.text, file=sys.stderr)
            sys.exit(1)
        cid = resp.json().get("id")
        if not cid:
            print("No child id returned in response:", resp.text, file=sys.stderr)
            sys.exit(1)
        child_ids.append(cid)

    print("Creating parent CAROUSEL container with children:", child_ids)
    parent_resp = create_parent_container(child_ids, caption=caption)
    print("Parent create response:", parent_resp.status_code, parent_resp.text)
    if parent_resp.status_code not in (200, 201):
        print("Parent creation failed:", parent_resp.status_code, parent_resp.text, file=sys.stderr)
        sys.exit(1)
    parent_id = parent_resp.json().get("id")
    if not parent_id:
        print("No parent creation id returned:", parent_resp.text, file=sys.stderr)
        sys.exit(1)

    pub_resp = publish_parent_container(parent_id)
    print("Publish response:", pub_resp.status_code, pub_resp.text)
    if pub_resp.status_code not in (200, 201):
        print("Publish failed:", pub_resp.status_code, pub_resp.text, file=sys.stderr)
        sys.exit(1)

    pub_json = pub_resp.json()
    published_post_id = pub_json.get("id") or pub_json.get("post_id") or json.dumps(pub_json)
    print("Published IG CAROUSEL post id:", published_post_id)
    return 0

if __name__ == "__main__":
    try:
        rc = main() or 0
        sys.exit(rc)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
