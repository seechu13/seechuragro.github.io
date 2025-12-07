#!/usr/bin/env python3
"""
Unified FB/IG publisher.
Modes:
    --mode fb
    --mode ig

Usage examples:
    python scripts/publish_fb_insta.py path/to/article.json --mode fb
    python scripts/publish_fb_insta.py path/to/article.json --mode ig
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from urllib.parse import urljoin
import requests

# -------- ENVIRONMENT --------
FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
IG_USER_ID = os.getenv("IG_USER_ID")
SITE_URL_BASE = os.getenv("SITE_URL_BASE", "").rstrip("/")
ASSETS_PATH = os.getenv("ASSETS_PATH", "").strip("/")

GRAPH_VER = "v16.0"
FB_PHOTO_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{page_id}}/photos"
FB_FEED_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{page_id}}/feed"
IG_MEDIA_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{ig_user_id}}/media"
IG_PUBLISH_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{ig_user_id}}/media_publish"

TIMEOUT = 30


# -------- UTILS --------
def load_json(path):
    p = Path(path)
    if not p.exists():
        print(f"JSON not found: {path}")
        sys.exit(2)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_image(article):
    for key in ("cover_image", "image", "featured_image", "hero"):
        if article.get(key):
            return article[key]
    return None


def is_public_url(v):
    return isinstance(v, str) and (v.startswith("http://") or v.startswith("https://"))


def build_public_url(val):
    if not SITE_URL_BASE:
        return None
    v = val.lstrip("/")
    # if val already starts with assets path
    if ASSETS_PATH and v.startswith(ASSETS_PATH):
        return f"{SITE_URL_BASE}/{v}"
    # if val begins with assets/
    if v.startswith("assets/"):
        return f"{SITE_URL_BASE}/{v}"
    # fallback to putting under ASSETS_PATH
    if ASSETS_PATH:
        return f"{SITE_URL_BASE}/{ASSETS_PATH}/{Path(v).name}"
    return f"{SITE_URL_BASE}/{v}"


def public_reachable(url, retries, interval):
    for i in range(retries):
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(interval)
    return False


# -------- FACEBOOK --------
def fb_upload(page_id, token, img, caption):
    url = FB_PHOTO_URL.format(page_id=page_id)
    if is_public_url(img):
        data = {"url": img, "caption": caption, "access_token": token}
        r = requests.post(url, data=data, timeout=TIMEOUT)
    else:
        with open(img, "rb") as fp:
            files = {"source": fp}
            data = {"caption": caption, "access_token": token}
            r = requests.post(url, data=data, files=files, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fb_feed_with_media(page_id, token, media_id, msg):
    url = FB_FEED_URL.format(page_id=page_id)
    payload = {
        "message": msg,
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": token
    }
    r = requests.post(url, data=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fb_feed_text(page_id, token, msg):
    url = FB_FEED_URL.format(page_id=page_id)
    r = requests.post(url, data={"message": msg, "access_token": token}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# -------- INSTAGRAM --------
def ig_publish(ig_user, token, image_url, caption):
    create = IG_MEDIA_URL.format(ig_user_id=ig_user)
    publish = IG_PUBLISH_URL.format(ig_user_id=ig_user)

    r = requests.post(create, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": token
    }, timeout=TIMEOUT)
    r.raise_for_status()
    container = r.json()
    cid = container.get("id")
    if not cid:
        raise RuntimeError("No IG container id")

    r2 = requests.post(publish, data={
        "creation_id": cid,
        "access_token": token
    }, timeout=TIMEOUT)
    r2.raise_for_status()
    return r2.json()


# -------- MAIN --------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonfile")
    parser.add_argument("--mode", required=True, choices=["fb", "ig"])
    parser.add_argument("--max-retries", type=int, default=6)
    parser.add_argument("--retry-interval", type=int, default=5)
    args = parser.parse_args()

    article = load_json(args.jsonfile)

    title = article.get("title") or article.get("slug") or "New Article"
    excerpt = article.get("excerpt") or article.get("summary") or ""
    url = article.get("url") or ""
    caption = f"{title}\n\n{excerpt}\n\nRead more: {url}"

    imgval = find_image(article)
    public_img = None
    local_img = None

    if imgval:
        if is_public_url(imgval):
            public_img = imgval
        else:
            maybe = build_public_url(imgval)
            if maybe:
                public_img = maybe

            p = Path(imgval.lstrip("/"))
            if p.exists():
                local_img = str(p)
            elif ASSETS_PATH:
                cand = Path(ASSETS_PATH) / Path(imgval).name
                if cand.exists():
                    local_img = str(cand)

    # ----- FB -----
    if args.mode == "fb":
        if not FB_PAGE_TOKEN or not FB_PAGE_ID:
            print("FB_PAGE_TOKEN or FB_PAGE_ID missing")
            sys.exit(1)

        try:
            if local_img:
                print("[FB] Uploading local:", local_img)
                resp = fb_upload(FB_PAGE_ID, FB_PAGE_TOKEN, local_img, caption)
                mid = resp.get("id")
                if mid:
                    fb_feed_with_media(FB_PAGE_ID, FB_PAGE_TOKEN, mid, caption)
                else:
                    fb_feed_text(FB_PAGE_ID, FB_PAGE_TOKEN, caption)
            elif public_img:
                print("[FB] Uploading URL:", public_img)
                resp = fb_upload(FB_PAGE_ID, FB_PAGE_TOKEN, public_img, caption)
                mid = resp.get("id")
                if mid:
                    fb_feed_with_media(FB_PAGE_ID, FB_PAGE_TOKEN, mid, caption)
                else:
                    fb_feed_text(FB_PAGE_ID, FB_PAGE_TOKEN, caption)
            else:
                print("[FB] No image → text-only")
                fb_feed_text(FB_PAGE_ID, FB_PAGE_TOKEN, caption)
        except Exception as e:
            print("[FB] Error:", e)
            sys.exit(5)

        print("[FB] Done")
        return

    # ----- IG -----
    if args.mode == "ig":
        if not IG_USER_ID:
            print("IG_USER_ID missing")
            sys.exit(2)

        if not public_img:
            print("[IG] No public image URL → cannot post")
            sys.exit(3)

        print(f"[IG] Checking {public_img}")
        if not public_reachable(public_img, args.max_retries, args.retry_interval):
            print("[IG] Public image not reachable")
            sys.exit(4)

        try:
            resp = ig_publish(IG_USER_ID, FB_PAGE_TOKEN, public_img, caption)
            print("[IG] Done:", resp)
        except Exception as e:
            print("[IG] Error:", e)
            sys.exit(5)
