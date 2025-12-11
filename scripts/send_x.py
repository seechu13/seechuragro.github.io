#!/usr/bin/env python3
"""
send_x.py — Post title/excerpt + article URL + up to 3 hashtags to X (text-only).
No threading, no replies.

Behavior:
- Final tweet: <title/excerpt (truncated)>\n<URL>\n#tag1 #tag2 #tag3
- Reserves space for t.co shortened URL (23 chars).
- Uses strict 280-char limit.
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
    logging.error("tweepy not installed.")
    sys.exit(2)

# Credentials from env
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")
BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')

# Limits
MAX_TAGS = 3
MIN_WORD_LEN = 4
MAX_TWEET_LEN = 280
URL_PLACEHOLDER_LEN = 23  # t.co length reserved

def normalize_hashtag_token(tok: str) -> str:
    return re.sub(r'[^0-9A-Za-z]', '', tok).lower()

def generate_hashtags(title: str, excerpt: str, max_tags=MAX_TAGS):
    words = (title + " " + excerpt).split()
    tags = []
    for w in words:
        t = normalize_hashtag_token(w)
        if len(t) >= MIN_WORD_LEN and not t.isdigit() and t not in tags:
            tags.append(t)
        if len(tags) >= max_tags:
            break
    return ["#" + t for t in tags]

def extract_hashtags_field(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r'[\s,]+', str(raw))
    cleaned = []
    for item in items:
        s = str(item).strip().lstrip("#")
        if s:
            cleaned.append("#" + normalize_hashtag_token(s))
    seen = set(); out = []
    for h in cleaned:
        if h.lower() not in seen:
            seen.add(h.lower()); out.append(h)
    return out

def build_absolute_url(raw_url: str, slug: str) -> str:
    if raw_url:
        s = raw_url.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
        if s.startswith("//"):
            return f"https:{s}"
        return f"{BASE_URL}/{s.lstrip('/')}"
    if slug:
        return f"{BASE_URL}/{slug.lstrip('/')}"
    return ""

def build_hashtags_list(article):
    raw_tags = article.get("hashtags") or article.get("tags") or article.get("hashtag")
    tags = extract_hashtags_field(raw_tags)
    if not tags:
        t = article.get("title", "") or ""
        e = article.get("excerpt") or article.get("description") or ""
        tags = generate_hashtags(t, e)
    if not tags:
        tags = ["#seechuragro"]
    return tags[:MAX_TAGS]

def assemble_final_text(article):
    title = article.get("title", "") or ""
    excerpt = article.get("excerpt") or article.get("description") or ""
    if title and excerpt:
        body = f"{title}\n\n{excerpt}".strip()
    else:
        body = (title or excerpt).strip()

    raw_url = article.get("url") or article.get("link") or ""
    slug = article.get("slug") or ""
    url = build_absolute_url(raw_url, slug)

    tags_list = build_hashtags_list(article)
    tags_text = " ".join(tags_list) if tags_list else ""

    # Reserve room for URL (and newline) and tags (and newline)
    reserved = 0
    if url:
        reserved += 1 + URL_PLACEHOLDER_LEN  # newline + shortened url
    if tags_text:
        reserved += 1 + len(tags_text)  # newline + tags length

    available_for_body = MAX_TWEET_LEN - reserved
    if available_for_body < 0:
        # not enough space for both url+tags; prefer url and as many tags as fit
        if url:
            # try to fit tags only up to remaining chars (after url + newline)
            allowed_for_tags_after_url = MAX_TWEET_LEN - (1 + URL_PLACEHOLDER_LEN)
            chosen = []
            for t in tags_list:
                if len(" ".join(chosen + [t])) <= allowed_for_tags_after_url:
                    chosen.append(t)
                else:
                    break
            if chosen:
                return f"{url}\n{' '.join(chosen)}"
            else:
                return url[:MAX_TWEET_LEN]
        else:
            # no url and not enough space for tags => truncate tags to fit
            chosen = []
            for t in tags_list:
                if len(" ".join(chosen + [t])) <= MAX_TWEET_LEN:
                    chosen.append(t)
                else:
                    break
            return " ".join(chosen)[:MAX_TWEET_LEN]

    # Truncate body if necessary
    if len(body) <= available_for_body:
        final_body = body
    else:
        if available_for_body > 3:
            final_body = body[:available_for_body - 3].rstrip() + "..."
        else:
            final_body = body[:available_for_body].rstrip()

    parts = []
    if final_body:
        parts.append(final_body)
    if url:
        parts.append(url)
    if tags_text:
        parts.append(tags_text)
    final_text = "\n".join(parts)
    return final_text

def post_text(text: str) -> bool:
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        logging.error("Missing X credentials in env.")
        return False
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET,
            wait_on_rate_limit=True
        )
        # Optional debug: print authenticated user
        try:
            me = client.get_me()
            logging.info("DEBUG get_me -> %s", getattr(me, "data", me))
        except Exception:
            pass

        resp = client.create_tweet(text=text)
        logging.info("Tweet response: %s", getattr(resp, "data", resp))
        return True
    except Exception as e:
        logging.error("Failed posting to X: %s", e)
        # try to log more info if available
        try:
            if hasattr(e, "response") and e.response is not None:
                logging.error("HTTP response: %s", getattr(e.response, "text", repr(e.response)))
            elif getattr(e, "args", None):
                logging.error("Exception args: %s", e.args)
        except Exception:
            logging.exception("While logging post error")
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

    final_text = assemble_final_text(data)
    logging.info("Final text to post (len=%d): %s", len(final_text), final_text[:1000] + ("..." if len(final_text) > 1000 else ""))
    ok = post_text(final_text)
    sys.exit(0 if ok else 3)

if __name__ == "__main__":
    main()
