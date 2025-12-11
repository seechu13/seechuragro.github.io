#!/usr/bin/env python3
"""
Telegram poster with robust image handling:
- Downloads remote URLs
- Opens with Pillow
- Resizes to max 1280px (Telegram safe)
- Converts to clean JPEG
- Uploads as photo
- Sends caption as text first (title, excerpt, URL, hashtags)
"""

import os
import sys
import json
import logging
import requests
import re
import hashlib
from pathlib import Path
from collections import Counter
from PIL import Image
from io import BytesIO

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

if not BOT_TOKEN or not CHAT_ID:
    logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    sys.exit(2)

TMP_DIR = Path("/tmp/telegram_imgs")
TMP_DIR.mkdir(parents=True, exist_ok=True)

STOPWORDS = {
    'the','and','a','an','to','of','for','in','on','with','is','are','be','by','from',
    'this','that','we','our','as','it','its','at','will','or','which','about','into',
    'your','you','our','seechuragro'
}

# =====================================================
# HASHTAGS
# =====================================================
def normalize_token(t):
    return re.sub(r'[^0-9A-Za-z]+', '', str(t)).strip().lower()

def gen_hashtags_from_text(title, excerpt, limit=4):
    text = " ".join(filter(None, [title or "", excerpt or ""]))
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    ctr = Counter(words)
    tags = []
    for w,_ in ctr.most_common(limit*2):
        token = normalize_token(w)
        if token and token not in tags:
            tags.append(token)
        if len(tags) >= limit:
            break
    return tags

def hashtags_to_text(h, title=None, excerpt=None):
    if not h:
        tags = gen_hashtags_from_text(title, excerpt)
        return " ".join("#"+t for t in tags)
    if isinstance(h, list):
        tags = [str(x).strip().lstrip('#') for x in h if str(x).strip()]
    else:
        s = str(h).strip()
        tags = [p.strip().lstrip('#') for p in (s.split(",") if "," in s else s.split()) if p.strip()]
    return " ".join("#" + t for t in tags)

# =====================================================
# URL BUILDER
# =====================================================
def build_url(raw_url, slug):
    if raw_url:
        s = raw_url.strip()
        if s.startswith("http"):
            return s
        return f"{BASE_URL}/{s.lstrip('/')}"
    if slug:
        return f"{BASE_URL}/{str(slug).lstrip('/')}"
    return ""

# =====================================================
# IMAGE DOWNLOAD + PILLOW RESIZE + JPEG CONVERSION
# =====================================================
def download_and_prepare(url, max_size=1280):
    """
    Downloads the image → opens with Pillow → resizes → saves as JPEG.
    Returns path to processed JPEG or None.
    """
    try:
        logging.info("Downloading: %s", url)
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            logging.error("Download failed (%s) for %s", r.status_code, url)
            return None

        img = Image.open(BytesIO(r.content)).convert("RGB")
        w, h = img.size

        # Resize preserving aspect ratio
        if max(w,h) > max_size:
            img.thumbnail((max_size, max_size))

        # Filename based on URL hash
        hsh = hashlib.sha256(url.encode()).hexdigest()[:16]
        out_path = TMP_DIR / f"{hsh}.jpg"
        img.save(out_path, "JPEG", quality=90)

        logging.info("Saved processed image: %s", out_path)
        return str(out_path)

    except Exception as e:
        logging.error("Image processing failed for %s : %s", url, e)
        return None

# =====================================================
# TELEGRAM API
# =====================================================
def send_text(msg):
    url = f"{API_BASE}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
    logging.info("sendMessage: %s", r.status_code)
    return r.ok

def send_photo(path):
    url = f"{API_BASE}/sendPhoto"
    try:
        with open(path, "rb") as fh:
            files = {"photo": fh}
            data = {"chat_id": CHAT_ID}
            r = requests.post(url, files=files, data=data, timeout=60)
        logging.info("sendPhoto: %s for %s", r.status_code, path)
        if not r.ok:
            logging.error("sendPhoto response: %s", r.text)
        return r.ok
    except Exception as e:
        logging.error("Photo upload failed: %s", e)
        return False

# =====================================================
# MAIN
# =====================================================
def main():
    if len(sys.argv) < 2:
        print("Usage: send_telegram.py article.json")
        sys.exit(2)

    jf = Path(sys.argv[1])
    data = json.loads(jf.read_text())

    title   = data.get("title","")
    excerpt = data.get("excerpt","") or data.get("description","")
    raw_url = data.get("url") or data.get("link")
    slug    = data.get("slug")
    images  = data.get("images") or data.get("cover_image") or []

    hashtags_raw = data.get("hashtags") or data.get("tags")
    url = build_url(raw_url, slug)
    tags_text = hashtags_to_text(hashtags_raw, title, excerpt)

    caption = "\n\n".join(x for x in [f"<b>{title}</b>", excerpt, url, tags_text] if x)

    # 1️⃣ Always send caption first
    send_text(caption)

    # 2️⃣ Process up to 4 images
    local_imgs = []
    for img_url in images[:4]:
        if isinstance(img_url, str) and img_url.startswith("http"):
            processed = download_and_prepare(img_url)
            if processed:
                local_imgs.append(processed)
        else:
            # Local file
            p = Path(img_url)
            if p.exists():
                # Process local file too
                try:
                    img = Image.open(p).convert("RGB")
                    img.thumbnail((1280,1280))
                    out_path = TMP_DIR / (p.stem + "_resized.jpg")
                    img.save(out_path, "JPEG", quality=90)
                    local_imgs.append(str(out_path))
                except:
                    pass

    # 3️⃣ Upload each image
    ok = True
    for lp in local_imgs:
        if not send_photo(lp):
            ok = False

    sys.exit(0 if ok else 3)

if __name__ == "__main__":
    main()
