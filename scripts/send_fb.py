#!/usr/bin/env python3
import os, sys, json, requests
from urllib.parse import urljoin

FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")
BASE_URL = os.environ.get("BASE_URL", "")

if not FB_PAGE_ID or not FB_TOKEN:
    print("Missing FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN in env", file=sys.stderr)
    sys.exit(1)

GRAPH = "https://graph.facebook.com/v17.0"

def post_photo(image_url, caption=""):
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    params = {"url": image_url, "caption": caption, "access_token": FB_TOKEN}
    r = requests.post(url, data=params, timeout=30)
    r.raise_for_status()
    return r.json().get("id")

def post_feed(message, attached_media_ids=None, link=None):
    url = f"{GRAPH}/{FB_PAGE_ID}/feed"
    params = {"message": message, "access_token": FB_TOKEN}
    if attached_media_ids:
        media_list = [{"media_fbid": mid} for mid in attached_media_ids]
        params["attached_media"] = json.dumps(media_list)
    if link:
        params["link"] = link
    r = requests.post(url, data=params, timeout=30)
    r.raise_for_status()
    return r.json()

def build_message(j):
    title = j.get("title","")
    excerpt = j.get("excerpt") or j.get("summary","")
    slug = j.get("slug") or j.get("path") or ""
    url = urljoin(BASE_URL, slug)
    text = f"{title}\n\n{excerpt}\n\nRead more: {url}"
    return text, url

def main(path):
    with open(path, "r", encoding="utf-8") as f:
        j = json.load(f)

    message, link = build_message(j)
    images = j.get("images") or j.get("media") or []
    attached = []
    for i, img in enumerate(images[:2]):
        try:
            print("Uploading photo:", img)
            pid = post_photo(img, caption=message if i == 0 else "")
            attached.append(pid)
        except Exception as e:
            print("Photo upload failed:", e)

    try:
        resp = post_feed(message, attached_media_ids=attached if attached else None, link=None if attached else link)
        print("Posted to FB:", resp)
    except Exception as e:
        print("Failed to post feed:", e)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: send_fb.py <json-file>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
