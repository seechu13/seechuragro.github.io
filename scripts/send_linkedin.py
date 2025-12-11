#!/usr/bin/env python3
"""
Robust LinkedIn poster with long-term image-key support.

Features:
- Accepts images from any of these fields (priority order):
  images, image, cover_image, cover, thumbnail
- Supports list or string values.
- Downloads remote images or reads local repo files.
- Processes images (resize + iterative JPEG quality reduction) to target size.
- Registers upload, uploads binary via PUT, creates UGC post with media.
- Env toggles:
    LINKEDIN_KEEP_URL_WITH_IMAGE: "true"|"false"   (default true)
    LINKEDIN_POST_IMAGE: "true"|"false"            (default true)
- Required env:
    LINKEDIN_ACCESS_TOKEN
    LINKEDIN_PERSON  (person id only, e.g. grQXp0KaKF)
    BASE_URL (optional)
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

# ---- logging ----
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

# ---- helpers ----
def get_env(name, required=True):
    v = os.getenv(name)
    if required and not v:
        logger.error("Missing env var: %s", name)
        sys.exit(2)
    return v

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_full_caption(article, base_url=None, max_tags=6):
    title = (article.get("title") or "").strip()
    excerpt = (article.get("excerpt") or article.get("description") or "").strip()
    url = article.get("url") or ""
    if not url and base_url and article.get("path"):
        url = urljoin(base_url.rstrip("/") + "/", article.get("path").lstrip("/"))
    hashtags = article.get("hashtags")
    if not hashtags:
        # auto-generate a few hashtags from words
        words = (title + " " + excerpt).split()
        tags = []
        for w in words:
            tok = ''.join(ch for ch in w if ch.isalnum()).lower()
            if len(tok) > 3 and tok not in tags:
                tags.append(tok)
            if len(tags) >= max_tags:
                break
        hashtags = ["#" + t for t in tags]
    tagline = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags).strip()
    parts = []
    if title: parts.append(title)
    if excerpt: parts.append(excerpt)
    if url: parts.append(url)
    if tagline: parts.append(tagline)
    return "\n\n".join(parts)

def build_caption_no_url(article, base_url=None, max_tags=6):
    title = (article.get("title") or "").strip()
    excerpt = (article.get("excerpt") or article.get("description") or "").strip()
    hashtags = article.get("hashtags")
    if not hashtags:
        words = (title + " " + excerpt).split()
        tags = []
        for w in words:
            tok = ''.join(ch for ch in w if ch.isalnum()).lower()
            if len(tok) > 3 and tok not in tags:
                tags.append(tok)
            if len(tags) >= max_tags:
                break
        hashtags = ["#" + t for t in tags]
    tagline = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags).strip()
    parts = []
    if title: parts.append(title)
    if excerpt: parts.append(excerpt)
    if tagline: parts.append(tagline)
    return "\n\n".join(parts)

def choose_images_from_article(article):
    """
    Return list of image references by checking keys in priority order.
    Accepts 'images', 'image', 'cover_image', 'cover', 'thumbnail'.
    Normalize to list of strings.
    """
    candidates = []
    for k in ("images", "image", "cover_image", "cover", "thumbnail"):
        v = article.get(k)
        if not v:
            continue
        # Normalize
        if isinstance(v, str):
            candidates = [v]
        elif isinstance(v, (list, tuple)):
            # flatten and filter empty
            candidates = [str(x) for x in v if x]
        else:
            # fallback: stringify
            candidates = [str(v)]
        if candidates:
            logger.info("Using image key '%s' from JSON (found %d entries)", k, len(candidates))
            break
    return candidates

def is_remote(u):
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https")
    except Exception:
        return False

def download_image(url):
    logger.info("Downloading image URL: %s", url)
    r = requests.get(url, timeout=30)
    logger.info("Download response status: %s", r.status_code)
    r.raise_for_status()
    return BytesIO(r.content)

def process_image_bytes(img_bytes, max_px=1200, target_bytes=4_500_000):
    """
    Convert to JPEG, resize if needed, iteratively reduce quality to meet target_bytes.
    Returns BytesIO.
    """
    logger.info("Processing image (max_px=%d target_bytes=%d)", max_px, target_bytes)
    img = Image.open(img_bytes).convert("RGB")
    w, h = img.size
    logger.info("Original image dimensions: %dx%d", w, h)

    # Resize if needed
    max_side = max(w, h)
    if max_side > max_px:
        scale = max_px / float(max_side)
        new = (int(w * scale), int(h * scale))
        logger.info("Resizing to: %s", new)
        img = img.resize(new, Image.LANCZOS)

    # Save and iterate quality
    quality = 90
    out = BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    size = len(out.getvalue())
    logger.info("Saved JPEG quality=%d size=%d", quality, size)

    while size > target_bytes and quality >= 55:
        quality -= 5
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        size = len(out.getvalue())
        logger.info("Saved JPEG quality=%d size=%d", quality, size)

    if size > target_bytes:
        logger.info("Still too large after quality reductions — downscaling further")
        w2, h2 = img.size
        new_max = int(max_px * 0.8)
        if max(w2, h2) > new_max:
            scale = new_max / float(max(w2, h2))
            new = (int(w2 * scale), int(h2 * scale))
            logger.info("Further resizing to: %s", new)
            img = img.resize(new, Image.LANCZOS)
        quality = 65
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        size = len(out.getvalue())
        logger.info("After downscale quality=%d size=%d", quality, size)
        while size > target_bytes and quality > 50:
            quality -= 5
            out = BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            size = len(out.getvalue())
            logger.info("After extra reduction quality=%d size=%d", quality, size)

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
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    logger.info("Calling registerUpload...")
    r = requests.post(url, headers=headers, json=body, timeout=30)
    logger.info("registerUpload status: %s", r.status_code)
    try:
        j = r.json()
    except Exception:
        j = {"raw_text": r.text}
    logger.info("registerUpload response (truncated): %s", json.dumps(j)[:1000])
    r.raise_for_status()
    asset = j.get("value", {}).get("asset")
    upload_mech = j.get("value", {}).get("uploadMechanism", {})
    upload_url = None
    if isinstance(upload_mech, dict):
        for v in upload_mech.values():
            if isinstance(v, dict) and v.get("uploadUrl"):
                upload_url = v["uploadUrl"]
                break
    if not asset or not upload_url:
        raise RuntimeError("registerUpload missing asset or uploadUrl: %s" % j)
    return asset, upload_url

def upload_image_to_url(upload_url, image_bytes):
    logger.info("Uploading image to uploadUrl (PUT)...")
    headers = {"Content-Type": "image/jpeg"}
    r = requests.put(upload_url, data=image_bytes.read(), headers=headers, timeout=120)
    logger.info("PUT response code: %s", r.status_code)
    logger.info("PUT response text (truncated): %s", (r.text or "")[:500])
    r.raise_for_status()
    return r.status_code

def create_ugc_post(author_urn, access_token, caption, asset_urn=None, title_text=None):
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    if asset_urn:
        media = [{"status": "READY", "media": asset_urn, "title": {"text": title_text or ""}}]
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
      "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    if asset_urn:
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = media

    logger.info("Posting UGC (payload preview): %s", json.dumps(body)[:1000])
    r = requests.post(url, headers=headers, json=body, timeout=30)
    logger.info("create_ugc_post status: %s", r.status_code)
    try:
        j = r.json()
    except Exception:
        j = {"raw_text": r.text}
    logger.info("create_ugc_post response (truncated): %s", json.dumps(j)[:2000])
    r.raise_for_status()
    return j

# ---- main ----
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True)
    args = p.parse_args()

    access_token = get_env("LINKEDIN_ACCESS_TOKEN")
    person_id = get_env("LINKEDIN_PERSON")
    base_url = os.getenv("BASE_URL", "").strip() or None
    keep_url_with_image = os.getenv("LINKEDIN_KEEP_URL_WITH_IMAGE", "true").lower() in ("1","true","yes")
    post_image_env = os.getenv("LINKEDIN_POST_IMAGE", "true").lower()
    post_image = post_image_env not in ("0","false","no")
    author_urn = f"urn:li:person:{person_id}"

    article = read_json(args.json)
    logger.info("Article title (preview): %s", (article.get("title") or "")[:120])
    full_caption = build_full_caption(article, base_url=base_url)
    caption_no_url = build_caption_no_url(article, base_url=base_url)
    logger.info("Full caption preview: %s", full_caption[:400].replace("\n", " / "))
    logger.info("Caption-no-url preview: %s", caption_no_url[:400].replace("\n", " / "))

    images = choose_images_from_article(article)
    logger.info("Resolved images list: %s", images)

    caption_to_send = full_caption
    asset_urn = None

    if post_image and images:
        # Use first valid image only (LinkedIn personal posts support a single image in this flow)
        first = images[0] if images else None
        if not first:
            logger.warning("Image entry empty — will post text-only")
        else:
            # choose caption policy
            caption_to_send = full_caption if keep_url_with_image else caption_no_url

            img_bytes_obj = None
            try:
                if is_remote(first):
                    img_bytes_obj = download_image(first)
                else:
                    # local path: try direct and repo-relative
                    local_path = first.lstrip("/")
                    if os.path.isfile(local_path):
                        logger.info("Opening local image: %s", local_path)
                        img_bytes_obj = open(local_path, "rb")
                    else:
                        alt = os.path.join(os.getcwd(), local_path)
                        if os.path.isfile(alt):
                            logger.info("Opening local image alt: %s", alt)
                            img_bytes_obj = open(alt, "rb")
                        else:
                            logger.warning("Local image not found: %s", first)
                            img_bytes_obj = None

                if img_bytes_obj:
                    processed = process_image_bytes(img_bytes_obj, max_px=1200, target_bytes=4_500_000)
                    # register upload
                    try:
                        asset_urn, upload_url = register_upload(author_urn, access_token)
                        logger.info("Asset URN: %s", asset_urn)
                    except Exception:
                        logger.exception("register_upload failed")
                        asset_urn = None
                        upload_url = None

                    if upload_url and processed:
                        try:
                            code = upload_image_to_url(upload_url, processed)
                            logger.info("Upload returned HTTP code: %s", code)
                        except Exception:
                            logger.exception("upload_image_to_url failed")
                            asset_urn = None
                else:
                    logger.warning("No image bytes available; will post text-only")
            except requests.HTTPError:
                logger.exception("HTTP error during image download or upload; will post text-only")
                asset_urn = None
            except Exception:
                logger.exception("Unexpected error during image handling; will post text-only")
                asset_urn = None
    else:
        if not post_image:
            logger.info("Posting text-only because LINKEDIN_POST_IMAGE is false")
        else:
            logger.info("No images resolved; posting text-only")

    # final create UGC post
    try:
        resp = create_ugc_post(author_urn, access_token, caption_to_send, asset_urn=asset_urn, title_text=article.get("title",""))
        logger.info("LinkedIn post created successfully: %s", resp.get("id", resp))
    except requests.HTTPError as e:
        logger.exception("LinkedIn returned HTTP error on create_ugc_post")
        try:
            logger.error("create_ugc_post response body: %s", e.response.text)
        except Exception:
            pass
        sys.exit(3)
    except Exception as e:
        logger.exception("Unexpected error creating UGC post")
        sys.exit(3)

if __name__ == "__main__":
    main()
