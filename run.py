#!/usr/bin/env python3
"""Gpura corpus harness: run the encoding pipeline for one item.

Any Gpura book, from its link (fetches metadata, page images and Gpura's text, then encodes):

    python3 run.py https://gpura.org/item/<slug> --pages 17-19      # default: every page of the book
    python3 run.py items/<slug>                                     # re-run on an item already fetched

The reviewed specimen:

    python3 run.py items/american-aikyanadu-1971                  # align skips reviewed pages
    python3 run.py items/american-aikyanadu-1971 --stages ocr,compare   # specimen research stages

Stages, in order:
  fetch    Gpura API + IIIF manifest → item.json, images/pNNN.jpg, ocr/gpura_existing_NNNN.txt
  align    detect lines, align Gpura's text to them  → ocr/pNNN.lines.json (automatic; reviewed files untouched)
  page     lines.json → PAGE-XML 2019                 → page/*.page.xml
  alto     PAGE-XML → ALTO 4.4                        → page/*.alto.xml
  tei      lines.json → TEI P5                        → tei/*.tei.xml
  html     TEI → reading view                         → tei/reading.html
  check    XSD/RELAX NG validation + TEI link checks
  site     Build the specimen explorer                → docs/specimen/<item>/
Specimen-only research stages (need its hand-tuned settings):
  ocr      Tesseract (mal+eng) on images/*.png        → ocr/*.tess.{hocr,alto.xml,tsv}
  compare  CER/WER of Tesseract and the archive text  → ocr/comparison.md

The item folder layout is: images/ ocr/ page/ tei/ item.json.  Needs Tesseract for `align`
(set GPURA_TESSERACT if it is not on PATH) and the models from pipeline/tools/fetch_models.sh.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PIPE = REPO / "pipeline"
DEFAULT = ["align", "page", "alto", "tei", "html", "check", "site"]
ALL = ["ocr", "compare"] + DEFAULT


def sh(args, item, capture=False):
    env = dict(os.environ, GPURA_ITEM_DIR=str(item), PYTHONUTF8="1")
    env.setdefault("GPURA_TESSDATA", str(REPO / ".cache" / "tessdata"))
    print("  $", " ".join(str(a) for a in args), flush=True)
    r = subprocess.run([str(a) for a in args], env=env, cwd=item, text=capture, capture_output=capture,
                       encoding="utf-8" if capture else None)
    if capture:
        print(r.stdout, end="", flush=True)
        print(r.stderr, end="", file=sys.stderr, flush=True)
    if r.returncode:
        sys.exit(f"stage failed (exit {r.returncode}): {args[1] if len(args) > 1 else args[0]}")
    return r.stdout if capture else None


def item_json(item):
    f = item / "item.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


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
    def image(p):
        return next(f for f in (item / "images" / f"{p}.png", item / "images" / f"{p}.jpg") if f.exists())
    for p in pages:
        im = Image.open(image(p)).convert("RGB")
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
        src = Image.open(image(f"p{int(canvas):03d}")).convert("RGB").crop((int(x), int(y), int(x) + int(cw), int(y) + int(ch)))
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
    (out / "pages.json").write_text(json.dumps({**meta, "item": name, "tei": tei_file(item).name, "pages": plist}, ensure_ascii=False, indent=1), encoding="utf-8")
    findings = item / "site" / "findings.html"
    if findings.exists():
        shutil.copy(findings, out / "findings.html")
    tmpl = REPO / "docs" / "specimen" / "explorer.html"
    shutil.copy(tmpl, out / "index.html")
    print(f"  site → {out.relative_to(REPO)}/ ({len(pages)} pages)")
    book_index()


def book_index():
    """docs/specimen/index.json: every book on the site, read by docs/nav.js for the Books menu."""
    books = []
    for pj in sorted((REPO / "docs" / "specimen").glob("*/pages.json")):
        m = json.loads(pj.read_text(encoding="utf-8"))
        src = REPO / "items" / m["item"] / "ocr"
        auto = any(json.loads(f.read_text(encoding="utf-8")).get("automatic") for f in src.glob("*.lines.json"))
        books.append({"item": m["item"], "title": m.get("title"), "title_en": m.get("title_en"), "date": m.get("date"),
                      "pages": len(m.get("pages", [])), "automatic": auto})
    books.sort(key=lambda b: (b["automatic"], b["item"]))
    (REPO / "docs" / "specimen" / "index.json").write_text(json.dumps(books, ensure_ascii=False, indent=1) + "\n",
                                                          encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", help="Gpura item link (or slug), or an item folder such as items/american-aikyanadu-1971")
    ap.add_argument("--stages", default=None, help="comma list, or 'all'")
    ap.add_argument("--pages", help="with a link: viewer page numbers to fetch, e.g. 17-19,25 (default: all)")
    a = ap.parse_args()
    py = sys.executable
    local = Path(a.item)
    if local.is_dir():
        item = local.resolve()
        stages = ALL if a.stages == "all" else (a.stages or ",".join(DEFAULT)).split(",")
    else:
        print("[fetch]", flush=True)
        args = [py, PIPE / "fetch/gpura.py", a.item, "--items-dir", REPO / "items"] + (["--pages", a.pages] if a.pages else [])
        item = Path(sh(args, REPO, capture=True).strip().splitlines()[-1]).resolve()
        stages = (a.stages or ",".join(DEFAULT)).split(",")
    stages = [s.strip() for s in stages if s.strip()]
    for s in stages:
        print(f"[{s}]", flush=True)
        if s == "fetch":
            meta = item_json(item)
            pages = a.pages or ",".join(str(n) for n in meta.get("canvases_encoded", []))
            sh([py, PIPE / "fetch/gpura.py", meta.get("gpura_item", item.name), "--items-dir", item.parent]
               + (["--pages", pages] if pages else []), item)
        elif s == "align": sh([py, PIPE / "align/auto_lines.py"], item)
        elif s == "ocr": sh([py, PIPE / "ocr/run_ocr.py"], item)
        elif s == "compare": sh([py, PIPE / "ocr/compare.py"], item)
        elif s == "page": sh([py, PIPE / "page/json2page.py"], item)
        elif s == "alto": sh([py, PIPE / "page/page2alto.py"], item)
        elif s == "tei": sh([py, REPO / item_json(item).get("tei_builder", "pipeline/tei/make_tei.py")], item)
        elif s == "html": sh([py, PIPE / "tei/tei2html.py", tei_file(item), item / "tei" / "reading.html"], item)
        elif s == "check":
            sh([py, PIPE / "tei/check_tei.py", tei_file(item)], item)
            validate(item)
        elif s == "site": build_site(item)
        else: sys.exit(f"unknown stage: {s}")
    print("done")


if __name__ == "__main__":
    main()
