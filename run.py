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
    files = sorted(f for f in (item / "tei").glob("*.tei.xml") if not f.name.endswith(".dict.tei.xml"))
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
    (item / "checks.json").write_text(json.dumps({          # read by the site stage (book page, page view header)
        "page_valid": len(list((item / "page").glob("*.page.xml"))), "alto_valid": len(list((item / "page").glob("*.alto.xml"))),
        "tei_valid": bool(good), "contract": True, "ok": bool(ok)}, indent=1) + "\n", encoding="utf-8", newline="\n")
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
        w = 1200
        im.resize((w, round(im.height * w / im.width)), Image.LANCZOS).save(out / f"{p}.jpg", quality=72, optimize=True, progressive=True)
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
    summary = book_summary(item, pages, out)
    (out / "pages.json").write_text(json.dumps({**meta, "item": name, "tei": tei_file(item).name, "pages": plist,
                                                "summary": summary}, ensure_ascii=False, indent=1), encoding="utf-8")
    findings = item / "site" / "findings.html"
    if findings.exists():
        shutil.copy(findings, out / "findings.html")
    tmpl = REPO / "docs" / "specimen" / "explorer.html"
    shutil.copy(tmpl, out / "index.html")
    print(f"  site → {out.relative_to(REPO)}/ ({len(pages)} pages)")
    subprocess.run([sys.executable, str(REPO / "pipeline" / "tools" / "package.py"), name], check=True)   # downloads/<item>.zip
    book_index()


SOURCE_NAMES = {"reviewed": "checked line by line against the scan (model-made, not yet verified by a person)", "gpura": "Gpura's existing OCR",
                "sarvam": "Sarvam Vision (where Gpura has no text)", "ai": "an AI reading of the line image",
                "tesseract": "Tesseract OCR only (uncertain)"}
CHAPTER = re.compile(r"^\s*(അദ്ധ്യായം|അധ്യായം|ഭാഗം|പ്രകരണം|chapter|part)(?![^\W\d_])", re.I)


def line_source(l, automatic):
    return l.get("source") or (("gpura" if "match" in l else "tesseract") if automatic else "reviewed")


def toc_from_tei(item):
    """Table of contents from the TEI headings: grouped per page, stamps and catalogue numbers left out
    (no Malayalam or too few letters, or another Indic script), and only chapter openings where the book
    labels its chapters (അദ്ധ്യായം, Chapter …)."""
    from lxml import etree
    NS = "{http://www.tei-c.org/ns/1.0}"
    t = etree.parse(str(tei_file(item)))
    groups = []
    for h in t.iter(NS + "head"):
        txt = " ".join("".join(h.itertext()).split())
        page = (h.get("facs") or "#").lstrip("#").split("_")[0]
        letters = sum(1 for c in txt if "അ" <= c <= "ഹ")
        other_indic = any("ऀ" <= c <= "೿" for c in txt)
        if letters < 3 or other_indic or not page:
            continue
        if groups and groups[-1]["page"] == page:
            groups[-1]["title"] += " · " + txt
        else:
            groups.append({"page": page, "title": txt})
    chapters = [g for g in groups if CHAPTER.search(g["title"])]
    if len(chapters) < 3:
        return groups
    first = groups.index(chapters[0])
    if first > 0 and int(groups[first - 1]["page"][1:]) < int(chapters[0]["page"][1:]):
        chapters.insert(0, groups[first - 1])         # an unlabelled first chapter (its label was not read as a heading)
    return chapters


def book_summary(item, pages, out):
    """Per-page data files for the reader (data/pNNN.json) and the book's summary (book.json)."""
    meta = item_json(item)
    data = out / "data"
    data.mkdir(exist_ok=True)
    sources, reviewed, non_text, plist = {}, True, 0, []
    for p in pages:
        lj = json.loads((item / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8"))
        auto = bool(lj.get("automatic"))
        reviewed &= not auto
        non_text += bool(lj.get("non_text"))
        regions, n = [], 0
        for r in sorted(lj["regions"], key=lambda r: (r.get("reading_order") is None, r.get("reading_order") or 0)):
            ls = []
            for l in r.get("lines", []):
                src = line_source(l, auto)
                sources[src] = sources.get(src, 0) + 1
                ls.append({"id": l["id"], "bbox": l["bbox"], "text": l.get("text", ""), "src": src,
                           **({"unclear": True} if any(f.get("type") == "unclear" for f in l.get("flags", [])) else {})})
            n += len(ls)
            regions.append({"id": r["id"], "type": r["type"], "production": r.get("production", "printed"),
                            "bbox": r.get("bbox"), "lines": ls})
        rec = {"id": p, "canvas": lj.get("canvas"), "printed": lj.get("printed_page"), "width": lj["width"],
               "height": lj["height"], "image": f"{p}.jpg", "regions": regions, "unplaced": len(lj.get("unplaced", [])),
               **({"non_text": lj["non_text"]} if lj.get("non_text") else {})}
        (data / f"{p}.json").write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
        plist.append({"id": p, "canvas": lj.get("canvas"), "printed": lj.get("printed_page"), "lines": n})
    checks = json.loads((item / "checks.json").read_text(encoding="utf-8")) if (item / "checks.json").exists() else {}
    total = sum(sources.values())
    if reviewed:
        status = meta.get("status") or "Reviewed by a person."
    else:
        parts = [f"{SOURCE_NAMES.get(k, k)} ({v:,} lines)" for k, v in sorted(sources.items(), key=lambda kv: -kv[1])]
        status = ("Automatic encoding, not reviewed by a person: line boxes, regions and reading order detected by the "
                  "pipeline; text from " + "; ".join(parts) + ".")
    cover = next((x["id"] for x in plist if x["lines"] >= 3), plist[0]["id"] if plist else None)
    summary = {"reviewed": reviewed, "sources": sources, "lines": total, "pages_encoded": len(pages),
               "non_text_pages": non_text, "status": status, "checks": checks, "cover": cover}
    book = {k: meta.get(k) for k in ("title", "title_en", "author", "author_ml", "translator", "publisher", "publisher_ml",
                                     "printer", "date", "pages_total", "dimensions", "holding", "digitized", "rights",
                                     "gpura_item", "iiif_manifest")}
    book.update({"item": item.name, "summary": summary, "pages": plist, "toc": toc_from_tei(item),
                 "tei": "tei-source.txt", "dictionary": (out / "dictionary.html").exists() or
                 any((item / "tei").glob("*.dict.tei.xml"))})
    (out / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return summary


def ensure_images(item):
    """Scans are not kept in git: download any that are missing from Gpura's IIIF image service."""
    import urllib.request
    meta = item_json(item)
    pages = {int(Path(f).name[1:4]) for f in glob.glob(str(item / "ocr" / "p*.lines.json"))}
    pages |= set(meta.get("canvases_encoded", []))
    (item / "images").mkdir(exist_ok=True)
    for n in sorted(pages):
        if any((item / "images" / f"p{n:03d}.{e}").exists() for e in ("png", "jpg")):
            continue
        url = meta["iiif_image_base"] + f"{n:04d}.jpg/full/max/0/default.jpg"
        print(f"  downloading scan {n} from Gpura", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "gpura-corpus-pipeline (+https://github.com/beniza/gpura-corpus)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            (item / "images" / f"p{n:03d}.jpg").write_bytes(r.read())


def book_index():
    """docs/specimen/index.json: every book on the site, read by docs/nav.js for the Books menu."""
    books = []
    for pj in sorted((REPO / "docs" / "specimen").glob("*/pages.json")):
        m = json.loads(pj.read_text(encoding="utf-8"))
        src = REPO / "items" / m["item"] / "ocr"
        auto = any(json.loads(f.read_text(encoding="utf-8")).get("automatic") for f in src.glob("*.lines.json"))
        sm = m.get("summary") or {}
        books.append({"item": m["item"], "title": m.get("title"), "title_en": m.get("title_en"), "date": m.get("date"),
                      "author": m.get("author"), "pages": len(m.get("pages", [])), "pages_total": m.get("pages_total"),
                      "automatic": auto, "cover": sm.get("cover"), "lines": sm.get("lines"), "sources": sm.get("sources")})
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
    if set(stages) & {"align", "ocr", "ai-export", "sarvam", "site"}:
        ensure_images(item)
    for s in stages:
        print(f"[{s}]", flush=True)
        if s == "fetch":
            meta = item_json(item)
            pages = a.pages or ",".join(str(n) for n in meta.get("canvases_encoded", []))
            sh([py, PIPE / "fetch/gpura.py", meta.get("gpura_item", item.name), "--items-dir", item.parent]
               + (["--pages", pages] if pages else []), item)
        elif s == "align": sh([py, PIPE / "align/auto_lines.py"], item)
        elif s == "ai-export": sh([py, PIPE / "ai/export_strips.py"], item)
        elif s == "sarvam": sh([py, PIPE / "fetch/sarvam_text.py"], item)
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
