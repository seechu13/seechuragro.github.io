#!/usr/bin/env python3
"""
Minimal Instagram poster using Instagram Graph API.

- Supports single-image posts and carousel posts (up to 4 images).
- Requires public image URLs (the script will retry HEAD a few times if 404).
- Environment:
    IG_USER_ID        (required)
    IG_ACCESS_TOKEN   (required) or FB_PAGE_ACCESS_TOKEN used as fallback.
    BASE_URL          (optional) used for relative asset paths.

Usage:
    python3 scripts/ig.py path/to/post.json
"""
import os
import sys
import json
import time
import traceback
import requests
from urllib.parse import urljoin

IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN") or os.environ.get("FB_PAGE_ACCESS_TOKEN")
BASE_URL = os.environ.get("BASE_URL", "")

GRAPH = "https://graph.facebook.com/v24.0"
MAX_IMAGES = 4
HEAD_RETRIES = 4
HEAD_BACKOFF = [2, 4, 8, 16]  # seconds

def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)

def normalize_url(u):
    if not u:
        return None
    u = u.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("/"):
        return urljoin(BASE_URL.rstrip("/") + "/", u.lstrip("/"))
    return urljoin(BASE_URL.rstrip("/") + "/", u)

def check_url_with_retries(url):
    for attempt in range(HEAD_RETRIES):
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            if r.status_code < 400:
                size = None
                size_h = r.headers.get("Content-Length")
                if size_h:
                    try:
                        size = int(size_h)
                    except:
                        size = None
                return True, size
            else:
                print(f"HEAD returned {r.status_code} for {url}; retrying...")
        except Exception as e:
            print(f"HEAD error for {url}: {e}; retrying...")
        # backoff
        time.sleep(HEAD_BACKOFF[min(attempt, len(HEAD_BACKOFF)-1)])
    return False, None

def create_image_container(image_url, is_carousel_item=False, caption=None):
    """
    Create a media container for an image.
    For carousel children set is_carousel_item=true.
    Returns creation_id (string).
    """
    endpoint = f"{GRAPH}/{IG_USER_ID}/media"
    params = {"image_url": image_url, "access_token": IG_ACCESS_TOKEN}
    if is_carousel_item:
        params["is_carousel_item"] = "true"
    if caption and not is_carousel_item:
        params["caption"] = caption
    r = requests.post(endpoint, data=params, timeout=60)
    r.raise_for_status()
    return r.json().get("id")  # creation_id

def publish_container(creation_id):
    endpoint = f"{GRAPH}/{IG_USER_ID}/media_publish"
    params = {"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN}
    r = requests.post(endpoint, data=params, timeout=60)
    r.raise_for_status()
    return r.json()

def build_message(j):
    title = j.get("title","")
    excerpt = j.get("excerpt") or j.get("summary","")
    # prefer explicit url
    if j.get("url") and isinstance(j["url"], str) and j["url"].startswith("http"):
        full_url = j["url"]
    else:
        slug = j.get("slug") or j.get("path") or ""
        if isinstance(slug, str) and slug.startswith("http"):
            full_url = slug
        else:
            full_url = urljoin(BASE_URL, str(slug))
    caption = f"{title}\n\n{excerpt}\n\nRead more: {full_url}"
    return caption

def extract_images_from_json_local(j):
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
    return [normalize_url(u) for u in imgs if normalize_url(u)]

def main(path):
    try:
        if not IG_USER_ID or not IG_ACCESS_TOKEN:
            die("Missing IG_USER_ID or IG_ACCESS_TOKEN in environment")

        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)

        caption = build_message(j)
        images = extract_images_from_json_local(j)
        if not images:
            print("No images found — creating caption-only IG post (single media container with no image is not allowed).")
            # Instagram requires media_url; in this case we cannot publish text-only posts via API.
            die("Instagram API requires image/video for publishing via API in this flow.")
        # cap to MAX_IMAGES
        images = images[:MAX_IMAGES]
        print("Posting to IG with images:", images)

        # For single image: create container with image_url + caption, publish
        if len(images) == 1:
            img = images[0]
            ok, size = check_url_with_retries(img)
            if not ok:
                die(f"Image not available for upload: {img}")
            creation_id = create_image_container(img, is_carousel_item=False, caption=caption)
            print("Created single image container:", creation_id)
            pub = publish_container(creation_id)
            print("Published IG post:", pub)
            return

        # For carousel: create child containers first (is_carousel_item=true)
        child_ids = []
        for u in images:
            ok, size = check_url_with_retries(u)
            if not ok:
                die(f"Image not available for upload: {u}")
            cid = create_image_container(u, is_carousel_item=True)
            print("Created child container:", cid)
            child_ids.append(cid)

        # create parent carousel container with children list and caption
        children_csv = ",".join(child_ids)
        endpoint = f"{GRAPH}/{IG_USER_ID}/media"
        params = {"media_type": "CAROUSEL", "children": children_csv, "caption": caption, "access_token": IG_ACCESS_TOKEN}
        r = requests.post(endpoint, data=params, timeout=60)
        r.raise_for_status()
        parent_creation_id = r.json().get("id")
        print("Created parent carousel container:", parent_creation_id)

        pub = publish_container(parent_creation_id)
        print("Published IG carousel:", pub)

    except Exception:
        print("Exception in ig.py:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ig.py <json-file>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
