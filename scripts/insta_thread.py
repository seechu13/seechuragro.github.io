#!/usr/bin/env python3
"""
insta_thread.py — FINAL (Threads via JSON)

Instagram:
- Save up to 10 images
- Save long caption to social/insta/caption.txt

Threads:
- Generate caption ≤ 500 chars
- Pick first 4 images
- Save ONLY to threads.json (no folders, no images written)

Used by:
- Auto workflow
- Manual workflow
- Telegram Threads sender
"""

import json
import sys
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image

# ---------------- CONFIG ----------------

MAX_IG_IMAGES = 10
MAX_THREADS_IMAGES = 4
THREADS_CHAR_LIMIT = 500
IMG_SIZE = (1080, 1080)

ROOT = Path(".")
INSTA_DIR = ROOT / "social" / "insta"
INSTA_IMG_DIR = INSTA_DIR / "images"
THREADS_JSON = ROOT / "threads.json"

INSTAGRAM_HASHTAGS = [
    "aeroponics",
    "hydroponics",
    "smartfarming",
    "verticalfarming",
    "controlledenvironment",
    "seechuragro",
]

THREADS_HASHTAGS = [
    "aeroponics",
    "futurefarming",
    "agritech",
    "sustainableagriculture",
]

# ----------------------------------------


def reset_instagram_dirs():
    if INSTA_DIR.exists():
        shutil.rmtree(INSTA_DIR)
    INSTA_IMG_DIR.mkdir(parents=True, exist_ok=True)


def resize_and_save(src: Path, dst: Path):
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail(IMG_SIZE, Image.LANCZOS)
        canvas = Image.new("RGB", IMG_SIZE, (255, 255, 255))
        offset = ((IMG_SIZE[0] - im.width) // 2, (IMG_SIZE[1] - im.height) // 2)
        canvas.paste(im, offset)
        canvas.save(dst, "JPEG", quality=90, optimize=True)


def shorten_for_threads(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    return cut.rsplit(" ", 1)[0] + "..."


def main(article_path: str):
    article_path = article_path.strip()
    html = Path(article_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    # -------- TITLE --------
    title = soup.title.text.replace(" - Seechur Agro", "").strip()

    # -------- EXCERPT --------
    subtitle = soup.select_one("p.subtitle")
    if not subtitle:
        raise RuntimeError("Missing <p class='subtitle'> in article")
    excerpt = subtitle.get_text(strip=True)

    # -------- URL --------
    slug = Path(article_path).name
    url = f"https://seechuragro.in/articles/{slug}"

    # -------- IMAGES --------
    images = []

    hero = soup.select_one(".article-hero img")
    if hero and hero.get("src"):
        images.append(hero["src"])

    for img in soup.select("article img"):
        src = img.get("src")
        if src and src not in images:
            images.append(src)

    if not images:
        raise RuntimeError("No images found in article")

    # -------- INSTAGRAM --------
    reset_instagram_dirs()

    ig_images = images[:MAX_IG_IMAGES]
    for idx, src in enumerate(ig_images, start=1):
        src_path = ROOT / src.lstrip("/")
        if not src_path.exists():
            continue
        resize_and_save(src_path, INSTA_IMG_DIR / f"{idx:02}.jpg")

    insta_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(f"#{h}" for h in INSTAGRAM_HASHTAGS)
    )

    (INSTA_DIR / "caption.txt").write_text(insta_caption, encoding="utf-8")

    # -------- THREADS --------
    threads_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read more on our website (link in bio).\n\n"
        + " ".join(f"#{h}" for h in THREADS_HASHTAGS)
    )

    threads_caption = shorten_for_threads(
        threads_caption, THREADS_CHAR_LIMIT
    )

    threads_images = images[:MAX_THREADS_IMAGES]

    threads_data = {
        "title": title,
        "url": url,
        "caption": threads_caption,
        "images": threads_images,
    }

    THREADS_JSON.write_text(
        json.dumps(threads_data, indent=2),
        encoding="utf-8"
    )

    print("✅ Instagram assets generated")
    print("✅ threads.json generated (Threads-ready)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 insta_thread.py <article_html_path>")
        sys.exit(1)

    main(sys.argv[1])
