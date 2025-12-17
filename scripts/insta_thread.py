#!/usr/bin/env python3
"""
FINAL insta_thread.py (LOCKED)

Instagram:
- Long caption
- Dynamic hashtags
- Up to 10 images

Threads:
- NO hashtags
- Caption <= 250 chars TOTAL (URL included)
- Clickable URL
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


def reset_instagram_dir():
    if INSTA_IMG_DIR.exists():
        shutil.rmtree(INSTA_IMG_DIR)
    INSTA_IMG_DIR.mkdir(parents=True, exist_ok=True)


def resize_image(src: Path, dst: Path):
    img = Image.open(src).convert("RGB")
    img.thumbnail(IMAGE_SIZE, Image.LANCZOS)
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

        # STRICT: only article-local assets
        if not src.startswith("/assets/articles/"):
            continue

        img_path = ROOT / src.lstrip("/")
        if img_path.exists():
            images.append(img_path)

    return title_text, excerpt, images


def generate_instagram_hashtags(title: str):
    words = re.findall(r"[a-zA-Z]{4,}", title.lower())
    unique = []
    for w in words:
        tag = f"#{w}"
        if tag not in unique:
            unique.append(tag)
        if len(unique) >= 6:
            break

    return unique + INSTAGRAM_FALLBACK_HASHTAGS


def sentence_safe_trim(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text

    trimmed = text[:max_len]
    for sep in [". ", "। ", "; ", ", "]:
        if sep in trimmed:
            return trimmed.rsplit(sep, 1)[0] + sep.strip()

    return trimmed.rsplit(" ", 1)[0]


def build_threads_caption(excerpt: str, url: str) -> str:
    static_part = f"\n\n{url}"
    available = THREADS_CHAR_LIMIT - len(static_part)

    if available <= 30:
        die("Threads character budget too small")

    body = sentence_safe_trim(excerpt, available)
    return f"{body}\n\n{url}"


def main(article_path: str):
    article_path = article_path.strip()
    article_html = ROOT / article_path

    if not article_html.exists():
        die(f"Article not found: {article_path}")

    title, excerpt, images = extract_article_data(article_html)

    if not images:
        die("No valid article images found")

    article_url = f"https://seechuragro.in/articles/{article_html.name}"

    # ---------- INSTAGRAM ----------
    reset_instagram_dir()

    for idx, img in enumerate(images[:INSTAGRAM_MAX_IMAGES], start=1):
        out = INSTA_IMG_DIR / f"{idx:02d}.jpg"
        resize_image(img, out)

    insta_hashtags = generate_instagram_hashtags(title)

    insta_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{article_url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(insta_hashtags)
    )

    INSTA_CAPTION_FILE.write_text(insta_caption, encoding="utf-8")

    print("✅ Instagram assets generated")

    # ---------- THREADS ----------
    threads_caption = build_threads_caption(excerpt, article_url)

    threads_data = {
        "title": title,
        "caption": threads_caption,
        "images": [str(p.relative_to(ROOT)) for p in images[:4]],
        "url": article_url,
    }

    THREADS_JSON.write_text(
        json.dumps(threads_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("✅ threads.json generated (Threads-ready)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        die("Usage: python insta_thread.py <article_html_path>")

    main(sys.argv[1])
