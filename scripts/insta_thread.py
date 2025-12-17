#!/usr/bin/env python3
"""
Generate Instagram assets + Threads-ready threads.json
Rules enforced:
- NEVER include logo or global images
- Use ONLY images inside the article's own assets folder
- Instagram: up to 10 images
- Threads: up to 4 images
- Threads caption: meaningful excerpt, clickable URL, proper hashtags
"""

import sys
import json
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOCIAL_INSTA_DIR = ROOT / "social" / "insta" / "images"
THREADS_JSON = ROOT / "threads.json"

INSTAGRAM_MAX = 10
THREADS_MAX = 4

THREADS_HASHTAGS = [
    "#aeroponics",
    "#futurefarming",
    "#agritech",
    "#sustainablefarming",
]


def die(msg):
    raise RuntimeError(msg)


def clean_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def resize_for_instagram(src: Path, dst: Path):
    img = Image.open(src).convert("RGB")
    img.thumbnail((1080, 1080), Image.LANCZOS)
    img.save(dst, format="JPEG", quality=90)


def extract_article_images(article_html: Path):
    soup = BeautifulSoup(article_html.read_text(encoding="utf-8", errors="ignore"), "html.parser")

    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src:
            continue

        # Only allow article-local assets
        if not src.startswith("/assets/articles/"):
            continue

        img_path = ROOT / src.lstrip("/")
        if img_path.exists():
            images.append(img_path)

    return images


def extract_texts(article_html: Path):
    soup = BeautifulSoup(article_html.read_text(encoding="utf-8", errors="ignore"), "html.parser")

    title = soup.find("h1")
    subtitle = soup.find("p", class_="subtitle")

    title_text = title.get_text(strip=True) if title else ""
    excerpt = subtitle.get_text(strip=True) if subtitle else ""

    return title_text, excerpt


def build_threads_caption(title, excerpt, url):
    parts = []

    if excerpt:
        parts.append(excerpt)

    parts.append("")
    parts.append("Read the full article:")
    parts.append(url)
    parts.append("")
    parts.append(" ".join(THREADS_HASHTAGS))

    return "\n".join(parts).strip()


def main(article_path: str):
    article_path = article_path.strip()
    article_html = ROOT / article_path

    if not article_html.exists():
        die(f"Article not found: {article_path}")

    # Clear Instagram images every run
    clean_dir(SOCIAL_INSTA_DIR)

    images = extract_article_images(article_html)
    if not images:
        die("No resolvable article images found")

    title, excerpt = extract_texts(article_html)

    article_slug = article_html.stem
    article_url = f"https://seechuragro.in/articles/{article_html.name}"

    # --- Instagram images ---
    insta_images = images[:INSTAGRAM_MAX]
    for idx, img in enumerate(insta_images, start=1):
        out = SOCIAL_INSTA_DIR / f"{idx:02d}.jpg"
        resize_for_instagram(img, out)

    print("✅ Instagram assets generated")

    # --- Threads JSON ---
    threads_images = images[:THREADS_MAX]

    threads_data = {
        "title": title,
        "caption": build_threads_caption(title, excerpt, article_url),
        "images": [str(p.relative_to(ROOT)) for p in threads_images],
        "url": article_url,
    }

    THREADS_JSON.write_text(json.dumps(threads_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("✅ threads.json generated (Threads-ready)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        die("Usage: python insta_thread.py <article_html_path>")
    main(sys.argv[1])
