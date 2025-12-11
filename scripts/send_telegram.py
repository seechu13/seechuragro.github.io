#!/usr/bin/env python3
"""
Minimal Telegram poster for article JSON.

Usage:
  python3 scripts/send_telegram.py path/to/article.json

Env (in Actions):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  BASE_URL (optional)
"""
import os, sys, json, logging
from pathlib import Path
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

if not BOT_TOKEN or not CHAT_ID:
    logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment.")
    sys.exit(2)

def hashtags_to_text(h):
    if not h:
        return ""
    if isinstance(h, list):
        tags = [str(x).strip() for x in h if str(x).strip()]
    else:
        s = str(h).strip()
        tags = [p.strip() for p in (s.split(",") if "," in s else s.split()) if p.strip()]
    tags = [t.lstrip('#') for t in tags]
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
    hashtags_raw = data.get("hashtags") or data.get("tags") or ""

    url = build_url(raw_url, slug)
    tags_text = hashtags_to_text(hashtags_raw)

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
        logging.info("Multiple images provided (%d) — sending media group or fallback uploads.", len(photos))
        local_paths = [p for p in photos if Path(p).exists()]
        if local_paths:
            for i, p in enumerate(photos):
                if i == 0:
                    ok = send_photo(CHAT_ID, p, caption=caption)
                else:
                    ok = send_photo(CHAT_ID, p, caption=None)
                if not ok:
                    break
        else:
            ok = send_media_group(CHAT_ID, photos, caption=caption)
    sys.exit(0 if ok else 3)

if __name__ == "__main__":
    main()
