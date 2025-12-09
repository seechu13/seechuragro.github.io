#!/usr/bin/env python3
# Shared helpers for image extraction / normalization

from urllib.parse import urljoin

def normalize_image_url(url, base_url):
    """
    Convert relative paths (starting with /) to absolute using base_url.
    Leave absolute urls untouched.
    """
    if not url:
        return None
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))

def extract_images_from_json(j, base_url=""):
    """
    Return list of image URLs (may be empty).
    Order of preference:
      j['images'] -> j['cover_image'] -> j['media']
    Support: string or list for cover_image.
    Normalize relative to base_url.
    """
    imgs = None
    if isinstance(j.get("images"), list) and j.get("images"):
        imgs = j.get("images")
    elif j.get("cover_image") is not None:
        ci = j.get("cover_image")
        if isinstance(ci, list):
            imgs = ci
        elif isinstance(ci, str) and ci.strip() != "":
            imgs = [ci]
    elif isinstance(j.get("media"), list) and j.get("media"):
        imgs = j.get("media")

    if not imgs:
        return []

    normalized = []
    for u in imgs:
        nu = normalize_image_url(u, base_url) if base_url else (u.strip() if isinstance(u, str) else None)
        if nu:
            normalized.append(nu)
    return normalized
