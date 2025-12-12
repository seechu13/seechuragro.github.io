#!/usr/bin/env python3
"""
send_ig.py — posts to Instagram with processed images committed to a separate branch (PROCESSED_BRANCH)
Drop-in replacement. Commits processed images to PROCESSED_BRANCH (default: processed-images)
so the main content branch (GITHUB_BRANCH, e.g. staging) does not get noisy commits.

Requirements:
- GITHUB_TOKEN with contents: write permissions (workflow sets permissions: contents: write)
- IG_USER_ID, IG_ACCESS_TOKEN set in env
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
# branch holding article content (source). This should remain your staging branch.
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "staging")
# branch to put processed images into (separate, to avoid triggering site builds)
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

# Hashtag config (unchanged)
HASHTAG_MAX = int(os.environ.get("HASHTAG_MAX", "30"))
HASHTAG_MIN_WORD_LEN = int(os.environ.get("HASHTAG_MIN_WORD_LEN", "3"))
EXTRA_HASHTAGS = os.environ.get("EXTRA_HASHTAGS", "")

COMMON_STOPWORDS = {
    "the","and","for","that","with","this","from","have","are","was","were","will",
    "but","not","you","your","our","who","what","when","where","how","why","which",
    "their","they","them","been","had","has","about","into","over","through","also",
    "more","other","these","those","there","such","may","can","its","it's","a","an","in","on","of","to","by","as"
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
# GitHub helpers (supporting processed branch)
# -------------------------
def github_get_file(path, branch=None):
    branch = branch or PROCESSED_BRANCH
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path, safe='')}"
    params = {"ref": branch}
    r = requests.get(url, headers=HEADERS_GITHUB, params=params)
    if r.status_code == 200:
        j = r.json()
        return {"sha": j.get("sha"), "content_b64": j.get("content"), "text": base64.b64decode(j.get("content")).decode("utf-8", errors="ignore")}
    if r.status_code in (404,):
        return None
    raise RuntimeError(f"github_get_file failed for {path} (branch={branch}): {r.status_code} {r.text}")

def github_put_file(path, content_bytes, message, branch=None, sha=None):
    """
    Create/update file on the given branch. If sha not given, attempt to fetch it.
    """
    branch = branch or PROCESSED_BRANCH
    if sha is None:
        try:
            existing = github_get_file(path, branch=branch)
            sha = existing["sha"] if existing else None
        except Exception:
            sha = None
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
    """
    Ensure PROCESSED_BRANCH exists; if not, create it from GITHUB_BRANCH (source).
    Returns True if branch exists or was created successfully.
    """
    # check ref
    ref_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/ref/heads/{PROCESSED_BRANCH}"
    r = requests.get(ref_url, headers=HEADERS_GITHUB)
    if r.status_code == 200:
        return True
    # not exists -> create from source branch
    src_ref_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/ref/heads/{GITHUB_BRANCH}"
    r2 = requests.get(src_ref_url, headers=HEADERS_GITHUB)
    if r2.status_code != 200:
        raise RuntimeError(f"Could not read source branch ref {GITHUB_BRANCH}: {r2.status_code} {r2.text}")
    src_sha = r2.json().get("object", {}).get("sha")
    if not src_sha:
        raise RuntimeError("Could not determine source branch SHA to create processed branch.")
    create_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/refs"
    body = {"ref": f"refs/heads/{PROCESSED_BRANCH}", "sha": src_sha}
    r3 = requests.post(create_url, headers=HEADERS_GITHUB, json=body)
    if r3.status_code not in (201,):
        # If race condition (someone else created), accept existing
        if r3.status_code == 422 and "Reference already exists" in r3.text:
            return True
        raise RuntimeError(f"Could not create processed branch {PROCESSED_BRANCH}: {r3.status_code} {r3.text}")
    return True

# -------------------------
# Processed map helpers
# -------------------------
def load_processed_map_local():
    p = Path(PROCESSED_MAP)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def load_processed_map_remote(branch=None):
    branch = branch or PROCESSED_BRANCH
    raw_url = make_raw_url(PROCESSED_MAP, branch=branch)
    r = requests.get(raw_url, timeout=10)
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return None
    return None

def update_processed_map_and_commit(mapobj, commit_message="chore: update processed_map"):
    ensure_processed_branch_exists()
    content = json.dumps(mapobj, indent=2, ensure_ascii=False).encode("utf-8")
    existing = github_get_file(PROCESSED_MAP, branch=PROCESSED_BRANCH)
    sha = existing["sha"] if existing else None
    res = github_put_file(PROCESSED_MAP, content, commit_message, branch=PROCESSED_BRANCH, sha=sha)
    return res

def commit_processed_image_and_map(image_bytes, target_repo_path, processed_map):
    ensure_processed_branch_exists()
    try:
        github_put_file(target_repo_path, image_bytes, f"chore: add/update processed image {target_repo_path}", branch=PROCESSED_BRANCH)
    except Exception as e:
        raise RuntimeError(f"failed to commit image to {target_repo_path}: {e}")
    update_processed_map_and_commit(processed_map, commit_message=f"chore: update processed_map for {target_repo_path}")
    return True

# -------------------------
# ensure processed URL for an original URL
# -------------------------
def ensure_processed_url_for(original_url):
    # check remote processed map first (on processed branch)
    map_remote = load_processed_map_remote(branch=PROCESSED_BRANCH)
    if map_remote and original_url in map_remote:
        return map_remote[original_url].get("processed")
    # fallback to local
    map_local = load_processed_map_local()
    if map_local and original_url in map_local:
        return map_local[original_url].get("processed")
    # need to process
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set; cannot commit processed image automatically.")
    bts = download_bytes(original_url)
    jb = process_to_jpeg_bytes(bts)
    parsed = urllib.parse.urlparse(original_url)
    base = os.path.basename(parsed.path) or "img"
    name = _slugify(base)
    h = hashlib.sha256(jb).hexdigest()[:10]
    final_name = f"{h}-{name}"
    target_repo_path = f"{PROCESSED_DIR}/{final_name}"
    raw_url = make_raw_url(target_repo_path, branch=PROCESSED_BRANCH)
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
    newmap = load_processed_map_remote(branch=PROCESSED_BRANCH) or load_processed_map_local() or {}
    newmap[original_url] = entry
    commit_processed_image_and_map(jb, target_repo_path, newmap)
    return raw_url

# -------------------------
# Instagram Graph helpers and poller
# -------------------------
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

def is_media_ready(creation_id):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{creation_id}"
    params = {"fields": "status_code", "access_token": IG_ACCESS_TOKEN}
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return False
        j = r.json()
        sc = None
        if isinstance(j, dict):
            sc = j.get("status_code") or j.get("status") or None
        if isinstance(sc, str) and sc.upper() == "FINISHED":
            return True
        if sc in ("ready","complete"):
            return True
        return False
    except Exception:
        return False

def wait_for_media_ready(creation_id, timeout=120, poll_interval=2):
    waited = 0
    while waited < timeout:
        if is_media_ready(creation_id):
            return True
        time.sleep(poll_interval)
        waited += poll_interval
        if poll_interval < 8:
            poll_interval = min(poll_interval + 1, 8)
    return False

# -------------------------
# Hashtag generation
# -------------------------
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

# -------------------------
# Main
# -------------------------
def main():
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("ERROR: IG_USER_ID or IG_ACCESS_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set (required to commit processed images).", file=sys.stderr)
        sys.exit(2)
    print("IG_USER_ID:", IG_USER_ID)
    print("Processing branch (source):", GITHUB_BRANCH, "Processed branch:", PROCESSED_BRANCH)

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

    child_ids_ready = []
    for u in images:
        try:
            purl = ensure_processed_url_for(u)
            print("USING PROCESSED URL:", purl)
            # create child container
            resp = create_image_container(purl, is_carousel_item=True)
            print("CREATE child returned", resp.status_code, "->", resp.text)
            if resp.status_code not in (200,201):
                print("create_image_container failed:", resp.status_code, resp.text, file=sys.stderr)
                sys.exit(1)
            cid = resp.json().get("id")
            if not cid:
                print("No child id returned in response:", resp.text, file=sys.stderr)
                sys.exit(1)
            # wait for readiness
            ready = wait_for_media_ready(cid, timeout=120, poll_interval=2)
            if not ready:
                print(f"Child media {cid} did not become ready in time; aborting.", file=sys.stderr)
                sys.exit(1)
            print(f"Child media {cid} is ready.")
            child_ids_ready.append(cid)
        except Exception as e:
            print("ERROR preparing image:", u, e, file=sys.stderr)
            sys.exit(1)

    # compose caption and hashtags
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

    parent_resp = create_parent_container(child_ids_ready, caption=caption)
    print("Parent create response:", parent_resp.status_code, parent_resp.text)
    if parent_resp.status_code not in (200,201):
        print("Parent creation failed:", parent_resp.status_code, parent_resp.text, file=sys.stderr)
        sys.exit(1)
    parent_id = parent_resp.json().get("id")
    if not parent_id:
        print("No parent creation id returned:", parent_resp.text, file=sys.stderr)
        sys.exit(1)
    pub_resp = publish_parent_container(parent_id)
    print("Publish response:", pub_resp.status_code, pub_resp.text)
    if pub_resp.status_code not in (200,201):
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
