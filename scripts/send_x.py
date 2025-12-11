#!/usr/bin/env python3
"""
scripts/send_x.py — Post hashtags + article URL to X (text-only) with BASE_URL fallback.

Behavior:
- Prefer 'hashtags' field in JSON (list or string).
- If missing, auto-generate up to MAX_TAGS hashtags from title + excerpt (alphanumeric, >3 chars).
- Posts hashtags followed by the absolute article URL.
- Ensures combined text fits within MAX_TWEET_LEN (truncates hashtags list if needed).
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

# Fallback base URL used to build absolute URLs
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')

# Hashtag generation limits and tweet length
MAX_TAGS = 8
MIN_WORD_LEN = 4  # only use words longer than this for tag generation
MAX_TWEET_LEN = 2800  # conservative upper bound (adjust if you want stricter 280 char rule)

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
        out = []
        for item in raw:
            if not item:
                continue
            s = str(item).strip()
            if s.startswith("#"):
                out.append("#" + normalize_hashtag_token(s.lstrip("#")))
            else:
                parts = re.split(r'[\s,]+', s)
                for p in parts:
                    p2 = p.strip()
                    if p2:
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
        s = str(raw).strip()
        parts = re.split(r'[\s,]+', s)
        res = []
        for p in parts:
            if not p:
                continue
            res.append("#" + normalize_hashtag_token(p.lstrip("#")))
        seen = set()
        out = []
        for h in res:
            if h.lower() not in seen:
                seen.add(h.lower())
                out.append(h)
        return out

def build_absolute_url(raw_url: str, slug: str) -> str:
    """
    Return an absolute https URL to include in the tweet.
    raw_url: value from JSON 'url' or 'link' (may be empty or relative).
    slug: value from JSON 'slug' (may be empty).
    """
    if raw_url:
        s = raw_url.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
        if s.startswith("//"):
            return f"https:{s}"
        return f"{BASE_URL}/{s.lstrip('/')}"
    if slug:
        return f"{BASE_URL}/{str(slug).lstrip('/')}"
    return ""

def build_hashtags_list(article):
    raw_tags = article.get("hashtags") or article.get("tags") or article.get("hashtag")
    tags = extract_hashtags_field(raw_tags)
    if not tags:
        title = article.get("title", "") or ""
        excerpt = article.get("excerpt", "") or article.get("description", "") or ""
        tags = generate_hashtags(title, excerpt)
    if not tags:
        tags = ["#seechuragro"]
    # limit to MAX_TAGS
    return tags[:MAX_TAGS]

def assemble_text_with_url(tags_list, url):
    """
    Build final text: space-joined hashtags + ' ' + url.
    Ensure length <= MAX_TWEET_LEN by dropping trailing hashtags if necessary.
    """
    if not url:
        # if no url, just join tags
        base = " ".join(tags_list)
        return base[:MAX_TWEET_LEN]
    # start with full list and drop from end until fits
    tags = list(tags_list)
    while tags:
        text = " ".join(tags) + " " + url
        if len(text) <= MAX_TWEET_LEN:
            return text
        # drop last tag and retry
        tags.pop()
    # if no tags fit, return just the url (should fit)
    return url[:MAX_TWEET_LEN]

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

    raw_url = data.get("url") or data.get("link") or ""
    slug = data.get("slug") or ""
    absolute_url = build_absolute_url(raw_url, slug)

    tags_list = build_hashtags_list(data)
    final_text = assemble_text_with_url(tags_list, absolute_url)

    logging.info("Final text to post (len=%d): %s", len(final_text), final_text[:2000] + ("..." if len(final_text) > 2000 else ""))

    ok = post_text_v2(final_text)
    sys.exit(0 if ok else 3)

if __name__ == "__main__":
    main()
