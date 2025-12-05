#!/usr/bin/env python3
"""
scripts/send_x.py — text-only X posting (v2)
This script posts a text-only tweet using tweepy.Client.create_tweet.
It ALWAYS includes the article URL at the end of the text and will
truncate the title/excerpt if the combined length exceeds 2800 characters.

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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

try:
    import tweepy
except Exception:
    logging.error("tweepy library not installed. Install in workflow or runner environment.")
    sys.exit(2)

MAX_TWEET_LEN = 2800  # conservative cap (matches prior script)
# read credentials from env (set as repo secrets in GitHub Actions)
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

def compose_caption(title: str, excerpt: str, url: str) -> str:
    """
    Return text that contains title, excerpt, and URL.
    Ensure URL is preserved; truncate excerpt if needed to keep under MAX_TWEET_LEN.
    """
    parts = []
    if title:
        parts.append(title.strip())
    if excerpt:
        parts.append(excerpt.strip())
    body = "\n\n".join(parts).strip()

    # Always append the URL on its own line (if present)
    if url:
        # Reserve room for newline + url
        reserved = 1 + len(url)
    else:
        reserved = 0

    if reserved + len(body) <= MAX_TWEET_LEN:
        text = body
    else:
        # Need to truncate body to fit
        allowed_body_len = max(0, MAX_TWEET_LEN - reserved)
        # Simple truncation: keep the start of body and append ellipsis if trimmed
        if allowed_body_len > 3:
            text = body[:allowed_body_len - 3].rstrip() + "..."
        else:
            text = body[:allowed_body_len].rstrip()

    # If a URL exists, ensure it is appended separated by newline
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
        # resp may be a Response object; check for data or raise no-exception
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
    url = data.get("url") or data.get("link") or ""

    # If URL is relative path (local asset), do not try to resolve — we only embed absolute URLs.
    # If the JSON contains a relative path, it's fine — the script will include it as-is,
    # but typically you'll want a public absolute URL for readers to click.
    caption = compose_caption(title, excerpt, url)

    logging.info("Caption preview (truncated to %d chars):", MAX_TWEET_LEN)
    logging.info("%s", caption[:2000] + ("..." if len(caption) > 2000 else ""))

    ok = post_text_v2(caption)
    sys.exit(0 if ok else 3)

if __name__ == "__main__":
    main()
