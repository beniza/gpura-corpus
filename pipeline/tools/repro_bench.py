#!/usr/bin/env python3
"""Reproduction benchmark: can a page be rebuilt from the corpus files alone?

    python3 pipeline/tools/repro_bench.py [--cases pipeline/tools/repro_cases.json] [--out .cache/repro]

For every test case (an item page, chosen to cover one layout type) it reads only the corpus files
(page/pNNN.page.xml; the reference text below) and the scan, and reports:

  coverage   share of the page's printed-text ink that lies inside an encoded line box.  Ink is the
             pipeline's own dark, low-chroma mask; pictures, ornaments and rules are left out (connected
             components larger than ~8 text lines, or long and thin).  Tests that the layout was captured.
  complete   character-level share of the page's known text reproduced by the corpus: every reference line
             is matched to its closest encoded line; 100 % - CER.  Reference: the reviewed text where a
             person checked the page, else the page's source text (Gpura's OCR, or Sarvam Vision's where
             Gpura has none).  Tests that nothing was dropped or garbled between source and corpus.
  order      share of consecutive reference lines whose matches keep the same order in the corpus
             (reading order).
  lines      encoded lines; by source (gpura / sarvam / ai / tesseract / reviewed)

Results: <out>/results.json and a Markdown table on stdout.
"""
import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

import numpy as np
from lxml import etree
from PIL import Image
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
NS = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"}


def norm(s):
    return " ".join(unicodedata.normalize("NFC", s or "").replace("‌", "").replace("‍", "").split())


def page_lines(item, pid):
    """Encoded lines from PAGE-XML in document order: (bbox, text, source)."""
    t = etree.parse(str(REPO / "items" / item / "page" / f"{pid}.page.xml"))
    out = []
    for tl in t.iterfind(".//p:TextLine", NS):
        pts = [tuple(map(float, p.split(","))) for p in tl.find("p:Coords", NS).get("points").split()]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        te = tl.find("p:TextEquiv[@index='1']/p:Unicode", NS)
        com = (tl.find("p:TextEquiv[@index='1']", NS).get("comments") or "") if te is not None else ""
        src = ("sarvam" if "Sarvam" in com else "ai" if "AI reading" in com else "tesseract" if "Tesseract reading" in com
               else "gpura" if "Gpura" in com else "reviewed")
        out.append(((min(xs), min(ys), max(xs), max(ys)), te.text if te is not None and te.text else "", src))
    return out


def reference(item, pid):
    d = json.loads((REPO / "items" / item / "ocr" / f"{pid}.lines.json").read_text(encoding="utf-8"))
    if not d.get("automatic"):                         # reviewed: the person-checked line texts
        return "reviewed", [l["text"] for r in d["regions"] if r.get("production", "printed") == "printed"
                            for l in r.get("lines", []) if l.get("text")]
    n = int(pid[1:])
    for name in (f"gpura_existing_{n:04d}.txt", f"sarvam_{n:04d}.txt"):
        f = REPO / "items" / item / "ocr" / name
        if f.exists() and f.read_text(encoding="utf-8").strip():
            return name.split("_")[0], [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return "none", []


def ink_coverage(item, pid, boxes):
    sys.path.insert(0, str(REPO / "pipeline" / "align"))
    os.environ.setdefault("GPURA_ITEM_DIR", str(REPO / "items" / item))
    import auto_lines
    img = next(f for f in (REPO / "items" / item / "images" / f"{pid}.{e}" for e in ("png", "jpg")) if f.exists())
    _, ink = auto_lines.detect_lines(Image.open(img))
    lab, n = ndimage.label(ink)
    sl = ndimage.find_objects(lab)
    hs = np.array([s[0].stop - s[0].start for s in sl]); ws = np.array([s[1].stop - s[1].start for s in sl])
    ch = float(np.median(hs[(hs > 3) & (hs < ink.shape[0] * 0.05)])) if n else 10
    keep = np.zeros(n + 1, bool)
    keep[1:] = (hs < 8 * ch) & ~((ws > 25 * ch) & (hs < 0.5 * ch))        # no pictures, ornaments, rules
    text = keep[lab]
    inside = np.zeros_like(text)
    for x0, y0, x1, y1 in boxes:
        inside[int(y0):int(y1) + 1, int(x0):int(x1) + 1] = True
    tot = int(text.sum())
    return 100.0 * int((text & inside).sum()) / tot if tot else 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(REPO / "pipeline" / "tools" / "repro_cases.json"))
    ap.add_argument("--out", default=str(REPO / ".cache" / "repro"))
    a = ap.parse_args()
    cases = json.loads(Path(a.cases).read_text(encoding="utf-8"))
    res = []
    for c in cases:
        item, pid = c["item"], c["page"]
        lines = page_lines(item, pid)
        texts = [norm(t) for _, t, _ in lines]
        rkind, ref = reference(item, pid)
        ref = [norm(r) for r in ref if norm(r)]
        err = chars = 0
        idx = []
        for r in ref:
            j = max(range(len(texts)), key=lambda k: fuzz.ratio(texts[k], r)) if texts else -1
            hyp = texts[j] if j >= 0 else ""
            err += min(len(r), Levenshtein.distance(hyp, r)); chars += len(r); idx.append(j)
        order = (100.0 * sum(b >= a_ for a_, b in zip(idx, idx[1:])) / max(1, len(idx) - 1)) if len(idx) > 1 else 100.0
        src = {}
        for _, _, s in lines:
            src[s] = src.get(s, 0) + 1
        rec = {"layout": c["layout"], "item": item, "page": pid, "reference": rkind,
               "coverage": round(ink_coverage(item, pid, [b for b, _, _ in lines]), 1),
               "complete": round(100.0 * (1 - err / chars), 1) if chars else None,
               "order": round(order, 1), "lines": len(lines), "sources": src}
        res.append(rec)
        print(f"  {c['layout'][:38]:38} {item[:22]:22} {pid}  coverage {rec['coverage']:5}%  complete "
              f"{rec['complete']}%  order {rec['order']}%  lines {rec['lines']} {src}", flush=True)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n| Layout | Page | Reference | Ink in line boxes | Text reproduced | Order kept | Lines |")
    print("|---|---|---|---|---|---|---|")
    for r in res:
        print(f"| {r['layout']} | {r['item']} {r['page']} | {r['reference']} | {r['coverage']}% | {r['complete']}% | {r['order']}% | {r['lines']} |")


if __name__ == "__main__":
    main()
