#!/usr/bin/env python3
"""
send_x.py — Post title/excerpt + article URL + hashtags to X (text-only).
Supports optional threading: if excerpt is longer than fits, post remainder as replies.

Enable threading by setting:
    X_USE_THREAD=true
in your GitHub Actions workflow.

Main tweet layout:
    <Title + Excerpt (truncated)>
    <URL>
    <#tags>

Replies (if enabled):
    Remaining excerpt split into 260-char chunks.

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

# Credentials
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

BASE_URL = os.getenv("BASE_URL", "https://seechuragro.in").rstrip('/')

MAX_TAGS = 8
MIN_WORD_LEN = 4
MAX_TWEET_LEN = 280           # strict X limit
URL_PLACEHOLDER_LEN = 23      # t.co shortener length
USE_THREAD = os.getenv("X_USE_THREAD", "false").lower() in ("1", "true", "yes")


# ----------------------------
# Helpers
# ----------------------------

def normalize_hashtag_token(tok: str) -> str:
    t = re.sub(r'[^0-9A-Za-z]', '', tok)
    return t.lower()

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
    seen = set()
    out = []
    for h in cleaned:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
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

def split_text_into_chunks(text: str, max_len: int):
    """
    Break large text into <= max_len pieces.
    """
    words = text.strip().split()
    chunks = []
    cur = []
    cur_len = 0
    for w in words:
        extra = len(w) + (1 if cur else 0)
        if cur_len + extra <= max_len:
            cur.append(w)
            cur_len += extra
        else:
            chunks.append(" ".join(cur))
            cur = [w]
            cur_len = len(w)
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# ----------------------------
# MAIN ASSEMBLY
# ----------------------------

def assemble_main_and_remainder(article):
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

    # truncate body to fit: body + newline + url + newline + tags
    reserved = 0
    reserved += 1 + URL_PLACEHOLDER_LEN   # "\n" + URL
    if tags_list:
        reserved += 1                     # "\n" before tags

    available = MAX_TWEET_LEN - reserved
    if available < 0:
        main_body = ""
    else:
        if len(body) <= available:
            main_body = body
        else:
            # truncate without cutting mid-sentence too harshly
            if available > 3:
                main_body = body[:available-3].rstrip() + "..."
            else:
                main_body = body[:available].rstrip()

    # Determine remainder from excerpt (not title)
    if title and excerpt:
        # compute how many chars of excerpt were used
        consumed_excerpt = main_body.replace(title, "", 1).lstrip() if main_body.startswith(title) else ""
        # fallback: simply compute difference
        remainder = ""
        if len(main_body) < len(body):
            remainder = body[len(main_body):].lstrip()
    else:
        remainder = ""
        if len(main_body) < len(body):
            remainder = body[len(main_body):].lstrip()

    # Assemble main tweet
    parts = []
    if main_body:
        parts.append(main_body)
    if url:
        parts.append(url)
    if tags_list:
        parts.append(" ".join(tags_list))
    final_main = "\n".join(parts)

    return final_main, remainder


# ----------------------------
# POSTING
# ----------------------------

def post_text_and_thread(main_text: str, remainder: str):
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        logging.error("Missing X credentials.")
        return False

    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET,
            wait_on_rate_limit=True
        )

        # Main tweet
        resp = client.create_tweet(text=main_text)
        logging.info("Main tweet posted: %s", resp.data)
        tweet_id = resp.data.get("id")

        # Threading disabled or nothing left → stop
        if not USE_THREAD or not remainder:
            return True

        # Replies for remainder
        chunks = split_text_into_chunks(remainder, 260)
        parent = tweet_id
        for chunk in chunks:
            r = client.create_tweet(text=chunk, in_reply_to_tweet_id=parent)
            logging.info("Reply posted: %s", r.data)
            parent = r.data.get("id", parent)

        return True

    except Exception as e:
        logging.error("Failed posting to X: %s", e)
        return False


# ----------------------------
# MAIN
# ----------------------------

def usage():
    print("Usage: send_x.py <path/to/article.json>")
    sys.exit(2)

def main():
    if len(sys.argv) < 2:
        usage()

    jf = Path(sys.argv[1])
    if not jf.exists():
        logging.error("JSON not found: %s", jf)
        sys.exit(2)

    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except Exception as e:
        logging.error("JSON parse error: %s", e)
        sys.exit(2)

    main_text, remainder = assemble_main_and_remainder(data)

    logging.info("Posting main tweet:\n%s", main_text[:500])
    ok = post_text_and_thread(main_text, remainder)

    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
