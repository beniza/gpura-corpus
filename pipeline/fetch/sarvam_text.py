#!/usr/bin/env python3
"""Sarvam stage: page text from Sarvam Vision (Document AI "Parse") for pages Gpura has no text for.

    GPURA_ITEM_DIR=items/<item> python3 pipeline/fetch/sarvam_text.py [--force] [--workers 4]

Gpura's own OCR text matches Sarvam Vision's output character for character on the pages we compared,
so Sarvam fills the gaps in the same quality and conventions as the rest of Gpura.  For each encoded
page whose ocr/gpura_existing_NNNN.txt is empty, this writes
  ocr/sarvam_NNNN.json  the raw Parse result (blocks: layout_tag, coordinates, reading_order, text)
  ocr/sarvam_NNNN.txt   the text in Gpura's shape: one printed line per line, a blank line between
                        blocks, table cells one per line; image blocks left out
The align stage reads sarvam_NNNN.txt where Gpura has no text, and records Sarvam as the source.
Needs SARVAM_API_KEY (environment or .env).  About 0.4 credits and 8 seconds per page.
"""
import argparse
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from common import ITEM, item_dir, page_id, page_image  # noqa: E402
from sarvam_parse import api_key, parse  # noqa: E402

ROOT = item_dir()


def block_lines(b):
    t = b.get("text") or ""
    if b.get("layout_tag") == "image":
        return []
    if "<table" in t:                                 # HTML table: one line per cell, rows in order
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", t, flags=re.S)
        return [html.unescape(re.sub(r"<br\s*/?>", " ", c)).strip() for c in cells if c.strip()]
    t = re.sub(r"<[^>]+>", "", t)
    return [html.unescape(x).strip() for x in t.split("\n") if x.strip()]


def to_text(result):
    page = result["pages"][0]
    blocks = sorted(page["blocks"], key=lambda b: b.get("reading_order", 0))
    return "\n\n".join("\n".join(ls) for ls in (block_lines(b) for b in blocks) if ls) + "\n"


def wanted(n, force):
    if (ROOT / "ocr" / f"gpura_existing_{n:04d}.txt").exists() and \
            (ROOT / "ocr" / f"gpura_existing_{n:04d}.txt").read_text(encoding="utf-8").strip():
        return False                                   # Gpura has text: never replace it
    if not force and (ROOT / "ocr" / f"sarvam_{n:04d}.json").exists():
        return False
    return True       # covers and title pages too: Sarvam returns nothing for a blank page, and the
                      # non-text test (Tesseract confidence) misjudges sparse display type on title pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-run pages that already have a Sarvam result")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    todo = [n for n in ITEM.get("canvases_encoded", []) if wanted(n, a.force)]
    if not todo:
        print("  sarvam: no page needs text")
        return
    key = api_key()
    tmp = ROOT / "ocr" / "_sarvam"
    print(f"  sarvam: reading {len(todo)} page(s) with no Gpura text", flush=True)

    def one(n):
        out = tmp / f"p{n:04d}"
        out.mkdir(parents=True, exist_ok=True)
        rec = parse(Path(page_image(page_id(n))), out, key, "ml-IN", "json")
        if rec["status"] not in ("completed", "partially_completed"):
            return n, rec["status"]
        res = json.loads(next(out.rglob(f"{page_id(n)}.json")).read_text(encoding="utf-8"))
        (ROOT / "ocr" / f"sarvam_{n:04d}.json").write_text(json.dumps(res, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (ROOT / "ocr" / f"sarvam_{n:04d}.txt").write_text(to_text(res), encoding="utf-8", newline="\n")
        return n, f"ok ({rec['seconds_to_result']} s)"

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for n, msg in ex.map(one, todo):
            print(f"  sarvam p{n:03d}: {msg}", flush=True)
    for f in sorted(tmp.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    tmp.rmdir()


if __name__ == "__main__":
    main()
