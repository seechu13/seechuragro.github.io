#!/usr/bin/env python3
import os
import sys

# Ensure the scripts/ directory is on Python path so imports like
# `from common_utils import ...` work when running `python3 scripts/send_fb.py`
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import json
import traceback
from urllib.parse import urljoin
import requests
import tempfile
import shutil
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

def post_photo_by_url(image_url, caption=""):
    """Use the Graph API url= param (fast)"""
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    params = {"url": image_url, "caption": caption, "access_token": FB_TOKEN}
    r = requests.post(url, data=params, timeout=60)
    r.raise_for_status()
    return r.json().get("id")

def post_photo_by_file(filepath, caption=""):
    """Upload photo file (multipart 'source')"""
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    with open(filepath, "rb") as fh:
        files = {"source": fh}
        data = {"caption": caption, "access_token": FB_TOKEN}
        r = requests.post(url, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json().get("id")

def build_message(j):
    title = j.get("title","")
    excerpt = j.get("excerpt") or j.get("summary","")
    slug = j.get("slug") or j.get("path") or ""
    url = slug if isinstance(slug, str) and slug.startswith("http") else urljoin(BASE_URL, str(slug))
    text = f"{title}\n\n{excerpt}\n\nRead more: {url}"
    return text, url

def check_url_head(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        # Try to get Content-Length if available
        size = None
        if r.status_code < 400:
            size = r.headers.get("Content-Length")
            if size is not None:
                try:
                    size = int(size)
                except Exception:
                    size = None
        return (r.status_code < 400, size)
    except Exception:
        return (False, None)

def download_image_to_bytes(url):
    """Download image content as bytes (stream)."""
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    buf = BytesIO()
    for chunk in r.iter_content(8192):
        if chunk:
            buf.write(chunk)
            # quick guard: if massive size we still allow download but we detect later
    return buf.getvalue()

def compress_image_bytes_to_file(img_bytes, out_path, max_bytes=MAX_BYTES):
    """
    Open image bytes with Pillow, iteratively downscale / reduce quality
    until under max_bytes and write to out_path as JPEG (or original format).
    """
    try:
        im = Image.open(BytesIO(img_bytes))
    except Exception as e:
        raise RuntimeError(f"Cannot open image for compression: {e}")

    # If image has alpha channel, convert to RGB (JPEG doesn't support alpha)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGB")

    # Starting parameters
    quality = 85
    width, height = im.size
    # Try loop: reduce quality first, then shrink dimensions if needed
    for attempt in range(12):
        buf = BytesIO()
        save_kwargs = {"format": "JPEG", "quality": quality, "optimize": True}
        try:
            im.save(buf, **save_kwargs)
        except Exception:
            # fallback without optimize
            im.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= max_bytes or (quality <= 30 and (width < 400 or height < 400)):
            with open(out_path, "wb") as f:
                f.write(data)
            return out_path
        # reduce quality
        if quality > 30:
            quality -= 10
            continue
        # reduce size
        width = int(width * 0.85)
        height = int(height * 0.85)
        im = im.resize((max(1, width), max(1, height)), Image.LANCZOS)
        # reset quality for next attempt
        quality = max(30, quality - 5)

    # final save (best attempt)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=30)
    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
    return out_path

def prepare_image_for_upload(image_url):
    """
    If image URL size <= MAX_BYTES (by HEAD), return ('url', image_url).
    Otherwise download & compress and return ('file', tmp_filepath).
    """
    ok, size = check_url_head(image_url)
    if not ok:
        # HEAD failed but try download and check bytes
        try:
            b = download_image_to_bytes(image_url)
        except Exception as e:
            raise RuntimeError(f"Failed to download image for check: {e}")
        if len(b) <= MAX_BYTES:
            return ("bytes_url", image_url, None)  # still post by url
        # else compress and write
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        compress_image_bytes_to_file(b, tmp.name, max_bytes=MAX_BYTES)
        return ("file", None, tmp.name)
    else:
        # HEAD succeeded
        if size is not None and size <= MAX_BYTES:
            return ("bytes_url", image_url, None)
        # need to download & compress
        b = download_image_to_bytes(image_url)
        if len(b) <= MAX_BYTES:
            return ("bytes_url", image_url, None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        compress_image_bytes_to_file(b, tmp.name, max_bytes=MAX_BYTES)
        return ("file", None, tmp.name)

def cleanup_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def main(path):
    try:
        if not FB_PAGE_ID or not FB_TOKEN:
            die("Missing FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN in env")

        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)

        message, link = build_message(j)
        images = extract_images_from_json(j, base_url=BASE_URL)
        attached = []
        tmp_files = []

        # try up to 2 images
        for i, img in enumerate(images[:2]):
            try:
                print("Checking image url:", img)
                prep_type, url_for_upload, file_path = prepare_image_for_upload(img)
                if prep_type == "bytes_url":
                    # use direct URL param
                    print("Uploading by URL:", img)
                    pid = post_photo_by_url(img, caption=message if i == 0 else "")
                    attached.append(pid)
                elif prep_type == "file":
                    print("Uploading by file (resized):", file_path)
                    pid = post_photo_by_file(file_path, caption=message if i == 0 else "")
                    attached.append(pid)
                    tmp_files.append(file_path)
                else:
                    # fallback to URL post
                    print("Fallback: uploading by URL:", img)
                    pid = post_photo_by_url(img, caption=message if i == 0 else "")
                    attached.append(pid)
            except Exception as e:
                print("Photo upload failed for", img, ":", repr(e))

        try:
            resp = post_feed(message, attached_media_ids=attached if attached else None, link=None if attached else link)
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
