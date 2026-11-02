#!/usr/bin/env python3
"""AI step, part 2: store the model's readings so the align stage uses them.

    GPURA_ITEM_DIR=items/<item> python3 pipeline/ai/import_readings.py --model "Claude Sonnet 5.5"

Reads <item>/ai/manifest.json and <item>/ai/readings.json and merges them into
<item>/ocr/ai_readings.json: {line_id: {"bbox", "text", "model"}}.  That file is kept in git and the
align stage (auto_lines.py) applies a reading only while the line's box is unchanged, so a rerun that
detects lines differently never attaches a reading to the wrong line.
"""
import argparse
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import item_dir  # noqa: E402

ROOT = item_dir()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model that produced the readings, recorded as provenance")
    a = ap.parse_args()
    man = json.loads((ROOT / "ai" / "manifest.json").read_text(encoding="utf-8"))
    got = json.loads((ROOT / "ai" / "readings.json").read_text(encoding="utf-8"))
    store_f = ROOT / "ocr" / "ai_readings.json"
    store = json.loads(store_f.read_text(encoding="utf-8")) if store_f.exists() else {}
    added = skipped = 0
    for strip, lines in man.items():
        texts = got.get(strip)
        if texts is None or len(texts) != len(lines):
            print(f"  skip {strip}: expected {len(lines)} readings, got {None if texts is None else len(texts)}")
            skipped += len(lines)
            continue
        for l, t in zip(lines, texts):
            store[l["id"]] = {"bbox": l["bbox"], "text": unicodedata.normalize("NFC", " ".join(t.split())),
                              "model": a.model}
            added += 1
    store_f.write_text(json.dumps(dict(sorted(store.items())), ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
    print(f"{added} readings stored, {skipped} skipped -> {store_f.relative_to(ROOT.parent.parent)}; rerun the align stage")


if __name__ == "__main__":
    main()
