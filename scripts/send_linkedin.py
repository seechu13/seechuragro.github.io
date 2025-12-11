#!/usr/bin/env python3
"""
Send a single article JSON to LinkedIn as a personal post (UGC) using the first image only.

Usage:
  python scripts/send_linkedin.py --json articles/test-automation.json

Environment variables required:
  LINKEDIN_ACCESS_TOKEN  (string)
  LINKEDIN_PERSON        (string)  # numeric LinkedIn person id, e.g. grQXp0KaKF
  BASE_URL               (optional) fallback when JSON lacks absolute URL
  LINKEDIN_KEEP_URL_WITH_IMAGE: "true" or "false"
  LINKEDIN_POST_IMAGE: "true" or "false"
"""

import os
import sys
import json
import argparse
import logging
import requests
from urllib.parse import urljoin, urlparse
from io import BytesIO
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

def get_env(name, required=True):
    val = os.getenv(name)
    if required and not val:
        logger.error("Missing required env var: %s", name)
        sys.exit(2)
    return val

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def make_caption(article, base_url=None):
    title = article.get("title", "").strip()
    excerpt = article.get("excerpt", "").strip()
    url = article.get("url", "")
    if not url and base_url and article.get("path"):
        url = urljoin(base_url.rstrip("/") + "/", article.get("path").lstrip("/"))
    hashtags = article.get("hashtags")
    if not hashtags:
        words = (title + " " + excerpt).split()
        tags = []
        for w in words:
            w = ''.join(ch for ch in w if ch.isalnum())
            if len(w) > 3:
                tag = w.lower()
                if tag not in tags:
                    tags.append(tag)
            if len(tags) >= 4:
                break
        hashtags = ["#" + t for t in tags]
    if isinstance(hashtags, list):
        tagline = " ".join(hashtags)
    else:
        tagline = str(hashtags).strip()
    parts = []
    if title:
        parts.append(title)
    if excerpt:
        parts.append(excerpt)
    if url:
        parts.append(url)
    if tagline:
        parts.append(tagline)
    return "\n\n".join(parts)

def make_caption_no_url(article, base_url=None):
    title = article.get("title", "").strip()
    excerpt = article.get("excerpt", "").strip()
    hashtags = article.get("hashtags")
    if not hashtags:
        words = (title + " " + excerpt).split()
        tags = []
        for w in words:
            w = ''.join(ch for ch in w if ch.isalnum())
            if len(w) > 3:
                tag = w.lower()
                if tag not in tags:
                    tags.append(tag)
            if len(tags) >= 4:
                break
        hashtags = ["#" + t for t in tags]
    if isinstance(hashtags, list):
        tagline = " ".join(hashtags)
    else:
        tagline = str(hashtags).strip()
    parts = []
    if title:
        parts.append(title)
    if excerpt:
        parts.append(excerpt)
    if tagline:
        parts.append(tagline)
    return "\n\n".join(parts)

def is_remote(url):
    p = urlparse(url)
    return p.scheme in ("http", "https")

def download_image(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return BytesIO(resp.content)

def process_image_bytes(img_bytes, max_px=1200):
    img = Image.open(img_bytes).convert("RGB")
    w, h = img.size
    max_side = max(w, h)
    if max_side > max_px:
        scale = max_px / float(max_side)
        new = (int(w * scale), int(h * scale))
        img = img.resize(new, Image.LANCZOS)
    out = BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)
    out.seek(0)
    return out

def register_upload(owner_urn, access_token):
    url = f"{LINKEDIN_API_BASE}/assets?action=registerUpload"
    body = {
      "registerUploadRequest": {
        "owner": owner_urn,
        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
        "serviceRelationships": [
          {
            "identifier": "urn:li:userGeneratedContent",
            "relationshipType": "OWNER"
          }
        ]
      }
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    asset = data.get("value", {}).get("asset")
    upload_mech = data.get("value", {}).get("uploadMechanism", {})
    upload_url = None
    if isinstance(upload_mech, dict):
        for v in upload_mech.values():
            if isinstance(v, dict) and v.get("uploadUrl"):
                upload_url = v["uploadUrl"]
                break
    if not asset or not upload_url:
        raise RuntimeError("Invalid registerUpload response: missing asset or uploadUrl: %s" % data)
    return asset, upload_url

def upload_image_to_url(upload_url, image_bytes):
    headers = {"Content-Type": "image/jpeg"}
    resp = requests.put(upload_url, data=image_bytes.read(), headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.status_code

def create_ugc_post(author_urn, access_token, caption, asset_urn=None, title_text=None):
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    if asset_urn:
        media = [{
            "status": "READY",
            "media": asset_urn,
            "title": {"text": title_text or ""}
        }]
        share_media_category = "IMAGE"
    else:
        media = []
        share_media_category = "NONE"

    body = {
      "author": author_urn,
      "lifecycleState": "PUBLISHED",
      "specificContent": {
        "com.linkedin.ugc.ShareContent": {
          "shareCommentary": {
            "text": caption
          },
          "shareMediaCategory": share_media_category,
        }
      },
      "visibility": {
        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
      }
    }

    if asset_urn:
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = media

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Article JSON path")
    args = parser.parse_args()

    access_token = get_env("LINKEDIN_ACCESS_TOKEN")
    person_id = get_env("LINKEDIN_PERSON")
    base_url = os.getenv("BASE_URL", "").strip() or None

    keep_url_with_image = os.getenv("LINKEDIN_KEEP_URL_WITH_IMAGE", "true").lower() in ("1","true","yes")
    post_image_env = os.getenv("LINKEDIN_POST_IMAGE", "true").lower()
    post_image = post_image_env not in ("0","false","no")

    author_urn = f"urn:li:person:{person_id}"

    article = read_json(args.json)
    full_caption = make_caption(article, base_url=base_url)
    caption_no_url = make_caption_no_url(article, base_url=base_url)
    title = article.get("title", "")

    # pick default caption (we will re-select if image present)
    caption_to_send = full_caption

    images = article.get("images") or article.get("image") or []
    if isinstance(images, str):
        images = [images]
    if not isinstance(images, list):
        images = list(images)

    asset_urn = None

    try:
        if post_image and images:
            first = images[0]
            if not first:
                logger.info("First image is empty. Posting text-only.")
            else:
                # decide caption when image present
                if keep_url_with_image:
                    caption_to_send = full_caption
                else:
                    caption_to_send = caption_no_url

                if is_remote(first):
                    logger.info("Downloading remote image: %s", first)
                    img_bytes = download_image(first)
                else:
                    local_path = first
                    if local_path.startswith("/"):
                        local_path = local_path[1:]
                    if os.path.isfile(local_path):
                        logger.info("Opening local image: %s", local_path)
                        img_bytes = open(local_path, "rb")
                    else:
                        alternate = os.path.join(os.getcwd(), local_path)
                        if os.path.isfile(alternate):
                            logger.info("Opening local image (alternate): %s", alternate)
                            img_bytes = open(alternate, "rb")
                        else:
                            logger.warning("Local image not found: %s — posting without image", local_path)
                            img_bytes = None

                if img_bytes:
                    processed = process_image_bytes(img_bytes, max_px=1200)
                    logger.info("Processed image size: %d bytes", len(processed.getvalue()))
                    asset_urn, upload_url = register_upload(author_urn, access_token)
                    logger.info("Registered asset: %s", asset_urn)
                    upload_image_to_url(upload_url, processed)
                    logger.info("Uploaded image to LinkedIn uploadUrl.")
        else:
            # no image or explicitly disabled: send full caption (includes URL)
            caption_to_send = full_caption
    except requests.HTTPError as e:
        logger.error("HTTP error while handling image or LinkedIn endpoint: %s", e)
        logger.error("Posting text-only instead.")
        asset_urn = None
    except Exception as e:
        logger.error("Unexpected error while preparing image: %s", e)
        logger.error("Posting text-only instead.")
        asset_urn = None

    try:
        resp = create_ugc_post(author_urn, access_token, caption_to_send, asset_urn=asset_urn, title_text=title)
        logger.info("LinkedIn post created successfully: %s", resp.get("id", resp))
    except requests.HTTPError as e:
        if e.response is not None:
            try:
                logger.error("LinkedIn responded with: %s", e.response.text)
            except Exception:
                pass
        logger.error("Failed to create LinkedIn post: %s", e)
        sys.exit(3)

if __name__ == "__main__":
    main()
