#!/usr/bin/env python3
"""
scripts/send_telegram.py

Robust Telegram poster that downloads remote image URLs to the runner
and uploads the image files to Telegram (avoids Telegram's WEBPAGE_CURL_FAILED).

Behavior:
- Downloads remote images to /tmp/telegram_imgs/
- Verifies Content-Type starts with image/
- Uploads images as files (first with caption)
- Falls back gracefully on errors and logs details
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

if not BOT_TOKEN or not CHAT_ID:
    logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment.")
    sys.exit(2)


STOPWORDS = {
    'the','and','a','an','to','of','for','in','on','with','is','are','be','by','from',
    'this','that','we','our','as','it','its','at','will','or','which','about','into',
    'your','you','our','seechuragro'
}

TMP_DIR = Path("/tmp/telegram_imgs")
TMP_DIR.mkdir(parents=True, exist_ok=True)


def normalize_token(t):
    return re.sub(r'[^0-9A-Za-z]+', '', str(t)).strip().lower()


def gen_hashtags_from_text(title, excerpt, limit=4):
    text = " ".join(filter(None, [title or "", excerpt or ""]))
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    ctr = Counter(words)
    tags = []
    for w, _ in ctr.most_common(limit * 2):
        token = normalize_token(w)
        if not token or token in tags:
            continue
        tags.append(token)
        if len(tags) >= limit:
            break
    return tags


def hashtags_to_text(h, title=None, excerpt=None):
    if not h:
        tags = gen_hashtags_from_text(title, excerpt, limit=4)
        return " ".join("#" + t for t in tags) if tags else ""
    if isinstance(h, list):
        tags = [str(x).strip().lstrip('#') for x in h if str(x).strip()]
    else:
        s = str(h).strip()
        tags = [p.strip().lstrip('#') for p in (s.split(",") if "," in s else s.split()) if p.strip()]
    return " ".join("#" + t for t in tags) if tags else ""


def build_url(raw_url, slug):
    if raw_url:
        s = raw_url.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
        if s.startswith("//"):
            return "https:" + s
        return f"{BASE_URL}/{s.lstrip('/')}"
    if slug:
        return f"{BASE_URL}/{str(slug).lstrip('/')}"
    return ""


def download_image(url, timeout=20):
    """
    Download URL to TMP_DIR and return local path, or None on failure.
    """
    try:
        logging.info("Downloading image URL: %s", url)
        headers = {"User-Agent": "SeeChurAgro-Agent/1.0 (+https://seechuragro.in)"}
        r = requests.get(url, stream=True, timeout=timeout, headers=headers)
        if r.status_code != 200:
            logging.error("Download failed (%s) for %s", r.status_code, url)
            return None
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            logging.error("URL does not point to an image (content-type=%s): %s", ctype, url)
            return None
        data = r.content
        if not data:
            logging.error("No data downloaded from %s", url)
            return None
        # create filename by hashing url
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        ext = ctype.split("/")[-1].split(";")[0] or "jpg"
        fname = TMP_DIR / f"{h}.{ext}"
        fname.write_bytes(data)
        logging.info("Saved to %s", str(fname))
        return str(fname)
    except Exception as e:
        logging.error("Exception downloading %s : %s", url, e)
        return None


def send_text(chat_id, text):
    url = f"{API_BASE}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=30)
    logging.info("sendMessage status: %s", r.status_code)
    if not r.ok:
        logging.error("sendMessage response: %s", r.text)
    return r.ok


def send_photo_upload(chat_id, photo_path, caption=None):
    """
    Upload photo file (local path) with multipart/form-data.
    """
    url = f"{API_BASE}/sendPhoto"
    try:
        with open(photo_path, "rb") as fh:
            files = {"photo": fh}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            r = requests.post(url, data=data, files=files, timeout=120)
        logging.info("sendPhoto status: %s for %s", r.status_code, photo_path)
        if not r.ok:
            logging.error("sendPhoto response: %s", r.text)
        return r.ok
    except Exception as e:
        logging.error("Exception uploading %s : %s", photo_path, e)
        return False


def main():
    if len(sys.argv) < 2:
        logging.error("Usage: send_telegram.py path/to/article.json")
        sys.exit(2)
    jf = Path(sys.argv[1])
    if not jf.exists():
        logging.error("JSON file not found: %s", jf)
        sys.exit(2)

    data = json.loads(jf.read_text(encoding="utf-8"))
    title = data.get("title", "") or ""
    excerpt = data.get("excerpt", "") or data.get("description", "") or ""
    raw_url = data.get("url") or data.get("link") or ""
    slug = data.get("slug") or ""
    images = data.get("images") or []
    if not images:
        images = data.get("cover_image") or data.get("cover_images") or []
    hashtags_raw = data.get("hashtags") or data.get("tags") or ""

    url = build_url(raw_url, slug)
    tags_text = hashtags_to_text(hashtags_raw, title=title, excerpt=excerpt)

    parts = []
    if title:
        parts.append(f"<b>{title}</b>")
    if excerpt:
        parts.append(excerpt)
    if url:
        parts.append(url)
    if tags_text:
        parts.append(tags_text)

    caption = "\n\n".join(parts).strip()
    photos = list(images)[:4]

    # Prepare local files: for each photo, if it's a local path use it, if it's a URL attempt to download.
    local_photos = []
    for p in photos:
        if not isinstance(p, str) or not p.strip():
            continue
        p = p.strip()
        if Path(p).exists():
            local_photos.append(str(Path(p)))
            continue
        low = p.lower()
        if low.startswith("http://") or low.startswith("https://") or p.startswith("//"):
            # try to download
            local = download_image(p if not p.startswith("//") else ("https:" + p))
            if local:
                local_photos.append(local)
            else:
                logging.warning("Skipping image (could not download): %s", p)
        else:
            # treat as local path
            if Path(p).exists():
                local_photos.append(str(Path(p)))
            else:
                logging.warning("Skipping image (local file missing): %s", p)

    ok = False
    if not local_photos:
        logging.info("No images resolved — sending text message.")
        ok = send_text(CHAT_ID, caption)
    else:
        # Upload each image individually (first with caption)
        for i, lp in enumerate(local_photos):
            if i == 0:
                logging.info("Uploading first image with caption: %s", lp)
                ok = send_photo_upload(CHAT_ID, lp, caption=caption)
            else:
                logging.info("Uploading image without caption: %s", lp)
                ok = send_photo_upload(CHAT_ID, lp, caption=None)
            if not ok:
                logging.error("Failed uploading image: %s", lp)
                # continue to try remaining images
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
