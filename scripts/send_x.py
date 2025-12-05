#!/usr/bin/env python3
"""
scripts/send_x.py — text-only X posting (v2) with BASE_URL fallback.

Behavior:
- Composes a caption from title + excerpt and ALWAYS appends an absolute article URL.
- If JSON provides a relative URL or only a slug, this script builds an absolute URL
  using BASE_URL environment variable (default: https://seechuragro.in).
- Uses tweepy.Client.create_tweet (v2) to post text-only tweets (no media).
- Exit codes:
    0 = success
    2 = usage / missing args
    3 = post failed
"""

import os
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

try:
    import tweepy
except Exception:
    logging.error("tweepy library not installed. Install in workflow or runner environment.")
    sys.exit(2)

# Max tweet length we allow for composing/truncation (conservative)
MAX_TWEET_LEN = 2800

# Credentials read from env (these must be set as GitHub Secrets in workflow)
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

# Base URL used to build absolute URLs when JSON contains relative paths or slugs
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')


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
        # if starts with // (protocol relative), add https:
        if s.startswith("//"):
            return f"https:{s}"
        # otherwise treat as relative path
        return f"{BASE_URL}/{s.lstrip('/')}"
    # if no raw_url, try slug
    if slug:
        return f"{BASE_URL}/{str(slug).lstrip('/')}"
    return ""


def compose_caption(title: str, excerpt: str, url: str) -> str:
    """
    Compose text from title + excerpt, ensure URL appended.
    Truncate the combined text if necessary to keep under MAX_TWEET_LEN.
    """
    parts = []
    if title:
        parts.append(title.strip())
    if excerpt:
        parts.append(excerpt.strip())
    body = "\n\n".join(parts).strip()

    # reserved room for newline + url if url present
    reserved = (1 + len(url)) if url else 0

    if reserved + len(body) <= MAX_TWEET_LEN:
        text = body
    else:
        allowed_body_len = max(0, MAX_TWEET_LEN - reserved)
        if allowed_body_len > 3:
            text = body[:allowed_body_len - 3].rstrip() + "..."
        else:
            text = body[:allowed_body_len].rstrip()

    if url:
        if text:
            text = f"{text}\n{url}"
        else:
            text = url
    return text


def post_text_v2(text: str) -> bool:
    """
    Post text-only tweet via tweepy.Client.create_tweet.
    Returns True if successful.
    """
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

    title = data.get("title", "") or ""
    excerpt = data.get("excerpt") or data.get("description") or ""
    raw_url = data.get("url") or data.get("link") or ""
    slug = data.get("slug") or ""

    absolute_url = build_absolute_url(raw_url, slug)

    caption = compose_caption(title, excerpt, absolute_url)

    logging.info("Caption preview (truncated to %d chars):", MAX_TWEET_LEN)
    # log a short preview but avoid dumping huge text into logs
    logging.info("%s", caption[:2000] + ("..." if len(caption) > 2000 else ""))

    ok = post_text_v2(caption)
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
