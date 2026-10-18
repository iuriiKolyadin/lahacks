#!/usr/bin/env python3
"""Replace the Even HUD in press photos with Cue's lens strings, via the Gemini image model.

Usage:
  python3 tools/hud_edit.py --list                       # show image-capable models
  python3 tools/hud_edit.py --model MODEL [--only wearer] # run every job (or one)

Key is read from ~/.secrets/gemini_api_key (or $GEMINI_API_KEY). Inputs are the
converted press shots in /tmp/earshot-photos/out; outputs go to docs/deck/images/.
"""
import argparse, base64, json, os, pathlib, sys, time, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path("/tmp/earshot-photos/out")
OUT = ROOT / "docs/deck/images"
API = "https://generativelanguage.googleapis.com/v1beta"

STYLE = ("Keep the same neon green colour, the same soft glow, the same slight perspective "
         "tilt and the same position where the old overlay was. Monospace, lowercase, with "
         "a wide gap between the arrow and the word. Change nothing else in the photograph: "
         "same person, same glasses, same lighting, same background, same framing.")

JOBS = {
    "wearer": ("06-source.png",
               "Edit this photo. Remove the green heads-up display overlay (the large clock "
               "digits and the calendar list) and replace it with one single line of green "
               "monospace text that reads exactly:  <-----  doorbell  . " + STYLE),
    "back":   ("03-xpert.png",
               "Edit this photo. Remove the green heads-up display overlay (the calendar list "
               "and the 'Even AI Listening' bar) and replace it with one single line of green "
               "monospace text that reads exactly:  <-----  knock  . " + STYLE),
    "desk":   ("01-r1.jpg",
               "Edit this photo. Remove the green heads-up display overlay (the clock digits "
               "and the calendar list) and replace it with one single word of green monospace "
               "text that reads exactly:  alarm  . " + STYLE),
    "social": ("04-new-even.png",
               "Edit this photo. Remove the green heads-up display overlay (the clock digits "
               "and the calendar list) and replace it with one single line of green monospace "
               "text that reads exactly:  speech  ----->  . " + STYLE),
    "quiet":  ("02-quiet-revolution.jpg",
               "Edit this photo. Remove the headline text and the green beam, and add one "
               "single line of green monospace text floating over the lens that reads exactly: "
               " <-----  snap  . " + STYLE),
}

def key():
    k = os.environ.get("GEMINI_API_KEY") or pathlib.Path("~/.secrets/gemini_api_key").expanduser().read_text().strip()
    if not k: sys.exit("no key: put it in ~/.secrets/gemini_api_key")
    return k

def call(path, body=None):
    req = urllib.request.Request(f"{API}/{path}", headers={"x-goog-api-key": key(), "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body else None, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=180) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} on {path}: {e.read().decode()[:800]}")

def list_models():
    for m in call("models?pageSize=200").get("models", []):
        name = m["name"].split("/", 1)[1]
        if "image" in name.lower() and "generateContent" in m.get("supportedGenerationMethods", []):
            print(f"{name:45s} {m.get('displayName','')}")

def run(model, name, src, prompt):
    data = base64.b64encode((SRC / src).read_bytes()).decode()
    mime = "image/png" if src.endswith(".png") else "image/jpeg"
    body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": data}}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}
    t0 = time.time(); res = call(f"models/{model}:generateContent", body)
    parts = res.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    imgs = [p["inlineData"] for p in parts if "inlineData" in p]
    texts = [p["text"] for p in parts if "text" in p]
    if not imgs:
        print(f"{name}: no image returned ({time.time()-t0:.0f}s). text={texts[:1]} finish={res.get('candidates',[{}])[0].get('finishReason')}"); return
    ext = "png" if "png" in imgs[0]["mimeType"] else "jpg"
    out = OUT / f"cue-{name}.{ext}"; out.write_bytes(base64.b64decode(imgs[0]["data"]))
    print(f"{name}: wrote {out} ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--list", action="store_true"); ap.add_argument("--model"); ap.add_argument("--only")
    a = ap.parse_args()
    if a.list: list_models(); sys.exit()
    if not a.model: sys.exit("--model required (see --list)")
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (src, prompt) in JOBS.items():
        if a.only and n != a.only: continue
        run(a.model, n, src, prompt)
