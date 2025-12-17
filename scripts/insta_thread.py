#!/usr/bin/env python3
import sys
import re
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
import requests

ROOT = Path(".")
INSTA_IMG_DIR = ROOT / "social" / "insta" / "images"
INSTA_CAPTION = ROOT / "social" / "insta" / "caption.txt"
THREADS_JSON = ROOT / "threads.json"

SITE_URL = "https://seechuragro.in"


# ---------- helpers ----------

def clean_dir(p: Path):
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


def download_image(url: str, out: Path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    out.write_bytes(r.content)


def resize_instagram(img_path: Path):
    with Image.open(img_path) as im:
        im = im.convert("RGB")
        im.thumbnail((1080, 1080), Image.LANCZOS)
        im.save(img_path, "JPEG", quality=92)


def extract_images(html: str):
    imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
    cleaned = []
    for i in imgs:
        if i.startswith("//"):
            i = "https:" + i
        elif i.startswith("/"):
            i = SITE_URL + i
        cleaned.append(i)
    return cleaned


def extract_meta(html: str, tag: str):
    m = re.search(
        rf'<meta name="{tag}" content="([^"]+)"', html, re.IGNORECASE
    )
    return m.group(1).strip() if m else ""


def extract_title(html: str):
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def build_instagram_caption(title, excerpt, url, hashtags):
    return (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        f"Read the full article:\n{url}\n"
        f"(Link also in bio 👆)\n\n"
        + " ".join(hashtags)
    )


def build_threads_caption(title, excerpt, url, hashtags):
    base = f"{title}\n\n{excerpt}\n\nRead more: link in bio"
    tagline = " ".join(h.lstrip("#") for h in hashtags)
    full = f"{base}\n\n{tagline}"
    return full[:430]


# ---------- main ----------

def main(article_path: str):
    html_path = Path(article_path)
    if not html_path.exists():
        raise RuntimeError(f"Article not found: {article_path}")

    html = html_path.read_text(encoding="utf-8", errors="ignore")

    title = extract_title(html)
    excerpt = extract_meta(html, "description")
    slug = html_path.stem
    url = f"{SITE_URL}/articles/{html_path.name}"

    hashtags = [
        "#seecureagro",
        "#smartfarming",
        "#sustainableagriculture",
        "#futureoffarming",
        "#agritech",
    ]

    images = extract_images(html)
    if not images:
        raise RuntimeError("No images found in article HTML")

    # ---------- INSTAGRAM ----------
    clean_dir(INSTA_IMG_DIR)

    local_images = []
    for idx, img_url in enumerate(images, start=1):
        out = INSTA_IMG_DIR / f"{idx:02d}.jpg"
        try:
            download_image(img_url, out)
            resize_instagram(out)
            local_images.append(out)
        except Exception:
            continue

    if not local_images:
        raise RuntimeError("No resolvable image files found on disk")

    insta_caption = build_instagram_caption(
        title, excerpt, url, hashtags
    )
    INSTA_CAPTION.write_text(insta_caption, encoding="utf-8")

    print("✅ Instagram assets generated")

    # ---------- THREADS ----------
    threads_payload = {
        "title": title,
        "caption": build_threads_caption(
            title, excerpt, url, hashtags
        ),
        "images": [str(p) for p in local_images[:4]],
        "url": url,
    }

    THREADS_JSON.write_text(
        json.dumps(threads_payload, indent=2),
        encoding="utf-8"
    )

    print("✅ threads.json generated (Threads-ready)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python insta_thread.py <article.html>")
    main(sys.argv[1])
