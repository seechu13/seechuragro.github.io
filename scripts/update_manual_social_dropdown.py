#!/usr/bin/env python3
import pathlib
import re

WORKFLOW_FILE = ".github/workflows/manual-generate-social.yml"
ARTICLES_DIR = "articles"

def main():
    wf = pathlib.Path(WORKFLOW_FILE)
    if not wf.exists():
        raise SystemExit(f"Workflow not found: {WORKFLOW_FILE}")

    articles = sorted(
        str(p)
        for p in pathlib.Path(ARTICLES_DIR).rglob("*.html")
    )

    if not articles:
        raise SystemExit("No articles found")

    text = wf.read_text()

    # Replace only the options block
    new_options = "\n".join(f"          - {a}" for a in articles)

    pattern = re.compile(
        r"(options:\n)([\s\S]*?)(\n\s+permissions:)",
        re.MULTILINE,
    )

    def repl(m):
        return m.group(1) + new_options + m.group(3)

    new_text, count = pattern.subn(repl, text)

    if count != 1:
        raise SystemExit("Failed to update options block (pattern mismatch)")

    wf.write_text(new_text)
    print(f"Updated dropdown with {len(articles)} articles")

if __name__ == "__main__":
    main()
