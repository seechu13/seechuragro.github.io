#!/usr/bin/env python3
"""
Robust IG poster (debug-friendly).
Uses IG_USER_ID and IG_ACCESS_TOKEN (or FB_PAGE_ACCESS_TOKEN fallback).
Creates single-image posts or a carousel (up to 4 images).
Prints full Graph API responses on error for diagnosis.
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
HEAD_BACKOFF = [2, 4, 8, 12]
CREATE_RETRIES = 3
CREATE_BACKOFF = [2, 4, 8]

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

def head_check_with_retries(url):
    for attempt in range(HEAD_RETRIES):
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            status = r.status_code
            if status < 400:
                size = None
                cl = r.headers.get("Content-Length")
                if cl:
                    try:
                        size = int(cl)
                    except:
                        size = None
                return True, size
            else:
                print(f"HEAD returned {status} for {url} (attempt {attempt+1}/{HEAD_RETRIES})")
        except Exception as e:
            print(f"HEAD error for {url}: {e} (attempt {attempt+1}/{HEAD_RETRIES})")
        time.sleep(HEAD_BACKOFF[min(attempt, len(HEAD_BACKOFF)-1)])
    return False, None

def create_image_container(image_url, is_carousel_item=False, caption=None):
    endpoint = f"{GRAPH}/{IG_USER_ID}/media"
    params = {"image_url": image_url, "access_token": IG_ACCESS_TOKEN}
    if is_carousel_item:
        params["is_carousel_item"] = "true"
    if caption and not is_carousel_item:
        params["caption"] = caption
    last_exc = None
    for attempt in range(CREATE_RETRIES):
        try:
            r = requests.post(endpoint, data=params, timeout=60)
            if r.status_code >= 400:
                print(f"CREATE container returned {r.status_code} -> {r.text}")
                # raise to trigger retry branch
                r.raise_for_status()
            data = r.json()
            return data.get("id")
        except Exception as e:
            last_exc = e
            print(f"create_image_container attempt {attempt+1} failed: {e}")
            # If we got a response body, print it for debug
            try:
                print("Response content:", r.text)
            except:
                pass
            time.sleep(CREATE_BACKOFF[min(attempt, len(CREATE_BACKOFF)-1)])
    raise RuntimeError(f"Failed to create image container for {image_url}: {last_exc}")

def publish_container(creation_id):
    endpoint = f"{GRAPH}/{IG_USER_ID}/media_publish"
    params = {"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN}
    for attempt in range(CREATE_RETRIES):
        try:
            r = requests.post(endpoint, data=params, timeout=60)
            if r.status_code >= 400:
                print(f"PUBLISH returned {r.status_code} -> {r.text}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"publish_container attempt {attempt+1} failed: {e}")
            try:
                print("Response content:", r.text)
            except:
                pass
            time.sleep(CREATE_BACKOFF[min(attempt, len(CREATE_BACKOFF)-1)])
    raise RuntimeError(f"Failed to publish creation_id {creation_id}")

def build_message(j):
    title = j.get("title","")
    excerpt = j.get("excerpt") or j.get("summary","")
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
            die("No images found; IG API requires media for this flow.")

        images = images[:MAX_IMAGES]
        print("Posting to IG with images:", images)

        # For single-image post:
        if len(images) == 1:
            img = images[0]
            ok, size = head_check_with_retries(img)
            if not ok:
                die(f"Image not available for upload: {img}")
            creation_id = create_image_container(img, is_carousel_item=False, caption=caption)
            print("Created single image container:", creation_id)
            pub = publish_container(creation_id)
            print("Published IG post:", pub)
            return

        # For carousel:
        child_ids = []
        for u in images:
            ok, size = head_check_with_retries(u)
            if not ok:
                die(f"Image not available for upload: {u}")
            print("Creating child container for:", u)
            cid = create_image_container(u, is_carousel_item=True)
            print("Created child container id:", cid)
            child_ids.append(cid)

        children_csv = ",".join(child_ids)
        endpoint = f"{GRAPH}/{IG_USER_ID}/media"
        params = {"media_type": "CAROUSEL", "children": children_csv, "caption": caption, "access_token": IG_ACCESS_TOKEN}
        print("Creating parent carousel with children:", children_csv)
        r = requests.post(endpoint, data=params, timeout=60)
        print("Parent create response:", r.status_code, r.text)
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
