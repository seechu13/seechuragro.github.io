#!/usr/bin/env python3
import sys
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE_URL = "https://seechuragro.in"
OUTPUT_JSON = "social_new.json"
MAX_IMAGES = 4
ALLOWED_EXT = (".jpg", ".jpeg", ".png", ".webp")


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h1 = False
        self.in_p = False
        self.title = ""
        self.paragraphs = []
        self.images = []
        self.meta_description = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self.in_h1 = True
        elif tag == "p":
            self.in_p = True
        elif tag == "img":
            src = attrs.get("src", "")
            if src.lower().endswith(ALLOWED_EXT):
                self.images.append(src)
        elif tag == "meta":
            if attrs.get("name") == "description":
                self.meta_description = attrs.get("content", "")

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False
        elif tag == "p":
            self.in_p = False

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self.in_h1 and not self.title:
            self.title = text
        elif self.in_p:
            self.paragraphs.append(text)


def extract_hashtags(text):
    words = re.findall(r"[A-Za-z]{4,}", text.lower())
    stop = {
        "this","that","with","from","your","about","their","there",
        "which","where","while","these","those","into","using","used"
    }
    tags = []
    for w in words:
        if w in stop:
            continue
        tag = "#" + w
        if tag not in tags:
            tags.append(tag)
        if len(tags) >= 10:
            break
    return tags


def main(article_path):
    html = Path(article_path).read_text(encoding="utf-8", errors="ignore")

    parser = ArticleParser()
    parser.feed(html)

    if not parser.title:
        raise SystemExit("❌ Could not extract <h1> title")

    excerpt = (
        parser.meta_description
        or " ".join(parser.paragraphs[:2])
    ).strip()

    images = []
    for src in parser.images:
        full = src if src.startswith("http") else urljoin(BASE_URL + "/", src.lstrip("/"))
        if full not in images:
            images.append(full)
        if len(images) >= MAX_IMAGES:
            break

    article_slug = Path(article_path).stem
    article_url = f"{BASE_URL}/articles/{article_slug}.html"

    hashtags = extract_hashtags(parser.title + " " + excerpt)

    social = {
        "title": parser.title,
        "excerpt": excerpt,
        "url": article_url,
        "images": images,
        "hashtags": hashtags
    }

    Path(OUTPUT_JSON).write_text(
        json.dumps(social, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("✅ social_new.json generated")
    print(json.dumps(social, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: generate_social_json.py <article.html>")
    main(sys.argv[1])
