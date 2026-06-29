#!/usr/bin/env python3
"""
Embed creature artwork into index.html for Reptilia Antiqua.

Each illustration is served as two JPEG files under img/ — a `file` ~1000px
(card image) and a `thumb` ~200px (timeline) — referenced by path from the
CREDITS object. This script does the repetitive part of that pipeline — resize,
compress, write img/<id>.jpg + img/<id>_thumb.jpg, and point CREDITS at them —
and also saves the full-size source under art/.

Setup (once): a local venv with Pillow lives in tools/venv (git-ignored).
    python3 -m venv tools/venv && tools/venv/bin/pip install Pillow

Usage:
    # process every Gemini_Generated_*.png dropped in the repo root:
    tools/venv/bin/python tools/embed_image.py

    # or specific files:
    tools/venv/bin/python tools/embed_image.py Gemini_Generated_Spinosaurus.png

    # see what would happen without writing anything:
    tools/venv/bin/python tools/embed_image.py --dry-run

Each file's creature id is inferred from its name (ALIAS map + fuzzy match against
the ids already in index.html). The creature must already exist in CREDITS — this
script REPLACES that entry's `file`/`thumb` (the common "regenerated the art" case)
and refuses to invent a new entry, so a typo can't silently create a stray creature.
After processing it copies the source to art/<slug>.png and (by default) deletes the
root Gemini_Generated_*.png. Always eyeball the result in the app afterwards.
"""
import os, re, io, sys, glob, shutil
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
ART = os.path.join(ROOT, "art")
IMG = os.path.join(ROOT, "img")

FILE_W, FILE_Q = 1000, 82          # card image
THUMB_W, THUMB_Q = 200, 78         # timeline thumbnail
ARTIST = "AI-generated with Google Gemini (Nano Banana)"

# filename-stem -> creature id, for names that don't fuzzy-match cleanly.
ALIAS = {
    "tyrannosaurus_rex": "trex", "tyrannosaurusrex": "trex", "trex": "trex",
    "iguanadon": "iguanodon",
}
# creature id -> art/<slug>.png stem, when the art file isn't named after the id.
SLUG_OVERRIDES = {"trex": "tyrannosaurus-rex"}


def creature_ids(html):
    return re.findall(r'id:"([a-z0-9]+)"', html)


def infer_id(stem, ids):
    """Map a Gemini filename stem to a creature id."""
    s = re.sub(r'^gemini_generated_', '', stem.lower())
    s = re.sub(r'[^a-z0-9]', '', s)
    if s in ALIAS:
        return ALIAS[s]
    if s in ids:
        return s
    # fuzzy: the id is a prefix/substring of the cleaned stem or vice versa
    cand = [i for i in ids if i == s or s.startswith(i) or i.startswith(s) or i in s]
    if len(cand) == 1:
        return cand[0]
    if len(cand) > 1:
        raise ValueError(f"'{stem}' is ambiguous: {cand}")
    raise ValueError(f"could not map '{stem}' to a creature id (add it to ALIAS)")


def encode_jpeg(img, width, q, outpath=None):
    """Resize+compress to JPEG; write to outpath if given. Returns byte size."""
    im = img.convert("RGB")
    w, h = im.size
    im = im.resize((width, round(h * width / w)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q, progressive=True, optimize=True)
    data = buf.getvalue()
    if outpath:
        with open(outpath, "wb") as f:
            f.write(data)
    return len(data)


def credit_span(html, cid):
    """Return (start, end) of the "<cid>":{...} CREDITS object, or None."""
    key = f'"{cid}":{{'
    i = html.find(key)
    if i < 0:
        return None
    depth, j = 0, i + len(key) - 1
    while j < len(html):
        c = html[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i, j + 1
        j += 1
    raise ValueError(f"unterminated CREDITS entry for {cid}")


def set_field(obj, field, value):
    pat = re.compile(r'"' + field + r'":"(?:[^"\\]|\\.)*"')
    repl = '"' + field + '":"' + value + '"'
    new, n = pat.subn(repl, obj, count=1)
    if n != 1:
        raise ValueError(f'field "{field}" not found in CREDITS entry')
    return new


def process(path, html, ids, dry):
    stem = os.path.splitext(os.path.basename(path))[0]
    cid = infer_id(stem, ids)
    span = credit_span(html, cid)
    if span is None:
        raise ValueError(f"no CREDITS entry for id '{cid}' — add one first, then re-run")
    img = Image.open(path)
    file_rel, thumb_rel = f"img/{cid}.jpg", f"img/{cid}_thumb.jpg"
    if not dry:
        os.makedirs(IMG, exist_ok=True)
    fsz = encode_jpeg(img, FILE_W, FILE_Q, None if dry else os.path.join(ROOT, file_rel))
    tsz = encode_jpeg(img, THUMB_W, THUMB_Q, None if dry else os.path.join(ROOT, thumb_rel))
    print(f"  {os.path.basename(path)} -> {cid}: {img.size[0]}x{img.size[1]} "
          f"=> file ~{fsz // 1024} KB, thumb ~{tsz // 1024} KB")
    if dry:
        return html
    i, j = span
    obj = set_field(set_field(html[i:j], "file", file_rel), "thumb", thumb_rel)
    html = html[:i] + obj + html[j:]
    slug = SLUG_OVERRIDES.get(cid, cid)
    shutil.copyfile(path, os.path.join(ART, slug + ".png"))
    print(f"    wrote {file_rel} + {thumb_rel} and art/{slug}.png")
    return html


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    keep = "--keep" in sys.argv
    files = args or sorted(glob.glob(os.path.join(ROOT, "Gemini_Generated_*.png")))
    if not files:
        print("No images. Drop Gemini_Generated_*.png in the repo root, or pass paths.")
        return
    html = open(HTML, encoding="utf-8").read()
    ids = creature_ids(html)
    print(f"{len(files)} image(s){' (dry run)' if dry else ''}:")
    done = []
    for f in files:
        try:
            html = process(f, html, ids, dry)
            done.append(f)
        except Exception as e:
            print(f"  ✗ {os.path.basename(f)}: {e}")
    if not dry and done:
        open(HTML, "w", encoding="utf-8").write(html)
        if not keep:
            for f in done:
                if os.path.basename(f).startswith("Gemini_Generated_"):
                    os.remove(f)
        print(f"\nUpdated index.html ({len(done)} embedded). "
              f"Now open the app and check the artwork.")


if __name__ == "__main__":
    main()
