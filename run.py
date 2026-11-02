#!/usr/bin/env python3
"""Gpura corpus harness: run the encoding pipeline for one item.

    python3 run.py items/american-aikyanadu-1971                 # page → alto → tei → html → check → site
    python3 run.py items/american-aikyanadu-1971 --stages ocr,compare
    python3 run.py items/american-aikyanadu-1971 --stages all     # includes OCR (needs Tesseract + models)

Stages, in order:
  ocr      Tesseract (mal+eng) on images/*.png        → ocr/*.tess.{hocr,alto.xml,tsv}
  compare  CER/WER of Tesseract and the archive text  → ocr/comparison.md
  (review) Human/model review producing ocr/*.lines.json. Not automated; see pipeline/ocr/review/.
  page     lines.json → PAGE-XML 2019                 → page/*.page.xml
  alto     PAGE-XML → ALTO 4.4                        → page/*.alto.xml
  tei      lines.json → TEI P5                        → tei/*.tei.xml
  html     TEI → reading view                         → tei/reading.html
  check    XSD/RELAX NG validation + TEI link checks
  site     Build the specimen explorer                → docs/specimen/<item>/

The item folder layout is: images/ ocr/ page/ tei/ item.json
"""
import argparse, glob, json, os, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PIPE = REPO / "pipeline"
DEFAULT = ["page", "alto", "tei", "html", "check", "site"]
ALL = ["ocr", "compare"] + DEFAULT


def sh(args, item):
    env = dict(os.environ, GPURA_ITEM_DIR=str(item))
    env.setdefault("GPURA_TESSDATA", str(REPO / ".cache" / "tessdata"))
    print("  $", " ".join(str(a) for a in args), flush=True)
    r = subprocess.run([str(a) for a in args], env=env, cwd=item)
    if r.returncode:
        sys.exit(f"stage failed (exit {r.returncode}): {args[1] if len(args) > 1 else args[0]}")


def tei_file(item):
    files = sorted((item / "tei").glob("*.tei.xml"))
    if not files:
        sys.exit("no tei/*.tei.xml in item (run the tei stage first)")
    return files[0]


def validate(item):
    from lxml import etree
    ok = True
    page_xsd = etree.XMLSchema(etree.parse(str(REPO / "schemas/page/pagecontent-2019-07-15.xsd")))
    alto_xsd = etree.XMLSchema(etree.parse(str(REPO / "schemas/alto/alto-4-4.xsd")))
    tei_rng = etree.RelaxNG(etree.parse(str(REPO / "schemas/tei/tei_all.rng")))
    for f in sorted((item / "page").glob("*.page.xml")):
        good = page_xsd.validate(etree.parse(str(f))); ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  PAGE 2019   {f.name}")
        for e in page_xsd.error_log: print("       ", e.line, e.message)
    for f in sorted((item / "page").glob("*.alto.xml")):
        good = alto_xsd.validate(etree.parse(str(f))); ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  ALTO 4.4    {f.name}")
        for e in alto_xsd.error_log: print("       ", e.line, e.message)
    t = tei_file(item)
    good = tei_rng.validate(etree.parse(str(t))); ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  TEI tei_all {t.name}")
    for e in list(tei_rng.error_log)[:20]: print("       ", e.line, e.message)
    if not ok:
        sys.exit("validation failed")


IIIF_CROP = re.compile(r"https://iiif\.gpura\.org/iiif/3/[^\"']*?__(\d{4})\.jpg/(\d+),(\d+),(\d+),(\d+)/[^/\"']+/(\d+)/default\.jpg")


def build_site(item):
    from PIL import Image
    name = item.name
    out = REPO / "docs" / "specimen" / name
    out.mkdir(parents=True, exist_ok=True)
    pages = sorted(Path(p).name.split(".")[0] for p in glob.glob(str(item / "ocr" / "*.lines.json")))
    for p in pages:
        im = Image.open(item / "images" / f"{p}.png").convert("RGB")
        w = 1400
        im.resize((w, round(im.height * w / im.width)), Image.LANCZOS).save(out / f"{p}.jpg", quality=80, optimize=True, progressive=True)
        for ext in ("page.xml", "alto.xml"):
            shutil.copy(item / "page" / f"{p}.{ext}", out / f"{p}.{ext}")
        n = p[1:].zfill(4)
        existing = item / "ocr" / f"gpura_existing_{n}.txt"
        if existing.exists():
            shutil.copy(existing, out / existing.name)
    shutil.copy(tei_file(item), out / "tei-source.txt")
    html = (item / "tei" / "reading.html").read_text(encoding="utf-8")

    def local_crop(m):  # IIIF region crops in the reading view → local files (the site works offline)
        canvas, x, y, cw, ch, rot = m.groups()
        fn = f"crop-{canvas}-{x}-{y}-{cw}-{ch}-r{rot}.jpg"
        src = Image.open(item / "images" / f"p{canvas[1:]}.png").convert("RGB").crop((int(x), int(y), int(x) + int(cw), int(y) + int(ch)))
        if int(rot):
            src = src.rotate(-int(rot), expand=True)
        src.thumbnail((1400, 1400), Image.LANCZOS)
        src.save(out / fn, quality=80, optimize=True, progressive=True)
        return fn
    (out / "reading.html").write_text(IIIF_CROP.sub(local_crop, html), encoding="utf-8")
    meta = json.loads((item / "item.json").read_text(encoding="utf-8")) if (item / "item.json").exists() else {}
    plist = []
    for p in pages:
        lj = json.loads((item / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8"))
        plist.append({"id": p, "canvas": lj.get("canvas"), "printed": lj.get("printed_page")})
    (out / "pages.json").write_text(json.dumps({**meta, "item": name, "pages": plist}, ensure_ascii=False, indent=1), encoding="utf-8")
    findings = item / "site" / "findings.html"
    if findings.exists():
        shutil.copy(findings, out / "findings.html")
    tmpl = REPO / "docs" / "specimen" / "explorer.html"
    shutil.copy(tmpl, out / "index.html")
    print(f"  site → {out.relative_to(REPO)}/ ({len(pages)} pages)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", help="item folder, e.g. items/american-aikyanadu-1971")
    ap.add_argument("--stages", default=",".join(DEFAULT), help="comma list, or 'all'")
    a = ap.parse_args()
    item = Path(a.item).resolve()
    stages = ALL if a.stages == "all" else [s.strip() for s in a.stages.split(",") if s.strip()]
    py = sys.executable
    for s in stages:
        print(f"[{s}]", flush=True)
        if s == "ocr": sh([py, PIPE / "ocr/run_ocr.py"], item)
        elif s == "compare": sh([py, PIPE / "ocr/compare.py"], item)
        elif s == "page": sh([py, PIPE / "page/json2page.py"], item)
        elif s == "alto": sh([py, PIPE / "page/page2alto.py"], item)
        elif s == "tei": sh([py, PIPE / "tei/make_tei.py"], item)
        elif s == "html": sh([py, PIPE / "tei/tei2html.py", tei_file(item), item / "tei" / "reading.html"], item)
        elif s == "check":
            sh([py, PIPE / "tei/check_tei.py", tei_file(item)], item)
            validate(item)
        elif s == "site": build_site(item)
        else: sys.exit(f"unknown stage: {s}")
    print("done")


if __name__ == "__main__":
    main()
