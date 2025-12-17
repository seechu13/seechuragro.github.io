#!/usr/bin/env python3
"""
Generate Instagram + Threads assets from an article HTML.

Outputs:
- insta_thread.json
- social/insta/images/*.jpg
- social/insta/caption.txt
- social/threads/images/*.jpg
- social/threads/caption.txt

Rules:
- Same images for Insta & Threads
- Max 10 images
- Extract excerpt from <p class="subtitle">
- Overwrite old folders every run
"""

import json
import shutil
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image

MAX_IMAGES = 10
IMG_SIZE = (1080, 1080)

ROOT = Path(".")
OUT_BASE = ROOT / "social"
INSTA_DIR = OUT_BASE / "insta"
THREADS_DIR = OUT_BASE / "threads"
JSON_OUT = ROOT / "insta_thread.json"


INSTAGRAM_HASHTAGS = [
    "aeroponics",
    "hydroponics",
    "smartfarming",
    "verticalfarming",
    "controlledenvironment",
    "seechuragro",
]

THREADS_HASHTAGS = [
    "Aeroponics",
    "AgriTech",
    "SustainableFarming",
    "FutureOfFarming",
    "SeechurAgro",
]


def clean_dirs():
    for d in [INSTA_DIR, THREADS_DIR]:
        if d.exists():
            shutil.rmtree(d)
        (d / "images").mkdir(parents=True, exist_ok=True)


def resize_and_save(src: Path, dst: Path):
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail(IMG_SIZE, Image.LANCZOS)
        canvas = Image.new("RGB", IMG_SIZE, (255, 255, 255))
        offset = ((IMG_SIZE[0] - im.width) // 2, (IMG_SIZE[1] - im.height) // 2)
        canvas.paste(im, offset)
        canvas.save(dst, "JPEG", quality=90, optimize=True)


def main(article_path: str):
    article_path = article_path.strip()
    html = Path(article_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    # --- TITLE ---
    title = soup.title.text.replace(" - Seechur Agro", "").strip()

    # --- EXCERPT ---
    subtitle = soup.select_one("p.subtitle")
    if not subtitle:
        raise RuntimeError("Subtitle <p class='subtitle'> not found")
    excerpt = subtitle.get_text(strip=True)

    # --- URL ---
    slug = Path(article_path).name
    url = f"https://seechuragro.in/articles/{slug}"

    # --- IMAGES ---
    imgs = []
    hero = soup.select_one(".article-hero img")
    if hero and hero.get("src"):
        imgs.append(hero["src"])

    for img in soup.select("article img"):
        src = img.get("src")
        if src and src not in imgs:
            imgs.append(src)

    imgs = imgs[:MAX_IMAGES]
    if not imgs:
        raise RuntimeError("No images found in article")

    clean_dirs()

    image_names = []
    for idx, src in enumerate(imgs, start=1):
        src_path = ROOT / src.lstrip("/")
        if not src_path.exists():
            continue

        name = f"{idx:02}.jpg"
        for platform in [INSTA_DIR, THREADS_DIR]:
            resize_and_save(
                src_path,
                platform / "images" / name
            )
        image_names.append(name)

    # --- CAPTIONS ---
    insta_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(f"#{h}" for h in INSTAGRAM_HASHTAGS)
    )

    threads_caption = (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{url}\n"
        f"(Link also in bio 👇)\n\n"
        + " ".join(f"#{h}" for h in THREADS_HASHTAGS)
    )

    (INSTA_DIR / "caption.txt").write_text(insta_caption, encoding="utf-8")
    (THREADS_DIR / "caption.txt").write_text(threads_caption, encoding="utf-8")

    # --- JSON ---
    data = {
        "title": title,
        "excerpt": excerpt,
        "url": url,
        "images": image_names,
        "instagram_hashtags": INSTAGRAM_HASHTAGS,
        "threads_hashtags": THREADS_HASHTAGS,
    }

    JSON_OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print("✅ Insta + Threads assets generated successfully")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 insta_thread.py <article_html_path>")
        sys.exit(1)

    main(sys.argv[1])
