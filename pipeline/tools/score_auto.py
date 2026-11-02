#!/usr/bin/env python3
"""Score an automatic line inventory against a reviewed one (same pages).

    python3 pipeline/tools/score_auto.py <auto item dir> <reviewed item dir>

Line detection: a reviewed printed line counts as found if an automatic line overlaps it with IoU >= 0.5.
Text: character error rate of the automatic `text` against the reviewed `text` on found lines.
"""
import json, sys
from pathlib import Path
from rapidfuzz.distance import Levenshtein

auto_dir, ref_dir = Path(sys.argv[1]), Path(sys.argv[2])

def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i) if i else 0.0

tot = {"ref": 0, "found": 0, "chars": 0, "err": 0, "hy_ok": 0, "hy_n": 0, "auto": 0}
for rf in sorted((ref_dir / "ocr").glob("*.lines.json")):
    ref = json.loads(rf.read_text(encoding="utf-8"))
    af = auto_dir / "ocr" / rf.name
    if not af.exists():
        continue
    auto = json.loads(af.read_text(encoding="utf-8"))
    A = [l for r in auto["regions"] for l in r["lines"]]
    R = [l for r in ref["regions"] if r["production"] == "printed" and r["type"] not in ("map-label", "legend", "caption")
         for l in r.get("lines", []) if l["text"]]
    found = chars = err = hy_ok = 0
    for l in R:
        best = max(A, key=lambda a: iou(a["bbox"], l["bbox"]), default=None)
        if best and iou(best["bbox"], l["bbox"]) >= 0.5:
            found += 1
            chars += len(l["text"]); err += Levenshtein.distance(best["text"], l["text"])
            hy_ok += best["hyphen_end"] == l["hyphen_end"]
    print(f"{rf.stem.split('.')[0]}: reviewed lines {len(R)}, found {found} ({found / max(1, len(R)):.0%}), "
          f"auto lines {len(A)}, CER on found {err / max(1, chars):.2%}, hyphen_end agreement {hy_ok}/{found}, "
          f"unplaced archive lines {len(auto.get('unplaced', []))}")
    for k, v in (("ref", len(R)), ("found", found), ("chars", chars), ("err", err), ("hy_ok", hy_ok), ("hy_n", found), ("auto", len(A))):
        tot[k] += v
print(f"ALL: found {tot['found']}/{tot['ref']} ({tot['found'] / max(1, tot['ref']):.0%}), CER {tot['err'] / max(1, tot['chars']):.2%}, "
      f"hyphen_end {tot['hy_ok']}/{tot['hy_n']}")
