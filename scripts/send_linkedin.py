#!/usr/bin/env python3
"""
Verbose LinkedIn poster — logs download, Pillow conversion, registerUpload response,
upload PUT status code and full create_ugc_post response.

This version includes an improved `process_image_bytes` that compresses/resizes
images iteratively to target ~4.5MB so LinkedIn uploads are more reliable.
"""
import os
import sys
import json
import logging
import requests
import argparse
from urllib.parse import urljoin, urlparse
from io import BytesIO
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

def get_env(name, required=True):
    v = os.getenv(name)
    if required and not v:
        logger.error("Missing env var: %s", name)
        sys.exit(2)
    return v

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_full_caption(article, base_url=None):
    title = article.get("title","").strip()
    excerpt = article.get("excerpt","").strip()
    url = article.get("url","")
    if not url and base_url and article.get("path"):
        url = urljoin(base_url.rstrip("/") + "/", article.get("path").lstrip("/"))
    hashtags = article.get("hashtags")
    if not hashtags:
        words = (title + " " + excerpt).split()
        tags=[]
        for w in words:
            w=''.join(ch for ch in w if ch.isalnum())
            if len(w)>3 and w.lower() not in tags:
                tags.append(w.lower())
            if len(tags)>=4:
                break
        hashtags = ["#"+t for t in tags]
    if isinstance(hashtags,list):
        tags_line = " ".join(hashtags)
    else:
        tags_line = str(hashtags).strip()
    parts=[]
    if title: parts.append(title)
    if excerpt: parts.append(excerpt)
    if url: parts.append(url)
    if tags_line: parts.append(tags_line)
    return "\n\n".join(parts)

def build_caption_no_url(article):
    title = article.get("title","").strip()
    excerpt = article.get("excerpt","").strip()
    hashtags = article.get("hashtags")
    if not hashtags:
        words = (title + " " + excerpt).split()
        tags=[]
        for w in words:
            w=''.join(ch for ch in w if ch.isalnum())
            if len(w)>3 and w.lower() not in tags:
                tags.append(w.lower())
            if len(tags)>=4:
                break
        hashtags = ["#"+t for t in tags]
    if isinstance(hashtags,list):
        tags_line = " ".join(hashtags)
    else:
        tags_line = str(hashtags).strip()
    parts=[]
    if title: parts.append(title)
    if excerpt: parts.append(excerpt)
    if tags_line: parts.append(tags_line)
    return "\n\n".join(parts)

def is_remote(u):
    p = urlparse(u)
    return p.scheme in ("http","https")

def download_image(url):
    logger.info("Downloading image URL: %s", url)
    r = requests.get(url, timeout=30)
    logger.info("Download response: %s", r.status_code)
    r.raise_for_status()
    return BytesIO(r.content)

def process_image_bytes(img_bytes, max_px=1200, target_bytes=4_500_000):
    """
    Convert image to RGB JPEG, resize longest side to max_px, then iteratively
    lower JPEG quality until size <= target_bytes (or quality floor reached).
    Returns a BytesIO containing the JPEG data.
    """
    logger.info("Processing image with Pillow (max_px=%d, target_bytes=%d)", max_px, target_bytes)
    img = Image.open(img_bytes).convert("RGB")
    w, h = img.size
    logger.info("Original image size: %dx%d", w, h)

    # Resize if needed
    max_side = max(w, h)
    if max_side > max_px:
        scale = max_px / float(max_side)
        new = (int(w * scale), int(h * scale))
        logger.info("Resizing to: %s", new)
        img = img.resize(new, Image.LANCZOS)

    # Try saving with descending quality until under target_bytes
    quality = 90
    out = BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    size = len(out.getvalue())
    logger.info("Saved JPEG quality=%d size=%d bytes", quality, size)

    # Reduce quality in steps until under target or min quality reached
    while size > target_bytes and quality >= 55:
        quality -= 5
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        size = len(out.getvalue())
        logger.info("Saved JPEG quality=%d size=%d bytes", quality, size)

    # If still too large after reaching low quality, do a further resize (reduce max_px by 20%) and retry
    if size > target_bytes:
        logger.info("Still > target after quality reductions — additional downscale and retrying")
        w2, h2 = img.size
        new_max = int(max_px * 0.8)
        if max(w2, h2) > new_max:
            scale = new_max / float(max(w2, h2))
            new = (int(w2 * scale), int(h2 * scale))
            logger.info("Further resizing to: %s", new)
            img = img.resize(new, Image.LANCZOS)
        # final save attempts
        quality = 65
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        size = len(out.getvalue())
        logger.info("After downscale quality=%d size=%d bytes", quality, size)
        # if still too big, lower quality more (but stop at 50)
        while size > target_bytes and quality > 50:
            quality -= 5
            out = BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            size = len(out.getvalue())
            logger.info("After extra reduction quality=%d size=%d bytes", quality, size)

    out.seek(0)
    logger.info("Final processed image size: %d bytes (quality=%d)", len(out.getvalue()), quality)
    return out

def register_upload(owner_urn, access_token):
    url = f"{LINKEDIN_API_BASE}/assets?action=registerUpload"
    body = {
      "registerUploadRequest": {
        "owner": owner_urn,
        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
        "serviceRelationships": [
          {"identifier":"urn:li:userGeneratedContent","relationshipType":"OWNER"}
        ]
      }
    }
    headers = {"Authorization":f"Bearer {access_token}","Content-Type":"application/json","X-Restli-Protocol-Version":"2.0.0"}
    logger.info("Calling registerUpload...")
    r = requests.post(url, headers=headers, json=body, timeout=30)
    logger.info("registerUpload status: %s", r.status_code)
    try:
        j = r.json()
    except Exception:
        j = {"raw_text": r.text}
    logger.info("registerUpload response: %s", json.dumps(j)[:1000])
    r.raise_for_status()
    asset = j.get("value",{}).get("asset")
    upload_mech = j.get("value",{}).get("uploadMechanism",{})
    upload_url = None
    if isinstance(upload_mech, dict):
        for v in upload_mech.values():
            if isinstance(v, dict) and v.get("uploadUrl"):
                upload_url = v["uploadUrl"]; break
    if not asset or not upload_url:
        raise RuntimeError("registerUpload missing asset or uploadUrl: %s" % j)
    return asset, upload_url

def upload_image_to_url(upload_url, image_bytes):
    logger.info("Uploading image via PUT to uploadUrl (this is the large binary upload).")
    headers = {"Content-Type":"image/jpeg"}
    r = requests.put(upload_url, data=image_bytes.read(), headers=headers, timeout=120)
    logger.info("PUT upload response code: %s", r.status_code)
    logger.info("PUT response text (truncated): %s", (r.text or "")[:500])
    r.raise_for_status()
    return r.status_code

def create_ugc_post(author_urn, access_token, caption, asset_urn=None, title_text=None):
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = {"Authorization":f"Bearer {access_token}","Content-Type":"application/json","X-Restli-Protocol-Version":"2.0.0"}
    if asset_urn:
        media = [{"status":"READY","media":asset_urn,"title":{"text": title_text or ""}}]
        share_media_category = "IMAGE"
    else:
        media = []
        share_media_category = "NONE"
    body = {
      "author": author_urn,
      "lifecycleState": "PUBLISHED",
      "specificContent": {"com.linkedin.ugc.ShareContent": {
          "shareCommentary": {"text": caption},
          "shareMediaCategory": share_media_category
      }},
      "visibility": {"com.linkedin.ugc.MemberNetworkVisibility":"PUBLIC"}
    }
    if asset_urn:
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = media
    logger.info("Posting UGC with payload preview: %s", json.dumps(body)[:1000])
    r = requests.post(url, headers=headers, json=body, timeout=30)
    logger.info("create_ugc_post status: %s", r.status_code)
    try:
        j = r.json()
    except Exception:
        j = {"raw_text": r.text}
    logger.info("create_ugc_post response: %s", json.dumps(j)[:2000])
    r.raise_for_status()
    return j

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True)
    args = p.parse_args()

    access_token = get_env("LINKEDIN_ACCESS_TOKEN")
    person_id = get_env("LINKEDIN_PERSON")
    base_url = os.getenv("BASE_URL","").strip() or None
    keep_url_with_image = os.getenv("LINKEDIN_KEEP_URL_WITH_IMAGE","true").lower() in ("1","true","yes")
    post_image_env = os.getenv("LINKEDIN_POST_IMAGE","true").lower()
    post_image = post_image_env not in ("0","false","no")
    author_urn = f"urn:li:person:{person_id}"

    article = read_json(args.json)
    logger.info("Article read: title=%s", (article.get("title") or "")[:120])
    full_caption = build_full_caption(article, base_url=base_url)
    caption_no_url = build_caption_no_url(article)
    logger.info("Full caption preview: %s", full_caption[:500].replace("\n"," / "))
    logger.info("Caption-no-url preview: %s", caption_no_url[:500].replace("\n"," / "))

    images = article.get("images") or article.get("image") or []
    if isinstance(images, str): images=[images]
    if not isinstance(images, list): images=list(images)
    logger.info("Images list from JSON: %s", images)

    caption_to_send = full_caption
    asset_urn = None

    if post_image and images:
        first = images[0]
        if not first:
            logger.warning("First image empty -> posting text-only")
        else:
            # choose caption policy
            if keep_url_with_image:
                caption_to_send = full_caption
            else:
                caption_to_send = caption_no_url

            try:
                if is_remote(first):
                    img_bytes = download_image(first)
                else:
                    local = first.lstrip("/")
                    if os.path.isfile(local):
                        logger.info("Opening local image: %s", local)
                        img_bytes = open(local,"rb")
                    else:
                        alt = os.path.join(os.getcwd(), local)
                        if os.path.isfile(alt):
                            logger.info("Opening local image alt: %s", alt)
                            img_bytes = open(alt,"rb")
                        else:
                            logger.warning("Local image not found: %s", first)
                            img_bytes = None

                if img_bytes:
                    processed = process_image_bytes(img_bytes, max_px=1200, target_bytes=4_500_000)
                    # register upload
                    try:
                        asset_urn, upload_url = register_upload(author_urn, access_token)
                        logger.info("Asset URN: %s", asset_urn)
                    except Exception as e:
                        logger.exception("register_upload failed")
                        asset_urn = None
                        upload_url = None

                    if upload_url and processed:
                        try:
                            code = upload_image_to_url(upload_url, processed)
                            logger.info("Upload returned HTTP code: %s", code)
                        except Exception as e:
                            logger.exception("upload_image_to_url failed")
                            asset_urn = None
                else:
                    logger.warning("No img_bytes available; skipping image upload")
            except requests.HTTPError as e:
                logger.exception("HTTP error during image handling")
            except Exception as e:
                logger.exception("Unexpected error during image handling")

    else:
        if not post_image:
            logger.info("Posting text-only: LINKEDIN_POST_IMAGE=false")
        else:
            logger.info("No images found; posting text-only")

    # final post
    try:
        resp = create_ugc_post(author_urn, access_token, caption_to_send, asset_urn=asset_urn, title_text=article.get("title",""))
        logger.info("LinkedIn post created successfully: %s", resp.get("id", resp))
    except requests.HTTPError as e:
        logger.exception("LinkedIn returned HTTP error on create_ugc_post")
        try:
            logger.error("create_ugc_post body: %s", e.response.text)
        except Exception:
            pass
        sys.exit(3)
    except Exception as e:
        logger.exception("Unexpected error creating UGC post")
        sys.exit(3)

if __name__ == "__main__":
    main()
