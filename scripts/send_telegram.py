#!/usr/bin/env python3
"""
scripts/send_telegram.py

Telegram poster for article JSON.

Changes in this version:
- If 'hashtags' missing, auto-generate up to 4 tags from the title/excerpt.
- When multiple image URLs are provided: try sendMediaGroup; if it fails, fallback to sending each photo individually.
- Logs API responses (helpful for debugging).
"""
import os
import sys
import json
import logging
from pathlib import Path
import requests
import re
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


def normalize_token(t):
    s = re.sub(r'[^0-9A-Za-z]+', ' ', str(t)).strip().lower()
    return s


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


def send_text(chat_id, text):
    url = f"{API_BASE}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=30)
    logging.info("sendMessage status: %s", r.status_code)
    if not r.ok:
        logging.error("sendMessage response: %s", r.text)
    return r.ok


def send_photo(chat_id, photo, caption=None):
    url = f"{API_BASE}/sendPhoto"
    if Path(photo).exists():
        with open(photo, "rb") as fh:
            files = {"photo": fh}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            r = requests.post(url, data=data, files=files, timeout=60)
    else:
        data = {"chat_id": chat_id, "photo": photo}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        r = requests.post(url, json=data, timeout=30)
    logging.info("sendPhoto status: %s", r.status_code)
    if not r.ok:
        logging.error("sendPhoto response: %s", r.text)
    return r.ok


def send_media_group(chat_id, photos, caption=None):
    url = f"{API_BASE}/sendMediaGroup"
    media = []
    for i, p in enumerate(photos):
        item = {"type": "photo", "media": p}
        if i == 0 and caption:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media.append(item)
    r = requests.post(url, json={"chat_id": chat_id, "media": media}, timeout=30)
    logging.info("sendMediaGroup status: %s", r.status_code)
    if not r.ok:
        logging.error("sendMediaGroup response: %s", r.text)
    return r.ok


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

    ok = False
    if not photos:
        logging.info("No images provided — sending text message.")
        ok = send_text(CHAT_ID, caption)
    elif len(photos) == 1:
        logging.info("One image provided — sending photo with caption.")
        ok = send_photo(CHAT_ID, photos[0], caption=caption)
    else:
        logging.info("Multiple images provided (%d) — trying media group.", len(photos))
        # separate local vs remote
        local_paths = [p for p in photos if Path(p).exists()]
        remote_urls = [p for p in photos if not Path(p).exists()]

        # if some local files exist, upload individually (first with caption)
        if local_paths and remote_urls:
            logging.info("Mixed local and remote images — uploading individually.")
            for i, p in enumerate(photos):
                if i == 0:
                    ok = send_photo(CHAT_ID, p, caption=caption)
                else:
                    ok = send_photo(CHAT_ID, p, caption=None)
                if not ok:
                    logging.error("Failed uploading image: %s", p)
                    break
        elif local_paths:
            logging.info("All images are local — uploading individually.")
            for i, p in enumerate(photos):
                if i == 0:
                    ok = send_photo(CHAT_ID, p, caption=caption)
                else:
                    ok = send_photo(CHAT_ID, p, caption=None)
                if not ok:
                    logging.error("Failed uploading local image: %s", p)
                    break
        else:
            # all remote URLs — try media group first
            ok = send_media_group(CHAT_ID, photos, caption=caption)
            if not ok:
                logging.warning("media group failed — falling back to individual sends")
                for i, p in enumerate(photos):
                    if i == 0:
                        ok = send_photo(CHAT_ID, p, caption=caption)
                    else:
                        ok = send_photo(CHAT_ID, p, caption=None)
                    if not ok:
                        logging.error("Failed sending photo URL: %s", p)
                        break

    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
