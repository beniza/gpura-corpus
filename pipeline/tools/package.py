#!/usr/bin/env python3
"""Corpus package: one downloadable ZIP per book with all its digitised representations.

    python3 pipeline/tools/package.py [item ...]        # default: every item that has a site page

Writes docs/downloads/<item>.zip and docs/downloads/index.json (sizes, page counts), containing:
  README.txt          what is inside, how it was made, provenance of the text, licence, citation, feedback
  item.json           catalogue metadata (from Gpura's Omeka S record)
  tei/                the TEI P5 edition (and the dictionary encoding, where there is one)
  page/pNNN.page.xml  PAGE-XML 2019 layout for every page (the master format)
  alto/pNNN.alto.xml  ALTO 4.4 for every page
  text/<item>.txt     plain text in reading order, one printed line per line, with page markers
  images.txt          IIIF links to Gpura's page images (not copied: they stay with Gpura)
  LICENSE.txt         CC0 1.0 for the encoding
"""
import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "downloads"
SITE = "https://beniza.github.io/gpura-corpus"
FEEDBACK = "https://github.com/beniza/gpura-corpus/issues/new?template=corpus-feedback.md"


def plain_text(item, pages):
    out = []
    for p in pages:
        d = json.loads((item / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8"))
        out.append(f"=== page {d.get('canvas')}" + (f" (printed {d['printed_page']})" if d.get("printed_page") else "") + " ===")
        regions = sorted(d["regions"], key=lambda r: (r.get("reading_order") is None, r.get("reading_order") or 0))
        for r in regions:
            for l in r.get("lines", []):
                if l.get("text"):
                    out.append(l["text"])
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def sources(item, pages):
    n = {}
    for p in pages:
        d = json.loads((item / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8"))
        for r in d["regions"]:
            for l in r.get("lines", []):
                s = l.get("source") or ("gpura" if "match" in l else "reviewed" if not d.get("automatic") else "tesseract")
                n[s] = n.get(s, 0) + 1
    return n


def readme(meta, item, pages, src):
    names = {"gpura": "Gpura's existing OCR text", "sarvam": "Sarvam Vision (Sarvam AI Document AI), where Gpura has no text",
             "ai": "an AI model reading the line image (Claude)", "tesseract": "Tesseract OCR only (marked uncertain)",
             "reviewed": "transcribed and reviewed by a person"}
    lines = "\n".join(f"  {v:6} lines  {names.get(k, k)}" for k, v in sorted(src.items(), key=lambda kv: -kv[1]))
    dict_note = ("\n  tei/*.dict.tei.xml   dictionary entries (TEI dictionaries module): headword, etymology,\n"
                 "                       senses, glosses, examples, cross-references\n") if any((item / "tei").glob("*.dict.tei.xml")) else ""
    return f"""GPURA CORPUS: SAMPLE PACKAGE
{meta.get('title', '')}
{meta.get('title_en', '')}{' · ' + meta['author'] if meta.get('author') else ''}{' · ' + meta['date'] if meta.get('date') else ''}

Source: {meta.get('gpura_item', '')}
Pages in this package: {len(pages)} of {meta.get('pages_total', '?')} (viewer pages {', '.join(str(int(p[1:])) for p in pages[:3])}{'…' if len(pages) > 3 else ''})
Packaged: {date.today().isoformat()} · {SITE}

WHAT THIS IS
A structured, machine-readable companion to Gpura's scans of this item: for every page, the text
(what the page says), the structure (where it says it: regions, lines, reading order, positions on
the scan) and the metadata (what the item is). Region and line identifiers are the same in every file.

FILES
  item.json            catalogue metadata (from Gpura's Omeka S record)
  tei/<item>.tei.xml   TEI P5 edition: running text with headings, paragraphs, page breaks, page
                       numbers and running heads; every printed line points to its zone on the scan;
                       uncertain readings marked with <unclear> and their source{dict_note}
  page/pNNN.page.xml   PAGE-XML 2019 (master layout): regions, lines, baselines, reading order, and
                       each line's readings with their provenance and confidence
  alto/pNNN.alto.xml   ALTO 4.4, generated from PAGE-XML
  text/<item>.txt      plain text in reading order, one printed line per line, page markers
  images.txt           IIIF links to each page image at Gpura (coordinates in the XML refer to these)

WHERE THE TEXT COMES FROM
{lines}
Nothing in this package has been checked by a person unless marked "reviewed". Line boxes, regions and
reading order are detected automatically. All files validate against the official PAGE 2019, ALTO 4.4
and TEI P5 (tei_all) schemas.

LICENCE
The encoding is released under CC0 1.0 (see LICENSE.txt). The source item and its page images are in
the public domain per Gpura (gpura.org, Indic Digital Archive Foundation). This is an independent
proposal, not a Gpura publication.

FEEDBACK
This is a sample shared for comment. Please tell us what works, what is missing and what is wrong:
  {FEEDBACK}
(or open an issue at https://github.com/beniza/gpura-corpus/issues). Useful: the file and line id
(e.g. p016_r02_l005), what you expected, and what you found.
"""


def package(item):
    meta = json.loads((item / "item.json").read_text(encoding="utf-8"))
    pages = sorted((f.name.split(".")[0] for f in (item / "ocr").glob("p*.lines.json")), key=lambda p: int(p[1:]))
    buf = io.BytesIO()
    root = item.name
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(f"{root}/README.txt", readme(meta, item, pages, sources(item, pages)))
        z.writestr(f"{root}/item.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        for f in sorted((item / "tei").glob("*.xml")):
            z.write(f, f"{root}/tei/{f.name}")
        for p in pages:
            for kind, folder in (("page", "page"), ("alto", "alto")):
                f = item / "page" / f"{p}.{kind}.xml"
                if f.exists():
                    z.write(f, f"{root}/{folder}/{f.name}")
        z.writestr(f"{root}/text/{root}.txt", plain_text(item, pages))
        base = meta.get("iiif_image_base", "")
        z.writestr(f"{root}/images.txt", "".join(f"{p}\t{base}{int(p[1:]):04d}.jpg/full/max/0/default.jpg\n" for p in pages))
        z.write(REPO / "LICENSE-data", f"{root}/LICENSE.txt")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{root}.zip").write_bytes(buf.getvalue())
    return {"item": root, "pages": len(pages), "bytes": len(buf.getvalue())}


def main():
    names = sys.argv[1:] or sorted(p.name for p in (REPO / "docs" / "specimen").iterdir() if (p / "pages.json").exists())
    res = []
    for n in names:
        r = package(REPO / "items" / n)
        res.append(r)
        print(f"  {n}: {r['pages']} pages, {r['bytes'] / 1e6:.1f} MB")
    idx = OUT / "index.json"
    old = {r["item"]: r for r in json.loads(idx.read_text(encoding="utf-8")) if r["item"] != "*"} if idx.exists() else {}
    old.update({r["item"]: r for r in res})
    # the whole sample corpus in one ZIP: every book's package, side by side
    allz = OUT / "gpura-corpus-sample.zip"
    with zipfile.ZipFile(allz, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r in sorted(old.values(), key=lambda r: r["item"]):
            with zipfile.ZipFile(OUT / f"{r['item']}.zip") as one:
                for info in one.infolist():
                    z.writestr(f"gpura-corpus-sample/{info.filename}", one.read(info))
        z.write(REPO / "LICENSE-data", "gpura-corpus-sample/LICENSE.txt")
    old["*"] = {"item": "*", "file": allz.name, "books": len(old), "bytes": allz.stat().st_size}
    print(f"  all: {allz.name}, {allz.stat().st_size / 1e6:.1f} MB")
    idx.write_text(json.dumps(sorted(old.values(), key=lambda r: r["item"]), indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
