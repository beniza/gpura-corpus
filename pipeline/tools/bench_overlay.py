#!/usr/bin/env python3
"""Side-by-side overlays of each detector's line boxes, for judging pages with no known answer.

    python3 pipeline/tools/bench_overlay.py [page-key ...]

Reads .cache/bench/<detector>/<page>/boxes.json (written by bench_lines.py) and writes
.cache/bench/overlay/<page>.jpg: one panel per detector (ours | kraken | surya), boxes in alternating
colours so neighbouring lines can be told apart.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
B = REPO / ".cache" / "bench"
DETS = ["ours", "kraken", "surya"]
PANEL_W = 620
COLOURS = [(220, 30, 30), (20, 110, 220), (0, 150, 70)]


def image_for(key):
    f = B / "pages" / f"{key}.jpg"
    if f.exists():
        return f
    item, page = key.rsplit("_", 1)
    for ext in ("png", "jpg"):
        f = REPO / "items" / item / "images" / f"{page}.{ext}"
        if f.exists():
            return f
    raise SystemExit(f"no image for {key}")


def main():
    keys = sys.argv[1:] or sorted({p.name for d in DETS for p in (B / d).glob("*") if p.is_dir()})
    (B / "overlay").mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for key in keys:
        src = Image.open(image_for(key)).convert("RGB")
        k = PANEL_W / src.width
        H = int(src.height * k)
        sheet = Image.new("RGB", (PANEL_W * len(DETS) + 10 * (len(DETS) - 1), H + 34), "white")
        for i, det in enumerate(DETS):
            f = B / det / key / "boxes.json"
            panel = src.resize((PANEL_W, H))
            d = ImageDraw.Draw(panel)
            boxes = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
            for j, (x, y, w, h) in enumerate(sorted(boxes, key=lambda b: (b[1], b[0]))):
                d.rectangle([x * k, y * k, (x + w) * k, (y + h) * k], outline=COLOURS[j % 3], width=2)
            x0 = i * (PANEL_W + 10)
            sheet.paste(panel, (x0, 34))
            ImageDraw.Draw(sheet).text((x0 + 6, 6), f"{det}: {len(boxes)} lines" if f.exists() else f"{det}: not run",
                                       fill="black", font=font)
        out = B / "overlay" / f"{key}.jpg"
        sheet.save(out, quality=80)
        print(out.relative_to(REPO))


if __name__ == "__main__":
    main()
