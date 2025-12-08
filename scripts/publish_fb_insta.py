#!/usr/bin/env python3
"""
Verbose publisher for Facebook and Instagram — debug edition.

Usage:
  python3 scripts/publish_fb_insta.py path/to/article.json --mode fb
  python3 scripts/publish_fb_insta.py path/to/article.json --mode ig

This verbose variant logs environment presence (NOT values), prints the article JSON,
reports image selection, and prints HTTP request/response summaries.
"""

from __future__ import print_function
import os
import sys
import json
import time
import argparse
import traceback
from pathlib import Path
from urllib.parse import urljoin
import requests

# --- Config (env reading)
def env_present(name):
    return (name in os.environ) and (os.environ.get(name) not in (None, ""))

ENV_VARS = ["FB_PAGE_TOKEN", "FB_PAGE_ID", "IG_USER_ID", "SITE_URL_BASE", "ASSETS_PATH", "GITHUB_TOKEN"]

for v in ENV_VARS:
    print(f"[ENV] {v} present: {env_present(v)}")

FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
IG_USER_ID = os.getenv("IG_USER_ID")
SITE_URL_BASE = os.getenv("SITE_URL_BASE", "").rstrip("/")
ASSETS_PATH = os.getenv("ASSETS_PATH", "").strip("/")

GRAPH_VER = "v19.0"
FB_PHOTO_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{page_id}}/photos"
FB_FEED_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{page_id}}/feed"
IG_MEDIA_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{ig_user_id}}/media"
IG_PUBLISH_URL = f"https://graph.facebook.com/{GRAPH_VER}/{{ig_user_id}}/media_publish"

TIMEOUT = 30

# --- helpers
def load_json(path):
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] JSON not found: {path}")
        sys.exit(2)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def find_image(article):
    for key in ("cover_image", "image", "featured_image", "hero"):
        val = article.get(key)
        if val:
            return key, val
    return None, None

def is_public_url(val):
    return isinstance(val, str) and (val.startswith("http://") or val.startswith("https://"))

def build_public_url(val):
    if not SITE_URL_BASE:
        return None
    v = val.lstrip("/")
    if ASSETS_PATH and v.startswith(ASSETS_PATH):
        return f"{SITE_URL_BASE}/{v}"
    if v.startswith("assets/"):
        return f"{SITE_URL_BASE}/{v}"
    if ASSETS_PATH:
        return f"{SITE_URL_BASE}/{ASSETS_PATH}/{Path(v).name}"
    return f"{SITE_URL_BASE}/{v}"

def check_url_head(url):
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return r.status_code, r.headers.get("content-type", "")
    except Exception as e:
        return None, str(e)

def print_resp_summary(resp, prefix="RESP"):
    try:
        code = getattr(resp, "status_code", None)
        text = None
        try:
            text = resp.text
        except:
            text = "<no-text>"
        try:
            j = resp.json()
        except:
            j = None
        print(f"[{prefix}] status={code}")
        if j is not None:
            # avoid printing whole large objects — show keys and id if present
            print(f"[{prefix}] json keys: {list(j.keys())}")
            if "id" in j:
                print(f"[{prefix}] id: {j.get('id')}")
        else:
            print(f"[{prefix}] text (first 500 chars): {text[:500]}")
    except Exception:
        print(f"[{prefix}] (could not summarize response)")

# --- FB helpers
def fb_upload(page_id, token, img, caption):
    url = FB_PHOTO_URL.format(page_id=page_id)
    print(f"[FB] Upload endpoint: {url}")
    try:
        if is_public_url(img):
            print(f"[FB] Uploading by URL: {img}")
            payload = {"url": img, "caption": caption, "access_token": token}
            resp = requests.post(url, data=payload, timeout=TIMEOUT)
            print_resp_summary(resp, "FB_UPLOAD")
            resp.raise_for_status()
            return resp.json()
        else:
            print(f"[FB] Uploading local file: {img} (exists: {Path(img).exists()})")
            with open(img, "rb") as fp:
                files = {"source": fp}
                data = {"caption": caption, "access_token": token}
                resp = requests.post(url, data=data, files=files, timeout=TIMEOUT)
                print_resp_summary(resp, "FB_UPLOAD")
                resp.raise_for_status()
                return resp.json()
    except Exception as e:
        print("[FB] Exception during upload:", e)
        print(traceback.format_exc())
        raise

def fb_create_feed_with_media(page_id, token, media_fbid, message):
    url = FB_FEED_URL.format(page_id=page_id)
    payload = {
        "message": message,
        "attached_media[0]": json.dumps({"media_fbid": media_fbid}),
        "access_token": token
    }
    print(f"[FB] Creating feed post at {url} with media id {media_fbid}")
    try:
        r = requests.post(url, data=payload, timeout=TIMEOUT)
        print_resp_summary(r, "FB_FEED")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("[FB] Exception creating feed:", e)
        print(traceback.format_exc())
        raise

def fb_text_post(page_id, token, message):
    url = FB_FEED_URL.format(page_id=page_id)
    print(f"[FB] Creating text-only post at {url}")
    try:
        r = requests.post(url, data={"message": message, "access_token": token}, timeout=TIMEOUT)
        print_resp_summary(r, "FB_TEXT")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("[FB] Exception creating text post:", e)
        print(traceback.format_exc())
        raise

# --- IG helpers
def ig_publish(ig_user_id, token, image_url, caption):
    create_url = IG_MEDIA_URL.format(ig_user_id=ig_user_id)
    publish_url = IG_PUBLISH_URL.format(ig_user_id=ig_user_id)
    print(f"[IG] create: {create_url}")
    try:
        resp = requests.post(create_url, data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=TIMEOUT)
        print_resp_summary(resp, "IG_CREATE")
        resp.raise_for_status()
        container = resp.json()
        cid = container.get("id")
        print(f"[IG] container id: {cid}")
        if not cid:
            raise RuntimeError("no container id from IG create")
        resp2 = requests.post(publish_url, data={"creation_id": cid, "access_token": token}, timeout=TIMEOUT)
        print_resp_summary(resp2, "IG_PUBLISH")
        resp2.raise_for_status()
        return resp2.json()
    except Exception as e:
        print("[IG] Exception:", e)
        print(traceback.format_exc())
        raise

# --- main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonfile")
    parser.add_argument("--mode", required=True, choices=["fb", "ig"])
    parser.add_argument("--max-retries", type=int, default=6)
    parser.add_argument("--retry-interval", type=int, default=5)
    args = parser.parse_args()

    print(f"[RUN] mode={args.mode} jsonfile={args.jsonfile} SITE_URL_BASE={'set' if SITE_URL_BASE else 'not-set'} ASSETS_PATH={'set' if ASSETS_PATH else 'not-set'}")
    try:
        article = load_json(args.jsonfile)
    except Exception as e:
        print("[ERROR] Could not load JSON:", e)
        print(traceback.format_exc())
        sys.exit(2)

    print("[ARTICLE] keys:", list(article.keys()))
    # print the article header values (safe)
    for k in ("title", "excerpt", "slug", "url", "cover_image"):
        if k in article:
            v = article.get(k)
            if isinstance(v, str) and len(v) > 500:
                print(f"[ARTICLE] {k}: <long string, length={len(v)}>")
            else:
                print(f"[ARTICLE] {k}: {v}")

    title = article.get("title") or article.get("slug") or "New Article"
    excerpt = article.get("excerpt") or article.get("summary") or ""
    url = article.get("url") or ""
    caption = f"{title}\n\n{excerpt}\n\nRead more: {url}"

    key, imgval = find_image(article)
    print(f"[IMAGE] candidate key={key} value={imgval}")

    public_img = None
    local_img = None

    if imgval:
        if is_public_url(imgval):
            public_img = imgval
            print("[IMAGE] determined: public URL in JSON")
        else:
            # try build public url from SITE_URL_BASE
            if SITE_URL_BASE:
                built = build_public_url(imgval)
                print(f"[IMAGE] built public URL: {built}")
                public_img = built
            # check local file paths
            candidate_local = Path(imgval.lstrip("/"))
            if candidate_local.exists():
                local_img = str(candidate_local)
                print(f"[IMAGE] found local file: {local_img}")
            else:
                if ASSETS_PATH:
                    alt = Path(ASSETS_PATH) / Path(imgval).name
                    if alt.exists():
                        local_img = str(alt)
                        print(f"[IMAGE] found in ASSETS_PATH: {local_img}")
    else:
        print("[IMAGE] No image key found in JSON")

    # Decide FB behavior
    if args.mode == "fb":
        if not FB_PAGE_TOKEN or not FB_PAGE_ID:
            print("[ERROR] FB_PAGE_TOKEN or FB_PAGE_ID not set. Aborting FB publish.")
            sys.exit(5)
        try:
            if local_img:
                print("[FB] Uploading local file to FB...")
                resp = fb_upload(FB_PAGE_ID, FB_PAGE_TOKEN, local_img, caption)
                print("[FB] upload response:", resp)
                media_id = resp.get("id")
                if media_id:
                    fb_create_feed_with_media(FB_PAGE_ID, FB_PAGE_TOKEN, media_id, caption)
                else:
                    fb_text_post(FB_PAGE_ID, FB_PAGE_TOKEN, caption)
            elif public_img:
                print("[FB] Using public image URL for FB upload/checks...")
                status, ctype = check_url_head(public_img)
                print(f"[FB] HEAD check for public image: status={status} content-type={ctype}")
                # try FB upload with the URL
                resp = fb_upload(FB_PAGE_ID, FB_PAGE_TOKEN, public_img, caption)
                print("[FB] upload response:", resp)
                media_id = resp.get("id")
                if media_id:
                    fb_create_feed_with_media(FB_PAGE_ID, FB_PAGE_TOKEN, media_id, caption)
                else:
                    fb_text_post(FB_PAGE_ID, FB_PAGE_TOKEN, caption)
            else:
                print("[FB] No image available; making a text-only post")
                fb_text_post(FB_PAGE_ID, FB_PAGE_TOKEN, caption)
            print("[FB] Completed successfully")
            sys.exit(0)
        except Exception as e:
            print("[FB] Fatal error:", e)
            print(traceback.format_exc())
            sys.exit(6)

    #
