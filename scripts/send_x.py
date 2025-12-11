#!/usr/bin/env python3
"""
scripts/send_x.py — Post ONLY hashtags to X (text-only) with BASE_URL fallback.

Behavior:
- Prefer 'hashtags' field in JSON (list or string).
- If missing, auto-generate up to 5 hashtags from title + excerpt (alphanumeric, >3 chars).
- Posts a single line made of hashtags (space-separated).
- Uses tweepy.Client.create_tweet to post.
Exit codes:
  0 = success
  2 = usage / missing args
  3 = post failed
"""

import os
import sys
import json
import logging
from pathlib import Path
import re

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

try:
    import tweepy
except Exception:
    logging.error("tweepy library not installed. Install in workflow or runner environment.")
    sys.exit(2)

# Credentials from env (must be set)
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

# Fallback base URL (not used for hashtags but kept for consistency)
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')

# Hashtag generation limits
MAX_TAGS = 5
MIN_WORD_LEN = 4  # only use words longer than this for tag generation

def normalize_hashtag_token(tok: str) -> str:
    # keep only alphanumeric, lowercase
    t = re.sub(r'[^0-9A-Za-z]', '', tok)
    return t.lower()

def generate_hashtags(title: str, excerpt: str, max_tags=MAX_TAGS):
    words = (title + " " + excerpt).split()
    tags = []
    for w in words:
        t = normalize_hashtag_token(w)
        if len(t) >= MIN_WORD_LEN and not t.isdigit():
            if t not in tags:
                tags.append(t)
        if len(tags) >= max_tags:
            break
    return ["#" + t for t in tags]

def extract_hashtags_field(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        # sanitize content, drop empties
        out = []
        for item in raw:
            if not item:
                continue
            s = str(item).strip()
            if s.startswith("#"):
                out.append(s)
            else:
                # convert spaces or commas into single-hashtag tokens
                parts = re.split(r'[\s,]+', s)
                for p in parts:
                    p2 = p.strip()
                    if p2:
                        if p2.startswith("#"):
                            out.append(p2)
                        else:
                            out.append("#" + normalize_hashtag_token(p2))
        # dedupe while preserving order
        seen = set()
        res = []
        for h in out:
            if h.lower() not in seen:
                seen.add(h.lower())
                res.append(h)
        return res
    else:
        # string
        s = str(raw).strip()
        parts = re.split(r'[\s,]+', s)
        res = []
        for p in parts:
            if not p:
                continue
            if p.startswith("#"):
                token = "#" + normalize_hashtag_token(p.lstrip("#"))
                res.append(token)
            else:
                token = "#" + normalize_hashtag_token(p)
                res.append(token)
        # dedupe
        seen = set()
        out = []
        for h in res:
            if h.lower() not in seen:
                seen.add(h.lower())
                out.append(h)
        return out

def build_hashtag_text(article):
    raw_tags = article.get("hashtags") or article.get("tags") or article.get("hashtag")
    tags = extract_hashtags_field(raw_tags)
    if not tags:
        title = article.get("title", "") or ""
        excerpt = article.get("excerpt", "") or article.get("description", "") or ""
        tags = generate_hashtags(title, excerpt)
    # ensure at least one tag; fallback to site name
    if not tags:
        tags = ["#seechuragro"]
    # limit
    return " ".join(tags[:MAX_TAGS])

def post_text_v2(text: str) -> bool:
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        logging.error("Missing one or more X credentials in environment.")
        return False
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET,
            wait_on_rate_limit=True
        )
        resp = client.create_tweet(text=text)
        logging.info("v2 tweet response: %s", getattr(resp, "data", resp))
        return True
    except Exception as e:
        logging.error("v2 post failed: %s", e)
        return False

def usage_and_exit():
    print("Usage: send_x.py path/to/article.json")
    sys.exit(2)

def main():
    if len(sys.argv) < 2:
        usage_and_exit()

    jf_path = Path(sys.argv[1])
    if not jf_path.exists():
        logging.error("JSON file not found: %s", jf_path)
        sys.exit(2)

    try:
        data = json.loads(jf_path.read_text(encoding="utf-8"))
    except Exception as e:
        logging.error("Failed to read/parse JSON: %s", e)
        sys.exit(2)

    hashtag_text = build_hashtag_text(data)
    logging.info("Hashtag text to post: %s", hashtag_text)

    ok = post_text_v2(hashtag_text)
    sys.exit(0 if ok else 3)

if __name__ == "__main__":
    main()
