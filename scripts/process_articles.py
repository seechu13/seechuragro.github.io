#!/usr/bin/env python3
"""
scripts/process_articles.py

Used by telegram.yml to:
1) Detect changed article JSON files under articles/
2) Validate that any non-HTTP images exist in the repo
3) Call scripts/send_telegram.py for each JSON file

Safe: Skips invalid/broken files without stopping other posts.
"""

import os
import subprocess
import sys
import json
from pathlib import Path

repo_root = Path(".").resolve()
sha = os.environ.get("GITHUB_SHA", "")
before = os.environ.get("GITHUB_EVENT_BEFORE", "")


def git_changed_articles(before, sha):
    """
    Find changed article JSON files if Git history is available.
    """
    try:
        if before:
            out = subprocess.check_output(
                ["git", "diff", "--name-only", before, sha],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        else:
            out = subprocess.check_output(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
    except subprocess.CalledProcessError:
        out = ""

    files = [
        s.strip()
        for s in out.splitlines()
        if s.strip().startswith("articles/") and s.strip().endswith(".json")
    ]
    return files


def fallback_all_articles():
    """
    For manual runs (workflow_dispatch), or when no diff is available.
    """
    p = repo_root / "articles"
    if not p.exists():
        return []
    return [str(x) for x in sorted(p.glob("*.json"))]


def images_ok(json_path):
    """
    Ensures any local (non-HTTP) images are present inside the repo.
    """
    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot read JSON {json_path}: {e}")
        return False

    imgs = (
        data.get("images")
        or data.get("cover_image")
        or data.get("cover_images")
        or []
    )

    for im in imgs:
        if not isinstance(im, str):
            continue
        s = im.strip()
        if not s:
            continue

        # Remote images OK
        if s.lower().startswith("http://") or s.lower().startswith("https://") or s.startswith("//"):
            continue

        # Local file must exist
        p = Path(s.lstrip("/"))
        if not p.exists():
            print(f"MISSING local image for {json_path}: {s}")
            return False

    return True


def post_via_script(json_path):
    """
    Calls your existing send_telegram.py file.
    """
    try:
        print(f"Posting {json_path} via scripts/send_telegram.py")
        r = subprocess.run(
            ["python3", "scripts/send_telegram.py", json_path],
            check=False
        )
        return r.returncode == 0
    except Exception as e:
        print("ERROR running send_telegram.py:", e)
        return False


def main():
    changed = git_changed_articles(before, sha)
    if not changed:
        changed = fallback_all_articles()

    if not changed:
        print("No article JSON files to process.")
        return 0

    print("Files to process:", changed)
    overall_ok = True

    for jf in changed:
        jf = jf.strip()
        if not jf:
            continue
        if not Path(jf).exists():
            print(f"SKIP (file not found in workspace): {jf}")
            continue

        print(f"--- Processing {jf} ---")

        if not images_ok(jf):
            print(f"SKIP due to missing local images: {jf}")
            overall_ok = False
            continue

        posted = post_via_script(jf)
        if not posted:
            print(f"Posting failed for {jf}")
            overall_ok = False
            continue

        print(f"Posted successfully: {jf}")

    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
