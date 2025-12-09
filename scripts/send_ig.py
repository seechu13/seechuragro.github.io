#!/usr/bin/env python3
import os
import sys

# Ensure the scripts/ directory is on Python path so imports like
# `from common_utils import ...` work when running `python3 scripts/send_ig.py`
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import json
import time
import traceback
from urllib.parse import urljoin
import requests

from common_utils import extract_images_from_json

IG_USER_ID = os.environ.get("IG_USER_ID")
IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
BASE_URL = os.environ.get("BASE_URL", "")

GRAPH = "https://graph.facebook.com/v17.0"

def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)

def create_container(image_url, caption):
    url = f"{GRAPH}/{IG_USER_ID}/media"
    params = {"image_url": image_url, "caption": caption, "access_token": IG_TOKEN}
    r = requests.post(url, data=params, timeout=30)
    r.raise_for_status()
    return r.json().get("id")

def publish_container(container_id):
    url = f"{GRAPH}/{IG_USER_ID}/media_publish"
    params = {"creation_id": container_id, "access_token": IG_TOKEN}
    r = requests.post(url, data=params, timeout=30)
    r.raise_for_status()
    return r.json()

def build_message(j):
    title = j.get("title", "")
    excerpt = j.get("excerpt") or j.get("summary", "")
    slug = j.get("slug") or j.get("path") or ""
    url = slug if isinstance(slug, str) and slug.startswith("http") else urljoin(BASE_URL, str(slug))
    text = f"{title}\n\n{excerpt}\n\nRead more: {url}"
    return text, url

def check_url_head(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        return r.status_code < 400
    except Exception:
        return False

def main(path):
    try:
        if not IG_USER_ID or not IG_TOKEN:
            die("Missing IG_USER_ID or IG_ACCESS_TOKEN in env")

        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)

        caption, link = build_message(j)
        images = extract_images_from_json(j, base_url=BASE_URL)

        if not images:
            print("No images found in JSON; IG requires an image. Skipping.")
            return

        image_url = images[0]
        print("Checking image URL reachability:", image_url)
        if not check_url_head(image_url):
            print("Warning: image URL did not respond to HEAD request. Will still attempt upload but this might fail.")

        print("Creating IG media container for:", image_url)
        container = create_container(image_url, caption)
        print("Container id:", container)
        time.sleep(3)
        resp = publish_container(container)
        print("Published to IG:", resp)

    except Exception:
        print("Exception in send_ig.py:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: send_ig.py <json-file>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
