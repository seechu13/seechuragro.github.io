#!/usr/bin/env python3
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import json
import traceback
from urllib.parse import urljoin
import requests
import tempfile
from PIL import Image
from io import BytesIO
from common_utils import extract_images_from_json

FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")
BASE_URL = os.environ.get("BASE_URL", "")

GRAPH = "https://graph.facebook.com/v24.0"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


# ----------------- MEDIA UPLOAD FUNCTIONS ----------------- #

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


# ----------------- FEED POST FUNCTION ----------------- #

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


# ----------------- BUILD MESSAGE (WITH FIXED URL LOGIC) ----------------- #

def build_message(j):
    title = j.get("title", "")
    excerpt = j.get("excerpt") or j.get("summary", "")

    # NEW LOGIC — ALWAYS USE "url" IF PRESENT
    if j.get("url") and isinstance(j["url"], str) and j["url"].startswith("http"):
        full_url = j["url"]
    else:
        slug = j.get("slug") or j.get("path") or ""
        if isinstance(slug, str) and slug.startswith("http"):
            full_url = slug
        else:
            full_url = urljoin(BASE_URL, str(slug))

    text = f"{title}\n\n{excerpt}\n\nRead more: {full_url}"
    return text, full_url


# ----------------- IMAGE CHECK + PREP ----------------- #

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
        try:
            b = download_image_to_bytes(image_url)
        except Exception as e:
            raise RuntimeError(f"Failed to download image: {e}")

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


# ----------------- MAIN ----------------- #

def main(path):
    try:
        if not FB_PAGE_ID or not FB_TOKEN:
            die("Missing FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN in env")

        j = json.load(open(path, "r", encoding="utf-8"))

        message, link = build_message(j)
        images = extract_images_from_json(j, base_url=BASE_URL)

        attached = []
        tmp_files = []

        for img in images[:2]:
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
