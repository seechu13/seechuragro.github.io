#!/usr/bin/env python3
"""
insta_thread.py — FINAL, FIXED

Instagram:
- Save up to 10 images
- Save caption to social/insta/caption.txt

Threads:
- Max 4 images
- Caption <= 500 chars
- Save ONLY to threads.json (repo root)

This file is used by:
- Auto workflow
- Manual workflow
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

    html_file = ROOT / article_path
    if not html_file.exists():
        raise RuntimeError(f"Article not found: {article_path}")

    html = html_file.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    # ---------- TITLE ----------
    title = soup.title.text.replace(" - Seechur Agro", "").strip()

    # ---------- EXCERPT ----------
    subtitle = soup.select_one("p.subtitle")
    if not subtitle:
        raise RuntimeError("Missing <p class='subtitle'> in article")
    excerpt = subtitle.get_text(strip=True)

    # ---------- URL ----------
    slug = html_file.name
    url = f"https://seechuragro.in/articles/{slug}"

    # ---------- COLLECT IMAGE SRCs ----------
    srcs = []

    hero = soup.select_one(".article-hero img")
    if hero and hero.get("src"):
        srcs.append(hero["src"])

    for img in soup.select("article img"):
        s = img.get("src")
        if s and s not in srcs:
            srcs.append(s)

    if not srcs:
        raise RuntimeError("No image src found in article HTML")

    # ---------- RESOLVE IMAGE FILES ----------
    resolved = []
    for src in srcs:
        clean = src.lstrip("/")
        p = ROOT / clean
        if p.exists():
            resolved.append(p)

    if not resolved:
        raise RuntimeError("No resolvable image files found on disk")

    # ---------- INSTAGRAM ----------
    reset_instagram_dirs()

    for idx, p in enumerate(resolved[:MAX_IG_IMAGES], start=1):
        resize_and_save(p, INSTA_IMG_DIR / f"{idx:02}.jpg")

    insta_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(f"#{h}" for h in INSTAGRAM_HASHTAGS)
    )

    (INSTA_DIR / "caption.txt").write_text(insta_caption, encoding="utf-8")

    # ---------- THREADS ----------
    threads_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read more on our website (link in bio).\n\n"
        + " ".join(f"#{h}" for h in THREADS_HASHTAGS)
    )

    threads_caption = shorten_for_threads(
        threads_caption, THREADS_CHAR_LIMIT
    )

    threads_images = [
        "/" + p.as_posix()
        for p in resolved[:MAX_THREADS_IMAGES]
    ]

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
