#!/usr/bin/env python3
# send_fb.py — minimal change from your original: only adds hashtags appended to message
import os
import sys
import json
import traceback
from urllib.parse import urljoin
import requests
import tempfile
from PIL import Image
from io import BytesIO

# try to import your repo helper (unchanged)
try:
    from common_utils import extract_images_from_json
except Exception:
    # fallback basic extractor (keeps original behavior if common_utils exists)
    def extract_images_from_json(j, base_url=""):
        imgs = []
        if isinstance(j.get("images"), list) and j.get("images"):
            imgs = j.get("images")
        elif j.get("cover_image") is not None:
            ci = j.get("cover_image")
            if isinstance(ci, list):
                imgs = ci
            elif isinstance(ci, str) and ci.strip():
                imgs = [ci]
        elif isinstance(j.get("media"), list) and j.get("media"):
            imgs = j.get("media")
        def normalize(u):
            if not u: return None
            u = u.strip()
            if u.startswith("http"):
                return u
            if u.startswith("/"):
                return urljoin(base_url.rstrip("/") + "/", u.lstrip("/"))
            return urljoin(base_url.rstrip("/") + "/", u)
        return [normalize(u) for u in imgs if normalize(u)]

# --- env / config (keep same names as original) ---
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")
BASE_URL = os.environ.get("BASE_URL", "")
GRAPH = os.environ.get("FB_GRAPH_API", "https://graph.facebook.com/v24.0")
MAX_BYTES = int(os.environ.get("FB_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))  # 10MB

# Hashtag config (new, minimal)
HASHTAG_MAX = int(os.environ.get("HASHTAG_MAX", "30"))         # default max hashtags appended
HASHTAG_MIN_WORD_LEN = int(os.environ.get("HASHTAG_MIN_WORD_LEN", "3"))
EXTRA_HASHTAGS = os.environ.get("EXTRA_HASHTAGS", "")          # optional comma-separated extras

def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)

# ----------------- MEDIA UPLOAD FUNCTIONS (unchanged) ----------------- #
def upload_photo_unpublished_by_url(image_url):
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    params = {"url": image_url, "published": "false", "access_token": FB_TOKEN}
    r = requests.post(url, data=params, timeout=60)
    r.raise_for_status()
    return r.json().get("id")

def upload_photo_unpublished_by_file(filepath):
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    with open(filepath, "rb") as fh:
        files = {"source": fh}
        data = {"published": "false", "access_token": FB_TOKEN}
        r = requests.post(url, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json().get("id")

# ----------------- FEED POST FUNCTION (unchanged) ----------------- #
def post_feed(message, attached_media_ids=None, link=None):
    url = f"{GRAPH}/{FB_PAGE_ID}/feed"
    data = {"message": message, "access_token": FB_TOKEN}
    if attached_media_ids:
        attached = [{"media_fbid": mid} for mid in attached_media_ids]
        data["attached_media"] = json.dumps(attached)
    elif link:
        data["link"] = link
    r = requests.post(url, data=data, timeout=60)
    r.raise_for_status()
    return r.json()

# ----------------- BUILD MESSAGE (unchanged except returns title/excerpt) ----------------- #
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
    text = f"{title}\n\n{excerpt}\n\nRead more: {full_url}"
    return text, full_url, title, excerpt

# ----------------- HASHTAG GENERATOR (NEW, minimal) ----------------- #
COMMON_STOPWORDS = {
    "the","and","for","that","with","this","from","have","are","was","were","will",
    "but","not","you","your","our","who","what","when","where","how","why","which",
    "their","they","them","been","had","has","about","into","over","through","also",
    "more","other","these","those","there","such","may","can","its","it's","a","an","in","on","of","to","by","as"
}

import re
def make_candidate_tokens(text):
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens = [t for t in tokens if len(t) >= HASHTAG_MIN_WORD_LEN]
    return tokens

def generate_hashtags(title, excerpt, max_tags=HASHTAG_MAX):
    # prefer title tokens first
    seq = make_candidate_tokens(title) + make_candidate_tokens(excerpt)
    seen = set()
    tags = []
    for t in seq:
        if t in COMMON_STOPWORDS: continue
        if t.isdigit(): continue
        if t in seen: continue
        seen.add(t)
        tags.append("#" + t)
        if len(tags) >= max_tags:
            break
    if EXTRA_HASHTAGS:
        for e in [x.strip().lower() for x in EXTRA_HASHTAGS.split(",") if x.strip()]:
            e_clean = re.sub(r"[^a-z0-9]", "", e)
            if not e_clean or e_clean in seen: continue
            tags.append("#" + e_clean)
            seen.add(e_clean)
            if len(tags) >= max_tags:
                break
    return tags[:max_tags]

# ----------------- IMAGE PREP (kept same as original) ----------------- #
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
    im = Image.open(BytesIO(img_bytes))
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGB")
    quality = 85
    width, height = im.size
    for attempt in range(12):
        buf = BytesIO()
        try:
            im.save(buf, format="JPEG", quality=quality, optimize=True)
        except:
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
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=30)
    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
    return out_path

def prepare_image_for_upload(image_url):
    ok, size = check_url_head(image_url)
    if not ok:
        b = download_image_to_bytes(image_url)
        if len(b) <= MAX_BYTES:
            return ("url", image_url, None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        compress_image_bytes_to_file(b, tmp.name)
        return ("file", None, tmp.name)
    else:
        if size and size <= MAX_BYTES:
            return ("url", image_url, None)
        b = download_image_to_bytes(image_url)
        if len(b) <= MAX_BYTES:
            return ("url", image_url, None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        compress_image_bytes_to_file(b, tmp.name)
        return ("file", None, tmp.name)

def cleanup_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass

# ----------------- MAIN (only change: append hashtags if any) ----------------- #
def main(path):
    try:
        if not FB_PAGE_ID or not FB_TOKEN:
            die("Missing FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN in env")

        j = json.load(open(path, "r", encoding="utf-8"))
        message, link, title, excerpt = build_message(j)
        images = extract_images_from_json(j, base_url=BASE_URL)

        # --- NEW: generate hashtags and append if any ---
        tags = generate_hashtags(title, excerpt, max_tags=HASHTAG_MAX)
        if tags:
            message = message.rstrip() + "\n\n" + " ".join(tags)

        attached = []
        tmp_files = []

        for img in images[:4]:
            try:
                print("Checking image:", img)
                prep_type, url_for_upload, file_path = prepare_image_for_upload(img)
                if prep_type == "url":
                    mid = upload_photo_unpublished_by_url(img)
                else:
                    mid = upload_photo_unpublished_by_file(file_path)
                    tmp_files.append(file_path)
                attached.append(mid)
            except Exception as e:
                print("Image upload failed:", e)

        try:
            resp = post_feed(message, attached_media_ids=attached, link=None)
            print("Posted to FB:", resp)
        except Exception as e:
            print("Failed to post feed:", e)
            raise
        finally:
            for f in tmp_files:
                cleanup_file(f)

    except Exception:
        print("Exception in send_fb.py:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: send_fb.py <json-file>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
