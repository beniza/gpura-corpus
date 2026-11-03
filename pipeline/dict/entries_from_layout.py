#!/usr/bin/env python3
"""Dictionary pages, step 1: split a page's lines into entries by hanging indent.

    GPURA_ITEM_DIR=items/<item> python3 pipeline/dict/entries_from_layout.py p300 [--indent 0.6]

Dictionaries set the first line of an entry flush with the column's left edge and indent the rest.
Columns are found from the lines' left edges; a line starting within --indent character heights of its
column's edge opens an entry.  Lines are taken in reading order from ocr/<page>.lines.json (text and
boxes as encoded).  Writes dict/<page>.entries.json:
  {"page", "columns": [x], "entries": [{"n", "column", "lines": [{"id", "text", "bbox"}], "text"}],
   "furniture": [lines that are page numbers or running heads]}
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import item_dir  # noqa: E402

ROOT = item_dir()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--indent", type=float, default=0.6, help="in line heights")
    a = ap.parse_args()
    d = json.loads((ROOT / "ocr" / f"{a.page}.lines.json").read_text(encoding="utf-8"))
    furniture, body = [], []
    for r in d["regions"]:
        for l in r["lines"]:
            (furniture if r["type"] in ("page-number", "header") else body).append(l)
    if not body:
        raise SystemExit("no body lines")
    h = float(np.median([l["bbox"][3] for l in body]))
    W = d["width"]
    # columns: cluster the left edges of body lines (gap > 15% of page width)
    xs = sorted(l["bbox"][0] for l in body)
    cols = [[xs[0]]]
    for x in xs[1:]:
        if x - cols[-1][-1] < 0.15 * W:
            cols[-1].append(x)
        else:
            cols.append([x])
    edges = [float(np.percentile(c, 10)) for c in cols if len(c) >= 3]
    col_of = lambda l: int(np.argmin([abs(l["bbox"][0] - e) if l["bbox"][0] >= e - 2 * h else 1e9 for e in edges]))
    entries = []
    ordered = sorted(body, key=lambda l: (col_of(l), l["bbox"][1]))
    cols_of = [col_of(l) for l in ordered]
    for k, l in enumerate(ordered):
        c = cols_of[k]
        # the column's margin near this line: scans are often slightly skewed or curved, so a single edge
        # per column misreads indents; use the leftmost start among the neighbouring lines of the column
        near = [o["bbox"][0] for j, o in enumerate(ordered) if cols_of[j] == c and abs(j - k) <= 6]
        flush = l["bbox"][0] - min(near) < a.indent * h
        if flush or not entries or entries[-1]["column"] != c:
            entries.append({"n": len(entries) + 1, "column": c, "starts_flush": flush, "lines": []})
        entries[-1]["lines"].append({"id": l["id"], "text": l["text"], "bbox": l["bbox"]})
    for e in entries:
        e["text"] = "\n".join(x["text"] for x in e["lines"])
    out = ROOT / "dict"
    out.mkdir(exist_ok=True)
    (out / f"{a.page}.entries.json").write_text(json.dumps(
        {"page": a.page, "columns": edges, "entries": entries,
         "furniture": [{"id": l["id"], "text": l["text"]} for l in furniture]}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print(f"  {a.page}: {len(edges)} columns, {len(entries)} entries, {len(body)} lines "
          f"({sum(not e['starts_flush'] for e in entries)} entries start mid-entry: carried over from the previous column/page)")


if __name__ == "__main__":
    main()
