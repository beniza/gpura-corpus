"""Shared helpers: the item folder, its item.json and its pages.

Every stage runs with GPURA_ITEM_DIR set (run.py does this).  Item-specific facts
(metadata, IIIF URLs, wording of provenance notes) live in <item>/item.json, never in
the stage scripts.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ["GPURA_ITEM_DIR"]) if os.environ.get("GPURA_ITEM_DIR") else None


def item_dir():
    if ROOT is None:
        raise SystemExit("GPURA_ITEM_DIR is not set (run the stage through run.py)")
    return ROOT


def load_item():
    p = item_dir() / "item.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


ITEM = load_item() if ROOT is not None else {}

# Provenance wording for automatic encodings; a reviewed item overrides it in item.json "provenance".
AUTO_PROVENANCE = {
    "page_comment": "line boxes detected automatically (projection profiles); TextEquiv index=1 is Gpura's existing OCR "
                    "text for the line, aligned automatically and NOT reviewed; index=2 is the Tesseract reading used "
                    "for the alignment (mal+eng) with its mean word confidence; index=3 (where present) is Gpura's "
                    "string before the corpus encoding rules were applied.",
    "text1": "Gpura's existing OCR text, aligned automatically (not reviewed)",
    "text1_tesseract": "Tesseract reading (mal+eng); Gpura has no matching text for this line (not reviewed)",
    "text2": "Tesseract reading used for alignment (own encoding)",
    "text3": "Gpura's original string, before encoding normalisation",
    "alto_alternative": "Tesseract reading used for alignment",
    "alto_step": "Line boxes detected automatically; line text is Gpura's existing OCR aligned to them (ocr/*.lines.json), "
                 "not reviewed; ALTERNATIVE = Tesseract reading used for the alignment.",
    "alto_software": "Gpura corpus pipeline (auto_lines.py) + Tesseract",
}
PROV = {**AUTO_PROVENANCE, **ITEM.get("provenance", {})}
PROV.setdefault("text1_tesseract", AUTO_PROVENANCE["text1_tesseract"])


def page_ids():
    """Pages of the item that have a line inventory (ocr/<page>.lines.json), in canvas order."""
    ids = [p.name.split(".")[0] for p in (item_dir() / "ocr").glob("*.lines.json")]
    return sorted(ids, key=canvas_no)


def page_id(n):
    return f"p{int(n):03d}"


def canvas_no(page):
    return int(re.sub(r"\D", "", page))


def canvas_url(n):
    return ITEM["canvas_base"].format(n=int(n))


def image_url(n):
    return ITEM["iiif_image_base"] + f"{int(n):04d}.jpg/full/max/0/default.jpg"


def stamp():
    """Timestamp written into generated files.  item.json 'generated' pins it so reruns are byte-identical."""
    if ITEM.get("generated"):
        return ITEM["generated"]
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return datetime.fromtimestamp(int(os.environ["SOURCE_DATE_EPOCH"]), timezone.utc).isoformat()
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def page_image(page):
    """Local scan for a page id (png from the specimen, jpg from fetch)."""
    for ext in ("png", "jpg"):
        f = item_dir() / "images" / f"{page}.{ext}"
        if f.exists():
            return f
    raise SystemExit(f"no image for {page} in {item_dir() / 'images'}")
