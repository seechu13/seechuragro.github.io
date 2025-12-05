#!/usr/bin/env python3
import os, sys, json, tempfile, shutil, subprocess, logging
from pathlib import Path
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

try:
    import tweepy
except Exception:
    logging.error("tweepy is required; install it in the workflow environment.")
    sys.exit(2)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

MAX_WIDTH = int(os.getenv("MAX_WIDTH", "1280"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "85"))

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

def normalize(raw):
    if not raw:
        return ""
    s = raw.strip()
    if s.startswith("http://") or s.startswith("https://"):
        parts = s.split("/", 3)
        return parts[3] if len(parts) >= 4 else Path(s).name
    return s.lstrip("./").lstrip("/")

def find_local_image(candidate, jf):
    exts = ["jpg","jpeg","png","webp","gif"]
    name = Path(candidate).name
    base = Path(name).stem

    checks = [
        Path(candidate),
        jf.parent / name,
        Path("assets/articles")/name,
        Path("images")/name,
        Path("images/uploads")/name,
        Path(name),
    ]
    for p in checks:
        if p.exists() and p.is_file():
            return p.resolve()

    for ext in exts:
        for p in [
            Path("assets/articles")/f"{base}.{ext}",
            Path("images")/f"{base}.{ext}",
            Path("images/uploads")/f"{base}.{ext}",
            Path(f"{base}.{ext}"),
            jf.parent/f"{base}.{ext}",
        ]:
            if p.exists() and p.is_file():
                return p.resolve()

    try:
        out = subprocess.check_output(["git","ls-files"], text=True)
        for line in out.splitlines():
            if Path(line).stem == base and Path(line).exists():
                return Path(line).resolve()
    except:
        pass

    return None

def resize_im(src):
    try:
        tmp = Path(tempfile.mktemp(suffix=".jpg"))
        subprocess.check_call([
            "convert", str(src),
            "-resize", f"{MAX_WIDTH}x>",
            "-strip", "-quality", str(JPEG_QUALITY),
            str(tmp)
        ])
        return tmp
    except:
        return None

def resize_pillow(src):
    if not PIL_AVAILABLE:
        return None
    try:
        img = Image.open(src)
        w,h = img.size
        if w <= MAX_WIDTH:
            tmp = Path(tempfile.mktemp(suffix=".jpg"))
            if img.mode!="RGB":
                img = img.convert("RGB")
            img.save(tmp, format="JPEG", quality=JPEG_QUALITY)
            return tmp
        nh = int(h * (MAX_WIDTH/w))
        img = img.resize((MAX_WIDTH, nh), Image.LANCZOS)
        if img.mode!="RGB":
            img = img.convert("RGB")
        tmp = Path(tempfile.mktemp(suffix=".jpg"))
        img.save(tmp, format="JPEG", quality=JPEG_QUALITY)
        return tmp
    except:
        return None

def caption(t, e, u):
    parts=[p for p in [t,e,u] if p]
    out="\n\n".join(parts).strip()
    return out[:2800]

def post_text(api, text):
    try:
        api.update_status(status=text)
        return True
    except Exception as e:
        logging.error(e)
        return False

def post_media(api, text, img):
    tmp = Path(tempfile.mktemp(suffix=".jpg"))
    shutil.copyfile(img, tmp)
    try:
        media = api.media_upload(str(tmp))
        mid = getattr(media, "media_id_string", None)
        api.update_status(status=text, media_ids=[mid])
        return True
    except Exception as e:
        logging.error(e)
        return False
    finally:
        tmp.unlink(missing_ok=True)

def main():
    if len(sys.argv)<2:
        print("Usage: send_x.py file.json"); sys.exit(2)
    jf = Path(sys.argv[1])
    if not jf.exists():
        logging.error("JSON not found: %s", jf)
        sys.exit(2)
    data = json.loads(jf.read_text(encoding="utf-8"))
    title = data.get("title","")
    excerpt = data.get("excerpt") or data.get("description","")
    url = data.get("url") or data.get("link","")
    raw = data.get("cover_image","")

    cap = caption(title,excerpt,url)

    auth = tweepy.OAuth1UserHandler(
        X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
    )
    api = tweepy.API(auth, wait_on_rate_limit=True)

    img_final=None
    tmp_resized=None

    if raw and raw.startswith("http"):
        try:
            r = requests.get(raw, stream=True, timeout=20); r.raise_for_status()
            tmp = Path(tempfile.mktemp(suffix=".jpg"))
            with open(tmp,"wb") as f:
                for c in r.iter_content(8192): f.write(c)
            img_final=tmp
        except:
            img_final=None
    else:
        norm = normalize(raw)
        found = find_local_image(norm, jf)
        img_final = found or None

    if not img_final:
        found = find_local_image(jf.stem, jf)
        img_final = found or None

    if img_final:
        tmp = resize_im(img_final)
        if not tmp:
            tmp = resize_pillow(img_final)
        if tmp:
            tmp_resized = tmp

    ok=False
    if tmp_resized:
        ok = post_media(api, cap, tmp_resized)
        tmp_resized.unlink(missing_ok=True)
    elif img_final:
        ok = post_media(api, cap, img_final)
        if str(img_final).startswith("/tmp"):
            img_final.unlink(missing_ok=True)
    else:
        ok = post_text(api, cap)

    sys.exit(0 if ok else 3)

if __name__=="__main__":
    main()
