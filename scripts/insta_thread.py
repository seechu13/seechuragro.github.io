#!/usr/bin/env python3
"""
FINAL insta_thread.py (SIMPLIFIED & LOCKED)

Instagram:
- Generates resized images in social/insta/images/
- Generates long caption with dynamic hashtags

Threads:
- Generates threads.json (caption ONLY, no hashtags)
- Caption <= 250 chars TOTAL (URL included)

Telegram:
- Will reuse Instagram images (no separate Threads images)
"""

import sys
import json
import shutil
import re
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image

# ---------------- CONFIG ----------------

ROOT = Path(__file__).resolve().parents[1]

INSTA_IMG_DIR = ROOT / "social" / "insta" / "images"
INSTA_CAPTION_FILE = ROOT / "social" / "insta" / "caption.txt"
THREADS_JSON = ROOT / "threads.json"

INSTAGRAM_MAX_IMAGES = 10
THREADS_CHAR_LIMIT = 250
IMAGE_SIZE = (1080, 1080)

INSTAGRAM_FALLBACK_HASHTAGS = [
    "#seechuragro",
    "#smartfarming",
    "#sustainableagriculture",
]

# --------------------------------------


def die(msg):
    raise RuntimeError(msg)


def reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def resize_image_square(src: Path, dst: Path):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize(IMAGE_SIZE, Image.LANCZOS)
    img.save(dst, "JPEG", quality=90)


def extract_article_data(article_html: Path):
    soup = BeautifulSoup(
        article_html.read_text(encoding="utf-8", errors="ignore"),
        "html.parser",
    )

    title = soup.find("h1")
    subtitle = soup.find("p", class_="subtitle")

    title_text = title.get_text(strip=True) if title else ""
    excerpt = subtitle.get_text(strip=True) if subtitle else ""

    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()

        if not (
            src.startswith("/assets/articles/")
            or src.startswith("assets/articles/")
        ):
            continue

        img_path = ROOT / src.lstrip("/")
        if img_path.exists():
            images.append(img_path)

    return title_text, excerpt, images


def generate_instagram_hashtags(title: str):
    words = re.findall(r"[a-zA-Z]{4,}", title.lower())
    tags = []
    for w in words:
        tag = f"#{w}"
        if tag not in tags:
            tags.append(tag)
        if len(tags) >= 6:
            break
    return tags + INSTAGRAM_FALLBACK_HASHTAGS


def sentence_safe_trim(text: str, max_len: int):
    if len(text) <= max_len:
        return text
    trimmed = text[:max_len]
    for sep in [". ", "। ", "; ", ", "]:
        if sep in trimmed:
            return trimmed.rsplit(sep, 1)[0] + sep.strip()
    return trimmed.rsplit(" ", 1)[0]


def build_threads_caption(excerpt: str, url: str):
    static = f"\n\n{url}"
    available = THREADS_CHAR_LIMIT - len(static)
    if available <= 30:
        die("Threads caption budget too small")
    body = sentence_safe_trim(excerpt, available)
    return f"{body}\n\n{url}"


def main(article_path: str):
    article_html = ROOT / article_path.strip()
    if not article_html.exists():
        die(f"Article not found: {article_path}")

    title, excerpt, images = extract_article_data(article_html)
    if not images:
        die("No valid article images found")

    article_url = f"https://seechuragro.in/articles/{article_html.name}"

    # -------- Instagram --------
    reset_dir(INSTA_IMG_DIR)

    for idx, img in enumerate(images[:INSTAGRAM_MAX_IMAGES], start=1):
        resize_image_square(img, INSTA_IMG_DIR / f"{idx:02d}.jpg")

    insta_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{article_url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(generate_instagram_hashtags(title))
    )

    INSTA_CAPTION_FILE.write_text(insta_caption, encoding="utf-8")
    print("✅ Instagram assets generated")

    # -------- Threads (caption only) --------
    threads_data = {
        "title": title,
        "caption": build_threads_caption(excerpt, article_url),
        "url": article_url,
    }

    THREADS_JSON.write_text(
        json.dumps(threads_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("✅ threads.json generated")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        die("Usage: python insta_thread.py <article_html_path>")
    main(sys.argv[1])
