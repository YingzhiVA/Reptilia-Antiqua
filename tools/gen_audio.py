#!/usr/bin/env python3
"""
Generate pronunciation clips for Reptilia Antiqua using Google Cloud Text-to-Speech.

Run once locally (your API key is read from the environment and never committed):

    # 1. In Google Cloud Console: enable "Cloud Text-to-Speech API", create an API key.
    # 2. Then:
    export GOOGLE_TTS_KEY="your-api-key"
    python3 tools/gen_audio.py

Writes one MP3 per creature-name per language to ./audio/<id>_<lang>.mp3
(skips files that already exist, so it's safe to re-run). Without a key it does a
dry run and just prints what it would generate.

Usage cost: ~120 clips x ~12 characters ≈ 1.5k characters — comfortably inside
Google's monthly free tier. Re-run after adding/renaming creatures.
"""
import os, re, sys, json, base64, urllib.request

LANGS = ["en", "de", "fr", "it", "es", "zh"]
# lang -> (Google languageCode, voice name).  Female neural voices for a warm tone;
# tweak the voice names here if you prefer a different one.
VOICES = {
    "en": ("en-GB", "en-GB-Neural2-C"),
    "de": ("de-DE", "de-DE-Neural2-F"),
    "fr": ("fr-FR", "fr-FR-Neural2-C"),
    "it": ("it-IT", "it-IT-Neural2-A"),
    "es": ("es-ES", "es-ES-Neural2-A"),
    "zh": ("cmn-TW", "cmn-TW-Wavenet-A"),   # Mandarin, Traditional (Taiwan)
}
SPEAKING_RATE = 0.95

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "audio")


def parse_creatures(html):
    """Return [(id, {lang: name})] in document order."""
    out = []
    for block in re.findall(r'\{id:".*?facts:\[.*?\]\}', html, re.DOTALL):
        cid = re.search(r'id:"([a-z0-9]+)"', block).group(1)
        names = {}
        for lang in LANGS:
            m = re.search(r'\b' + lang + r':"([^"]*)"', block)
            if m:
                names[lang] = m.group(1)
        out.append((cid, names))
    return out


def synth(text, lang, key):
    lc, voice = VOICES[lang]
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": lc, "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": SPEAKING_RATE},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://texttospeech.googleapis.com/v1/text:synthesize?key=" + key,
        data=body, headers={"Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req))
    return base64.b64decode(resp["audioContent"])


def main():
    key = os.environ.get("GOOGLE_TTS_KEY")
    creatures = parse_creatures(open(HTML, encoding="utf-8").read())
    os.makedirs(OUT, exist_ok=True)
    planned = [(cid, lang, names[lang]) for cid, names in creatures for lang in LANGS if names.get(lang)]
    print(f"{len(creatures)} creatures, {len(planned)} clips planned.")
    if not key:
        print("\nNo GOOGLE_TTS_KEY set — DRY RUN. Would generate:")
        for cid, lang, txt in planned:
            print(f"  audio/{cid}_{lang}.mp3   ({lang}) {txt}")
        print("\nSet GOOGLE_TTS_KEY and re-run to actually synthesize.")
        return
    made = skipped = failed = 0
    for cid, lang, txt in planned:
        path = os.path.join(OUT, f"{cid}_{lang}.mp3")
        if os.path.exists(path):
            skipped += 1
            continue
        try:
            with open(path, "wb") as f:
                f.write(synth(txt, lang, key))
            made += 1
            print(f"  ✓ {cid}_{lang}.mp3  {txt}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {cid}_{lang}  ({txt}) — {e}")
    print(f"\nDone. {made} created, {skipped} skipped (existing), {failed} failed.")


if __name__ == "__main__":
    main()
