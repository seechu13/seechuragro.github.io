#!/usr/bin/env python3
"""
insta_thread.py — FINAL (legacy-safe)

Supports:
- /assets/articles/...
- /images/articles/...
- full https://seechuragro.in/... URLs
- single-image articles
"""

import json
import sys
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image
from urllib.parse import urlparse

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
    "microgreens",
    "urbanfarming",
    "hydroponics",
    "smartfarming",
    "seechuragro",
]

THREADS_HASHTAGS = [
    "microgreens",
    "futurefarming",
    "agritech",
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


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    return cut.rsplit(" ", 1)[0] + "..."


def resolve_image_path(src: str) -> Path | None:
    """
    Try all known legacy + new image locations
    """
    if not src:
        return None

    # Strip domain if full URL
    if src.startswith("http"):
        src = urlparse(src).path

    candidates = [
        ROOT / src.lstrip("/"),
        ROOT / "assets" / src.lstrip("/"),
        ROOT / "images" / src.lstrip("/"),
    ]

    for p in candidates:
        if p.exists():
            return p

    return None


def main(article_path: str):
    html_file = ROOT / article_path.strip()
    if not html_file.exists():
        raise RuntimeError(f"Article not found: {article_path}")

    soup = BeautifulSoup(
        html_file.read_text(encoding="utf-8", errors="ignore"),
        "html.parser",
    )

    # ---------- TITLE ----------
    title = soup.title.text.replace(" - Seechur Agro", "").strip()

    # ---------- EXCERPT ----------
    subtitle = soup.select_one("p.subtitle")
    if not subtitle:
        raise RuntimeError("Missing <p class='subtitle'>")
    excerpt = subtitle.get_text(strip=True)

    # ---------- URL ----------
    url = f"https://seechuragro.in/articles/{html_file.name}"

    # ---------- IMAGE SOURCES ----------
    srcs = []

    hero = soup.select_one(".article-hero img")
    if hero and hero.get("src"):
        srcs.append(hero["src"])

    for img in soup.select("article img"):
        s = img.get("src")
        if s and s not in srcs:
            srcs.append(s)

    resolved = []
    for src in srcs:
        p = resolve_image_path(src)
        if p:
            resolved.append(p)

    if not resolved:
        raise RuntimeError(
            "No resolvable image files found — check legacy image paths"
        )

    # ---------- INSTAGRAM ----------
    reset_instagram_dirs()

    for i, img in enumerate(resolved[:MAX_IG_IMAGES], start=1):
        resize_and_save(img, INSTA_IMG_DIR / f"{i:02}.jpg")

    insta_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(f"#{h}" for h in INSTAGRAM_HASHTAGS)
    )

    (INSTA_DIR / "caption.txt").write_text(insta_caption, encoding="utf-8")

    # ---------- THREADS ----------
    threads_caption = shorten(
        f"{title}\n\n{excerpt}\n\nRead more (link in bio).\n\n"
        + " ".join(f"#{h}" for h in THREADS_HASHTAGS),
        THREADS_CHAR_LIMIT,
    )

    threads_data = {
        "title": title,
        "url": url,
        "caption": threads_caption,
        "images": ["/" + p.as_posix() for p in resolved[:MAX_THREADS_IMAGES]],
    }

    THREADS_JSON.write_text(json.dumps(threads_data, indent=2), encoding="utf-8")

    print("✅ Instagram assets generated")
    print("✅ threads.json generated")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 insta_thread.py <article_html>")
        sys.exit(1)

    main(sys.argv[1])
