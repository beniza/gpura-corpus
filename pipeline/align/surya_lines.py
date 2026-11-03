#!/usr/bin/env python3
"""Run Surya's text-line detector on page images; called by auto_lines.py from Surya's own environment.

    <surya venv python> pipeline/align/surya_lines.py out.json page1.jpg page2.jpg ...

Writes {"surya": "<version>", "pages": {"<image path>": [[x1, y1, x2, y2], ...]}} in image pixels.
The model is loaded once for all pages.  Set up with `bash pipeline/tools/setup_bench.sh surya`
(or `surya-gpu`, which reuses an installed CUDA PyTorch).
"""
import importlib.metadata
import json
import sys

from PIL import Image
from surya.detection import DetectionPredictor


def main():
    out, paths = sys.argv[1], sys.argv[2:]
    det = DetectionPredictor()
    res = {}
    for i in range(0, len(paths), 4):                 # small batches keep memory modest on large scans
        batch = paths[i:i + 4]
        preds = det([Image.open(p).convert("RGB") for p in batch])
        for p, pr in zip(batch, preds):
            res[p] = [[round(v) for v in b.bbox] for b in pr.bboxes]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"surya": importlib.metadata.version("surya-ocr"), "pages": res}, f)


if __name__ == "__main__":
    main()
