#!/usr/bin/env python3
"""
send_fb.py

Usage:
    python send_fb.py <article-json-path>

Features:
- Generates hashtags (from title + excerpt) and appends them (if any) to the caption.
- Safe if there are no hashtags (won't append empty lines).
- Configurable via env:
    FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN, BASE_URL
    HASHTAG_MAX (default 30)
    HASHTAG_MIN_WORD_LEN (default 3)
    EXTRA_HASHTAGS (comma separated, no #)
    PREVIEW_ONLY ('true' to print caption and exit without posting)
- Uploads up to 4 images (existing flow preserved). Compresses/ converts as needed to JPEG for FB upload.
"""
import os
import sys
import json
import re
import traceback
from urllib.parse import urljoin
import requests
import tempfile
from io import BytesIO

# Pillow import - optional until runtime
try:
    from PIL import Image
except Exception:
    Image = None

# Try to import helper that your repo already has (if exists).
# If not, fallback to local simple extractor.
try:
    from common_utils import extract_images_from_json
except Exception:
    def extract_images_from_json(j, base_url=""):
        # Basic fallback: look for "cover_image" and "images" keys
        imgs = []
        if isinstance(j.get("cover_image"), str):
            imgs.append(j["cover_image"])
        if isinstance(j.get("images"), list):
            for it in j.get("images", []):
                if isinstance(it, str):
                    imgs.append(it)
                elif isinstance(it, dict) and it.get("url"):
                    imgs.append(it["url"])
        # If slug/path but not full, ignore - calling code uses BASE_URL to join if needed elsewhere
        out = []
        for u in imgs:
            if u and isinstance(u, str):
                out.append(u)
        return out

# ----------------- Config / Environment ----------------- #
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
FB_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "").strip()
BASE_URL = os.environ.get("BASE_URL", "").strip()
GRAPH = os.environ.get("FB_GRAPH_API", "https://graph.facebook.com/v24.0")
MAX_BYTES = int(os.environ.get("FB_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))  # 10MB default

# Hashtag config
HASHTAG_MAX = int(os.environ.get("HASHTAG_MAX", "30"))         # MAX hashtags appended (set high)
HASHTAG_MIN_WORD_LEN = int(os.environ.get("HASHTAG_MIN_WORD_LEN", "3"))
EXTRA_HASHTAGS = os.environ.get("EXTRA_HASHTAGS", "")          # comma-separated extras (no #)
PREVIEW_ONLY = str(os.environ.get("PREVIEW_ONLY", "false")).lower() in ("1", "true", "yes")

# Small stopword list (not exhaustive)
COMMON_STOPWORDS = {
    "the","and","for","that","with","this","from","have","are","was","were","will",
    "but","not","you","your","our","who","what","when","where","how","why","which",
    "their","they","them","been","had","has","about","into","over","through","also",
    "more","other","these","those","there","such","may","can","its","it's","a","an","in","on","of","to","by","as"
}

# ----------------- Utility / Safety ----------------- #
def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)

def safe_filename_suffix(name):
    return re.sub(r"[^a-z0-9_.-]", "_", name, flags=re.I)

# ----------------- Hashtag generation ----------------- #
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

# ----------------- Image helpers ----------------- #
def check_url_head(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        size = None
        if r.status_code < 400:
            size = r.headers.get("Content-Length")
            if size:
                try:
                    size = int(size)
                except:
                    size = None
        return (r.status_code < 400, size)
    except:
        return (False, None)

def download_image_to_bytes(url):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    buf = BytesIO()
    for chunk in r.iter_content(8192):
        buf.write(chunk)
    return buf.getvalue()

def compress_image_bytes_to_file(img_bytes, out_path, max_bytes=MAX_BYTES):
    if Image is None:
        # If Pillow not available, write raw bytes and hope they are OK
        with open(out_path, "wb") as f:
            f.write(img_bytes)
        return out_path

    im = Image.open(BytesIO(img_bytes))
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGB")

    quality = 85
    width, height = im.size

    for attempt in range(12):
        buf = BytesIO()
        try:
            im.save(buf, format="JPEG", quality=quality, optimize=True)
        except Exception:
            im.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= max_bytes or (quality <= 30 and (width < 400 or height < 400)):
            with open(out_path, "wb") as f:
                f.write(data)
            return out_path
        if quality > 30:
            quality -= 10
        else:
            width = int(width * 0.85)
            height = int(height * 0.85)
            im = im.resize((max(1, width), max(1, height)), Image.LANCZOS)
            quality = max(30, quality - 5)

    # last resort
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=30)
    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
    return out_path

def prepare_image_for_upload(image_url):
    ok, size = check_url_head(image_url)
    # If HEAD fails, download; if size small, use url; if too big compress
    if not ok:
        b = download_image_to_bytes(image_url)
        if len(b) <= MAX_BYTES:
            return ("url", image_url, None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        return ("file", None, compress_image_bytes_to_file(b, tmp.name, MAX_BYTES))
    else:
        if size and size <= MAX_BYTES:
            return ("url", image_url, None)
        b = download_image_to_bytes(image_url)
        if len(b) <= MAX_BYTES:
            return ("url", image_url, None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        return ("file", None, compress_image_bytes_to_file(b, tmp.name, MAX_BYTES))

def cleanup_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass

# ----------------- Facebook API helpers ----------------- #
def upload_photo_unpublished_by_url(page_id, token, image_url, graph=GRAPH):
    url = f"{graph}/{page_id}/photos"
    params = {"url": image_url, "published": "false", "access_token": token}
    r = requests.post(url, data=params, timeout=60)
    r.raise_for_status()
    return r.json().get("id")

def upload_photo_unpublished_by_file(page_id, token, filepath, graph=GRAPH):
    url = f"{graph}/{page_id}/photos"
    with open(filepath, "rb") as fh:
        files = {"source": fh}
        data = {"published": "false", "access_token": token}
        r = requests.post(url, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json().get("id")

def post_feed(page_id, token, message, attached_media_ids=None, link=None, graph=GRAPH):
    url = f"{graph}/{page_id}/feed"
    data = {"message": message, "access_token": token}
    if attached_media_ids:
        attached = [{"media_fbid": mid} for mid in attached_media_ids]
        data["attached_media"] = json.dumps(attached)
    elif link:
        data["link"] = link
    r = requests.post(url, data=data, timeout=60)
    r.raise_for_status()
    return r.json()

# ----------------- Build caption ----------------- #
def build_message(j):
    title = j.get("title", "") or ""
    excerpt = j.get("excerpt") or j.get("summary") or ""
    if j.get("url") and isinstance(j["url"], str) and j["url"].startswith("http"):
        full_url = j["url"]
    else:
        slug = j.get("slug") or j.get("path") or ""
        if isinstance(slug, str) and slug.startswith("http"):
            full_url = slug
        else:
            full_url = urljoin(BASE_URL, str(slug))
    text = f"{title}".strip()
    if excerpt:
        text += f"\n\n{excerpt.strip()}"
    if full_url:
        text += f"\n\nRead more: {full_url}"
    return text, full_url, title, excerpt

# ----------------- Main ----------------- #
def main(path):
    try:
        if not FB_PAGE_ID or not FB_TOKEN:
            die("Missing FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN in environment variables.")

        if not os.path.exists(path):
            die(f"Article JSON not found: {path}")

        j = json.load(open(path, "r", encoding="utf-8"))

        message, link, title, excerpt = build_message(j)
        images = extract_images_from_json(j, base_url=BASE_URL)

        # Generate hashtags
        tags = generate_hashtags(title, excerpt, max_tags=HASHTAG_MAX)
        hashtags_line = ""
        if tags:
            hashtags_line = "\n\n" + " ".join(tags)

        # Compose full message (only append hashtags if present)
        full_message = message + hashtags_line if hashtags_line else message

        # PREVIEW: print caption and exit if PREVIEW_ONLY
        if PREVIEW_ONLY:
            print("---- FB Caption PREVIEW ----")
            print(full_message)
            print("---- END PREVIEW (no post made) ----")
            print("Images (first 4):", images[:4])
            print("Hashtags count:", len(tags))
            sys.exit(0)

        attached = []
        tmp_files = []

        # Upload up to 4 images (preserve existing behavior)
        for img in images[:4]:
            try:
                prep_type, url_for_upload, file_path = prepare_image_for_upload(img)
                if prep_type == "url":
                    mid = upload_photo_unpublished_by_url(FB_PAGE_ID, FB_TOKEN, img)
                else:
                    mid = upload_photo_unpublished_by_file(FB_PAGE_ID, FB_TOKEN, file_path)
                    tmp_files.append(file_path)
                attached.append(mid)
            except Exception as e:
                print("Image upload failed for", img, ":", e)

        resp = post_feed(FB_PAGE_ID, FB_TOKEN, full_message, attached_media_ids=attached, link=None)
        print("Posted to FB successfully:", resp)

    except Exception:
        print("Exception in send_fb.py:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        for f in locals().get("tmp_files", []) or []:
            cleanup_file(f)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: send_fb.py <json-file>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
