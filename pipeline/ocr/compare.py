#!/usr/bin/env python3
"""CER / WER of raw Tesseract and the existing Gpura OCR against the reviewed
`text` readings in ocr/p0NN.lines.json.  Set GPURA_ITEM_DIR to the item folder (or use run.py):

    python3 ocr/compare.py [--runs DIR]     (DIR = temp dir of run_ocr.py with all candidate TSVs)

Prints a JSON summary used for ocr/comparison.md.
"""
import csv, glob, json, os, re, sys, unicodedata
from rapidfuzz.distance import Levenshtein

ROOT = os.environ.get("GPURA_ITEM_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZW = "‌‍"
BODY_TYPES = {"paragraph", "heading"}


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def norm_enc(s):
    """Neutralise encoding-only differences (NTA/TTA, chillu forms, ZWJ/ZWNJ, NFC)."""
    s = unicodedata.normalize("NFC", s)
    # legacy chillu: C + virama + ZWJ  -> atomic chillu
    for c, ch in {"ന": "ൻ", "ര": "ർ", "ല": "ൽ", "ള": "ൾ", "ണ": "ൺ"}.items():
        s = s.replace(c + "്‍", ch)
    s = s.replace("ൎ", "ർ")                     # dot reph
    # NTA variants: visual-order e-sign (ൻ + െ + റ) -> ന്റെ, then ൻ(്)റ -> ന്റ
    s = s.replace("ൻെറ", "ന്റെ").replace("ൻേറ", "ന്റേ")
    s = s.replace("ൻ്റ", "ന്റ").replace("ൻറ", "ന്റ")
    # visual-order mis-encoding of NTA + e/ee sign: ന + െ/േ + റ  ->  ന്റെ / ന്റേ
    s = re.sub("ന([െേ])റ(?![ാ-ൌ])", lambda m: "ന്റ" + m.group(1), s)
    # TTA: bare RRA RRA -> റ്റ (only where not already joined by virama)
    s = re.sub("റ(?!്)റ", "റ്റ", s)
    s = s.replace("റ്റ്റ", "റ്റ")
    for z in ZW:
        s = s.replace(z, "")
    return s


def cer(ref, hyp):
    return Levenshtein.distance(ref, hyp) / max(1, len(ref))


def wer(ref, hyp):
    r, h = ref.split(" "), hyp.split(" ")
    return Levenshtein.distance(r, h) / max(1, len(r))


def scores(ref, hyp):
    a = (ws(ref), ws(hyp))
    b = (ws(norm_enc(ref)), ws(norm_enc(hyp)))
    return {"cer_norm": cer(*b), "wer_norm": wer(*b), "cer_raw": cer(*a), "wer_raw": wer(*a),
            "ref_chars": len(b[0]), "hyp_chars": len(b[1]),
            "edits_norm": Levenshtein.distance(*b)}


def ref_text(d, types):
    return " ".join(l["text"] for r in d["regions"] if r["type"] in types for l in r["lines"] if l["text"])


def body_boxes(d, types):
    return [l["bbox"] for r in d["regions"] if r["type"] in types for l in r["lines"]]


def tess_text(tsv, boxes):
    rows = list(csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE))
    out = []
    for r in rows:
        if r["level"] != "5" or not r["text"].strip():
            continue
        x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
        cx, cy = x + w / 2, y + h / 2
        if any(b[0] - 10 <= cx <= b[0] + b[2] + 10 and b[1] <= cy <= b[1] + b[3] for b in boxes):
            out.append(r["text"])
    return " ".join(out)


def existing(page):
    n = int(page[1:])
    return open(os.path.join(ROOT, "ocr", f"gpura_existing_{n:04d}.txt"), encoding="utf-8").read().splitlines()


def main():
    runs = None
    if "--runs" in sys.argv:
        runs = sys.argv[sys.argv.index("--runs") + 1]
    res = {}
    for page in ("p017", "p018"):
        d = json.load(open(os.path.join(ROOT, "ocr", f"{page}.lines.json"), encoding="utf-8"))
        ref = ref_text(d, BODY_TYPES)
        boxes = body_boxes(d, BODY_TYPES)
        ex = existing(page)
        if page == "p018":
            ex = ex[3:]            # drop page number "2", blank, running head
        exb = " ".join(ex)
        res[page] = {"tesseract": scores(ref, tess_text(os.path.join(ROOT, "ocr", f"{page}.tess.tsv"), boxes)),
                     "existing": scores(ref, exb)}
        if runs:
            res[page]["candidates"] = {os.path.basename(f)[5:-4]: scores(ref, tess_text(f, boxes))["cer_norm"]
                                       for f in sorted(glob.glob(os.path.join(runs, f"{page}_*psm*.tsv")))}
        # running head check
        if page == "p018":
            hd = [l for r in d["regions"] if r["type"] == "header" for l in r["lines"]][0]
            res[page]["header"] = {"ref": hd["text"], "tesseract": hd["text_tesseract"], "existing": existing(page)[2],
                                   "tess": scores(hd["text"], hd["text_tesseract"]),
                                   "exist": scores(hd["text"], existing(page)[2])}
    # p019: all printed text we transcribed (header, page no., caption, legend, legible labels)
    d = json.load(open(os.path.join(ROOT, "ocr", "p019.lines.json"), encoding="utf-8"))
    types = {"header", "caption", "legend", "map-label"}
    ref = ref_text(d, types)
    tt = " ".join(l["text_tesseract"] for r in d["regions"] if r["type"] in types for l in r["lines"] if l["text_tesseract"])
    ex = existing("p019")
    ex_printed = " ".join(x for x in ex if x.strip() and not re.match(r"^[A-Za-z .]+$", x))
    res["p019"] = {"ref": ref, "tesseract_hyp": tt, "existing_hyp": ex_printed,
                   "tesseract": scores(ref, tt), "existing": scores(ref, ex_printed)}
    hw_ref = " ".join(l["text"] for r in d["regions"] if r["type"] == "marginalia" for l in r["lines"])
    hw_ex = " ".join(x for x in ex if re.match(r"^[A-Za-z .]+$", x) and x.strip() and not x.startswith("This image"))
    res["p019"]["handwriting"] = {"ref": hw_ref, "existing": hw_ex, "scores": scores(hw_ref, hw_ex)}
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
