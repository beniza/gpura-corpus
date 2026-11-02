#!/usr/bin/env python3
"""AI step, part 1: cut the lines that need an AI reading into numbered image strips.

    GPURA_ITEM_DIR=items/<item> python3 pipeline/ai/export_strips.py [--weak]

A line needs an AI reading when Gpura has no text for it (flag unclear, cert low) and it has no AI
reading yet.  --weak also includes lines whose match to Gpura's text is weak (cert medium).
Each strip stacks up to 6 line crops from one page, numbered 1..n in red in the left margin.

Writes <item>/ai/strips/<page>_sNN.png, <item>/ai/manifest.json ({strip: [{id, bbox}, ...]}) and
<item>/ai/PROMPT.md (the transcription instructions).  The model's answer goes in
<item>/ai/readings.json as {strip: ["line 1", "line 2", ...]}; import_readings.py takes it from there.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import item_dir, page_ids, page_image  # noqa: E402

ROOT = item_dir()
AI = ROOT / "ai"
PER_STRIP, PAD, MARGIN, GAP = 6, 10, 70, 14

PROMPT = """Transcribe printed Malayalam text from image strips into a JSON file.

Token rules: read only the files named here; read each image exactly once; do not echo transcriptions in
messages; write the output with one Write call; final reply is one line, "done: N lines written".

Inputs: {strips_dir} contains: {names}
Each strip stacks up to 6 separate printed lines cut from a page of a Malayalam book, numbered in red
(1..n) in the left margin. Ignore the red numbers themselves. Lines may come from title pages, headings or
body text, so they need not continue one another.

Transcription rules (diplomatic):
- Transcribe exactly what is printed, line by line, in Unicode Malayalam (or the script printed).
  Do not correct spelling, modernise, or complete words. A word broken at line end stays broken.
- Encode old (pre-reform) script forms as standard Unicode: atomic chillus (ൽ ൾ ൻ ർ ൺ); old NTA as ന്റ;
  old TTA as റ്റ; keep the samvruthokaram where printed (ഉണ്ടു്). Keep punctuation as printed.
- If a line is decoration, a rule, or has no legible text, write an empty string for it.
- If a word is unreadable, write your best reading; do not add markers.

Output: write {out} as a JSON object mapping each strip filename to an array of line strings in order 1..n.
The array length must equal the number of red-numbered lines in that strip.
"""


def needs_ai(line, weak):
    if line.get("source") == "ai":
        return False
    certs = {f.get("cert") for f in line.get("flags", []) if f.get("type") == "unclear"}
    return "low" in certs or (weak and "medium" in certs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weak", action="store_true", help="also lines with a weak match to Gpura's text")
    a = ap.parse_args()
    if AI.exists():
        shutil.rmtree(AI / "strips", ignore_errors=True)
    (AI / "strips").mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    manifest = {}
    for pid in page_ids():
        d = json.loads((ROOT / "ocr" / f"{pid}.lines.json").read_text(encoding="utf-8"))
        if not d.get("automatic"):
            continue
        todo = [l for r in d["regions"] for l in r.get("lines", []) if needs_ai(l, a.weak)]
        if not todo:
            continue
        im = Image.open(page_image(pid)).convert("RGB")
        for k in range(0, len(todo), PER_STRIP):
            grp = todo[k:k + PER_STRIP]
            crops = [im.crop((max(0, x - PAD), max(0, y - PAD), x + w + PAD, y + h + PAD)) for x, y, w, h in
                     (l["bbox"] for l in grp)]
            W = MARGIN + max(c.width for c in crops)
            H = sum(c.height for c in crops) + GAP * (len(crops) - 1)
            strip = Image.new("RGB", (W, H), "white")
            dr = ImageDraw.Draw(strip)
            y = 0
            for n, c in enumerate(crops, 1):
                strip.paste(c, (MARGIN, y))
                dr.text((10, y + c.height // 2 - 18), str(n), fill=(220, 0, 0), font=font)
                y += c.height + GAP
            name = f"{pid}_s{k // PER_STRIP + 1:02d}.png"
            strip.save(AI / "strips" / name)
            manifest[name] = [{"id": l["id"], "bbox": l["bbox"]} for l in grp]
    (AI / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    n = sum(len(v) for v in manifest.values())
    (AI / "PROMPT.md").write_text(PROMPT.format(strips_dir=(AI / "strips").resolve(), names=" ".join(manifest),
                                                out=(AI / "readings.json").resolve()), encoding="utf-8", newline="\n")
    print(f"{n} lines in {len(manifest)} strips need an AI reading -> {AI.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
