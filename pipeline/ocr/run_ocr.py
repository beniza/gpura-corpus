#!/usr/bin/env python3
"""Reproduce the raw Tesseract stage of the Gpura OCR demo.

Usage:  python3 ocr/run_ocr.py            (set GPURA_ITEM_DIR to the item folder, or use run.py)

For each page (p017, p018, p019) it:
  1. runs tesseract 5.3.4 with two model combinations (mal+eng and
     script/Malayalam+eng) at a few page-segmentation modes on the whole page,
     scores each run by mean word confidence (Malayalam words only); the configuration
     kept is PINNED (chosen by CER against the reviewed reading, see comparison.md);
  2. writes ocr/p0NN.tess.hocr, ocr/p0NN.tess.alto.xml, ocr/p0NN.tess.tsv for the
     chosen configuration (body pages) and ocr/p0NN.tess.choice.json with the scores;
  3. for p019 additionally crops the rotated caption and legend, rotates each crop
     upright with Pillow, OCRs it (psm 6 / 7) and maps the word boxes back to the
     unrotated page frame -> ocr/p019.rotated.json (+ the rotated runs' TSV).

The Tesseract model files are in ./tessdata (tessdata_best).
"""
import csv, io, json, os, subprocess, sys
from PIL import Image, ImageFilter, ImageOps

PAD = 30

ROOT = os.environ.get("GPURA_ITEM_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TD = os.environ.get("GPURA_TESSDATA") or os.path.join(ROOT, "tessdata")
IMG = os.path.join(ROOT, "images")
OUT = os.path.join(ROOT, "ocr")
LANGS = ["mal+eng", "script/Malayalam+eng"]
PSMS = {"p017": [3, 4, 6], "p018": [3, 4, 6], "p019": [3, 11]}
PINNED = {"p017": ("mal+eng", 6), "p018": ("mal+eng", 6), "p019": ("mal+eng", 11)}

# Rotated regions on p019, in page pixel coordinates (x, y, w, h), and the PIL
# rotation (degrees counter-clockwise) that makes the text upright.
# Text on the map reads bottom-to-top, so rotating the crop 90 deg clockwise
# (PIL angle -90 == ROTATE_270) makes it upright.
P019_ROTATED = {
    "caption": {"box": (2130, 1250, 100, 1300), "psm": 7, "thr": 150, "median": 1},
    "legend":  {"box": (1870, 1140, 230, 640), "psm": 6, "thr": 120, "median": 5},
}

if not os.path.isdir(os.path.join(TD, "script")):
    os.makedirs(os.path.join(TD, "script"), exist_ok=True)
    src = os.path.join(TD, "Malayalam.traineddata")
    dst = os.path.join(TD, "script", "Malayalam.traineddata")
    if not os.path.exists(dst):
        os.symlink(src, dst)


def tess(image, base, lang, psm, configs=("hocr", "alto", "tsv"), extra=()):
    # The custom tessdata dir has no configs/ folder, so request the output
    # renderers with -c variables instead of the "hocr alto tsv" config names.
    flags = {"hocr": "tessedit_create_hocr", "alto": "tessedit_create_alto", "tsv": "tessedit_create_tsv"}
    cfg = []
    for c in configs:
        cfg += ["-c", flags[c] + "=1"]
    cmd = ["tesseract", image, base, "--tessdata-dir", TD, "-l", lang,
           "--psm", str(psm), "--dpi", "400", "-c", "tessedit_create_txt=0", *cfg, *extra]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tsv_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def score(path):
    rows = [r for r in tsv_rows(path) if r["level"] == "5" and r["text"].strip()]
    mal = [r for r in rows if any("ഀ" <= c <= "ൿ" for c in r["text"])]
    if not mal:
        return 0.0, 0
    return sum(float(r["conf"]) for r in mal) / len(mal), len(mal)


def run_page(page, tmp):
    img = os.path.join(IMG, page + ".png")
    results = []
    for lang in LANGS:
        for psm in PSMS[page]:
            base = os.path.join(tmp, f"{page}_{lang.replace('/', '_').replace('+', '_')}_psm{psm}")
            tess(img, base, lang, psm, configs=("tsv",))
            s, n = score(base + ".tsv")
            results.append({"lang": lang, "psm": psm, "mean_conf": round(s, 2), "mal_words": n})
            print(page, lang, psm, round(s, 2), n, flush=True)
    if page in PINNED:
        # Pinned after the fact: of the candidates, this one had the lowest CER against
        # the reviewed reading (see ocr/comparison.md).  Mean confidence alone
        # (the fallback below) favours runs that drop hard words.
        best = next(r for r in results if (r["lang"], r["psm"]) == PINNED[page])
    else:
        best = max(results, key=lambda r: (r["mean_conf"] * min(1, r["mal_words"] / max(x["mal_words"] for x in results))))
    out = os.path.join(OUT, page + ".tess")
    tess(img, out, best["lang"], best["psm"])
    os.replace(out + ".xml", out + ".alto.xml")
    with open(os.path.join(OUT, page + ".tess.choice.json"), "w") as f:
        json.dump({"chosen": best, "runs": results}, f, indent=1)
    return best


def run_rotated(tmp):
    page = Image.open(os.path.join(IMG, "p019.png"))
    W, H = page.size
    res = {}
    for name, spec in P019_ROTATED.items():
        x, y, w, h = spec["box"]
        crop = page.crop((x, y, x + w, y + h)).rotate(-90, expand=True)  # clockwise 90
        # light preprocessing: grey, (median), autocontrast, threshold, 30px white pad
        g = crop.convert("L")
        if spec["median"] > 1:
            g = g.filter(ImageFilter.MedianFilter(spec["median"]))
        g = ImageOps.autocontrast(g, cutoff=2)
        g = g.point(lambda v, t=spec["thr"]: 0 if v < t else 255)
        crop = ImageOps.expand(g, PAD, 255)
        cp = os.path.join(tmp, f"p019_{name}_upright.png")
        crop.save(cp)
        best = None
        for lang in LANGS:
            base = os.path.join(tmp, f"p019_{name}_{lang.replace('/', '_').replace('+', '_')}")
            tess(cp, base, lang, spec["psm"], configs=("tsv",))
            s, n = score(base + ".tsv")
            if best is None or s > best[0]:
                best = (s, lang, base)
        words = []
        for r in tsv_rows(best[2] + ".tsv"):
            if r["level"] != "5" or not r["text"].strip():
                continue
            u, v, uw, vh = (int(r[k]) for k in ("left", "top", "width", "height"))
            u -= PAD; v -= PAD
            # Map upright-crop coords back.  Crop was rotated clockwise by 90:
            # upright (u, v) <- original crop (xc, yc) with u = h-1-yc, v = xc
            # => xc = v, yc = h-1-u.
            corners = [(u, v), (u + uw, v), (u + uw, v + vh), (u, v + vh)]
            poly = [[x + vv, y + (h - 1 - uu)] for uu, vv in corners]
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            words.append({"text": r["text"], "conf": float(r["conf"]),
                          "line_num": int(r["line_num"]), "block_num": int(r["block_num"]),
                          "polygon_page": poly,
                          "bbox_page": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]})
        os.replace(best[2] + ".tsv", os.path.join(OUT, f"p019.tess.{name}.rot.tsv"))
        res[name] = {"crop_box_page": spec["box"], "rotation": "crop rotated 90 deg clockwise to read; text orientation on page = 270 (reads bottom-to-top)",
                     "lang": best[1], "mean_conf": round(best[0], 2), "words": words}
    with open(os.path.join(OUT, "p019.rotated.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    import tempfile
    tmp = tempfile.mkdtemp(prefix="gpura_ocr_")
    if "--rotated-only" not in sys.argv:
        for p in ["p017", "p018", "p019"]:
            print(p, "->", run_page(p, tmp))
    run_rotated(tmp)
    print("done; candidate runs kept in", tmp, "(use: python3 ocr/compare.py --runs", tmp + ")")
