#!/usr/bin/env python3
"""Generic TEI stage: ocr/*.lines.json + item.json -> tei/<item>.tei.xml (TEI P5).

Works for any item whose line inventories follow the lines.json contract.  Readings and IDs are
copied verbatim; nothing here edits a reading.  Items that need a hand-built encoding name their own
builder in item.json ("tei_builder"), and run.py uses that instead.

Structure:
  <facsimile>  one <surface> per page, a <zone> per region and a nested <zone type="line"> per line
  <body>       running text in reading order: <pb/>, <fw> (page numbers, running heads), <head> starting a
               new <div>, <p> (continued across pages where lines.json says "continues"), <lb facs/>
               per printed line, <lb break="no"/> after a line whose word runs on (hyphen_end)
  <back>       review notes: weak or missing matches, and archive lines that matched nothing on the page
"""
import json
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ITEM, canvas_url, image_url, item_dir, page_ids, stamp  # noqa: E402

ROOT = item_dir()
OUT = ROOT / "tei" / f"{ROOT.name}.tei.xml"
TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"


def E(tag, parent=None, text=None, **attrs):
    a = {}
    for k, v in attrs.items():
        if v is None:
            continue
        k = {"id": f"{{{XML}}}id", "lang": f"{{{XML}}}lang"}.get(k, k)
        a[k] = str(v)
    el = etree.SubElement(parent, f"{{{TEI}}}{tag}", a) if parent is not None else \
        etree.Element(f"{{{TEI}}}{tag}", a, nsmap={None: TEI})
    if text is not None:
        el.text = text
    return el


def tail(parent, s):
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + s
    else:
        parent.text = (parent.text or "") + s


def pts(poly):
    return " ".join(f"{x},{y}" for x, y in poly)


def rect(b):
    x, y, w, h = b
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


PAGES = page_ids()
DATA = {p: json.loads((ROOT / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8")) for p in PAGES}
AUTO = any(d.get("automatic") for d in DATA.values())


# --------------------------------------------------------------------------- header
def header(tei):
    h = E("teiHeader", tei)
    fd = E("fileDesc", h)
    ts = E("titleStmt", fd)
    E("title", ts, ITEM.get("title"), type="main", lang="ml")
    canv = [d["canvas"] for d in DATA.values()]
    span = f"{min(canv)}–{max(canv)}" if len(canv) > 1 else f"{canv[0]}"
    E("title", ts, f"Gpura viewer pages {span}: {'automatic' if AUTO else 'reviewed'} TEI encoding", type="sub")
    if ITEM.get("author"):
        au = E("author", ts)
        E("persName", au, ITEM["author"], lang="en")
        if ITEM.get("author_ml"):
            E("persName", au, ITEM["author_ml"], lang="ml")
    if ITEM.get("translator"):
        rs = E("respStmt", ts)
        E("resp", rs, "translated by")
        E("persName", rs, ITEM["translator"], lang="en")
    rs = E("respStmt", ts, id="pipeline")
    E("resp", rs, "automatic layout detection, alignment of Gpura's text to lines, and encoding")
    E("name", rs, "Gpura corpus pipeline (github.com/beniza/gpura-corpus)")
    rs = E("respStmt", ts, id="gpura-ocr")
    E("resp", rs, "page text (existing OCR)")
    E("orgName", rs, "Gpura (gpura.org)")
    rs = E("respStmt", ts, id="tesseract")
    E("resp", rs, "fallback readings where Gpura's text has no matching line")
    E("name", rs, "Tesseract OCR (mal+eng)")
    models = sorted({l["ai_model"] for d in DATA.values() for r in d["regions"] for l in r.get("lines", [])
                     if l.get("source") == "ai"})
    if models:
        rs = E("respStmt", ts, id="ai")
        E("resp", rs, "readings of line images where Gpura has no text (not reviewed)")
        E("name", rs, ", ".join(models))

    ex = E("extent", fd)
    E("measure", ex, f"{len(PAGES)} page images", unit="pages", quantity=len(PAGES))
    ps = E("publicationStmt", fd)
    E("authority", ps, "Unpublished encoding produced by the Gpura corpus pipeline. Not a Gpura publication.")
    av = E("availability", ps)
    E("licence", av, "The source is in the public domain (per Gpura). This encoding is released under CC0 1.0.",
      target="https://creativecommons.org/publicdomain/zero/1.0/")

    sd = E("sourceDesc", fd)
    b = E("bibl", sd)
    E("title", b, ITEM.get("title"), lang="ml")
    if ITEM.get("title_en"):
        E("title", b, ITEM["title_en"], type="transliterated")
    if ITEM.get("author"):
        E("author", b, ITEM["author"])
    if ITEM.get("translator"):
        E("editor", b, ITEM["translator"], role="translator")
    if ITEM.get("publisher"):
        E("publisher", b, ITEM["publisher"])
    if ITEM.get("date"):
        E("date", b, ITEM["date"], when=ITEM["date"] if ITEM["date"].isdigit() else None)
    if ITEM.get("pages_total"):
        E("extent", b, f"{ITEM['pages_total']} page images" + (f"; {ITEM['dimensions']}" if ITEM.get("dimensions") else ""))
    if ITEM.get("holding"):
        E("note", b, f"Holding library: {ITEM['holding']}.", type="holding")
    E("ref", b, "Gpura item", target=ITEM["gpura_item"])
    E("ref", b, "IIIF manifest", target=ITEM["iiif_manifest"])

    ed = E("encodingDesc", h)
    pd = E("projectDesc", ed)
    E("p", pd, "Gpura corpus: a structured, machine-readable companion to Gpura's scans. The PAGE-XML and ALTO files "
               "for the same pages share this file's region and line identifiers.")
    if AUTO:
        E("samplingDecl", ed).append(E("p", None, "Line boxes were detected automatically from the page images. Each "
                                       "line's reading is Gpura's existing OCR text for that line, aligned to the "
                                       "detected line by fuzzy matching against a Tesseract reading. Nothing has "
                                       "been checked by a person. Illustrations, maps and reader handwriting are "
                                       "not encoded."))
    nz = E("editorialDecl", ed)
    E("p", E("normalization", nz), "Diplomatic: wording and spelling as in Gpura's text, which follows the print. "
      "Character encoding only: atomic chillus; NTA as ന്റ and TTA as റ്റ however the source spelled them; NFC. "
      "Where this changed Gpura's string, PAGE-XML keeps the original.")
    E("p", E("hyphenation", nz), "The print breaks words at line end without a hyphen. <lb break='no'/> marks a "
      "line that continues the previous line's word. In automatic encodings this is an estimate from the book's own "
      "vocabulary and Malayalam script rules.")
    E("p", E("interpretation", nz), "<unclear> marks a line whose reading is not Gpura's text (cert='low': "
      "Tesseract only; reason='ai-reading', cert='medium': read by an AI model from the line image) or whose "
      "match to the detected line is weak (cert='medium').")
    pf = E("profileDesc", h)
    E("language", E("langUsage", pf), "Malayalam", ident=ITEM.get("language", "ml"))
    rd = E("revisionDesc", h)
    E("change", rd, "Generated by pipeline/tei/make_tei.py from ocr/*.lines.json.", when=stamp()[:10], who="#pipeline")


# --------------------------------------------------------------------------- facsimile
def facsimile(tei):
    fx = E("facsimile", tei)
    for p in PAGES:
        d = DATA[p]
        s = E("surface", fx, id=p, n=d.get("printed_page"), ulx=0, uly=0, lrx=d["width"], lry=d["height"],
              facs=canvas_url(d["canvas"]))
        E("graphic", s, url=image_url(d["canvas"]), width=f"{d['width']}px", height=f"{d['height']}px")
        for r in d["regions"]:
            z = E("zone", s, id=r["id"], type=r["type"], points=pts(r.get("polygon") or rect(r["bbox"])),
                  rotate="270" if r.get("orientation") == 90 else None)
            for l in r.get("lines", []):
                E("zone", z, id=l["id"], type="line", points=pts(l.get("polygon") or rect(l["bbox"])))


# --------------------------------------------------------------------------- body
class Flow:
    def __init__(self, body):
        self.body, self.div, self.p, self.prev = body, None, None, None   # prev: last printed flow line

    def container(self):
        if self.div is None:
            self.div = E("div", self.body, type="text")
        return self.p if self.p is not None else self.div

    def line(self, parent, l, in_flow=True):
        brk = in_flow and self.prev is not None and self.prev.get("hyphen_end")
        if len(parent) or parent.text:
            if not brk:
                tail(parent, "\n")
        E("lb", parent, facs=f"#{l['id']}", **({"break": "no"} if brk else {}))
        text = l["text"]
        whole = [f for f in l.get("flags", []) if f["type"] == "unclear" and f["start"] <= 0 and f["end"] >= len(text)]
        if whole and text:
            f = whole[0]
            ai = f.get("source") == "ai"
            E("unclear", parent, text, id=f"f-{l['id']}-{l['flags'].index(f) + 1}", cert=f.get("cert"),
              reason="ai-reading" if ai else "no-archive-text" if f.get("cert") == "low" else "weak-match",
              resp="#ai" if ai else "#tesseract" if f.get("cert") == "low" else "#gpura-ocr")
        else:
            tail(parent, text)
        if in_flow:
            self.prev = l


def body(tei, notes):
    text = E("text", tei)
    bd = E("body", text)
    flow = Flow(bd)
    for p in PAGES:
        d = DATA[p]
        if not any(r.get("continues") for r in d["regions"]):
            flow.p = None                               # the paragraph ended on the previous page
        brk = flow.prev is not None and flow.prev.get("hyphen_end")
        E("pb", flow.container(), n=d.get("printed_page"), facs=f"#{p}", **({"break": "no"} if brk else {}))
        regions = sorted(d["regions"], key=lambda r: (r.get("reading_order") is None, r.get("reading_order") or 0))
        for r in regions:
            if not r.get("lines") or r["production"] != "printed":
                continue
            t = r["type"]
            if t in ("page-number", "header"):
                fw = E("fw", flow.container(), type="pageNum" if t == "page-number" else "header", facs=f"#{r['id']}")
                for l in r["lines"]:
                    flow.line(fw, l, in_flow=False)
                continue
            if t == "heading":
                flow.p = None
                flow.div = E("div", bd, type="section")
                hd = E("head", flow.div, facs=f"#{r['id']}")
                for l in r["lines"]:
                    flow.line(hd, l)
                continue
            if r.get("continues") and flow.p is not None:
                flow.p.set("facs", flow.p.get("facs") + f" #{r['id']}")
            else:
                flow.p = None
                flow.p = E("p", flow.container(), facs=f"#{r['id']}")
            for l in r["lines"]:
                flow.line(flow.p, l)
        for l in (l for r in d["regions"] for l in r.get("lines", [])):
            for k, f in enumerate(l.get("flags", []), 1):
                if f.get("note"):
                    notes.append((f"f-{l['id']}-{k}", f["type"], f["note"]))
        for u in d.get("unplaced", []):
            notes.append((p, "unplaced", f"Line {u['archive_line']} of Gpura's text for this page matches no printed "
                                         f"line found on the page: «{u['text']}»"))
    # a trailing pb/fw with no following text is fine; empty div is not
    for div in bd.iter(f"{{{TEI}}}div"):
        if not len(div):
            E("p", div)
    return text


def main():
    tei = E("TEI")
    tei.set(f"{{{XML}}}lang", "ml")
    header(tei)
    facsimile(tei)
    notes = []
    text = body(tei, notes)
    if notes:
        back = E("back", text)
        dv = E("div", back, type="notes")
        for target, typ, msg in notes:
            E("note", dv, msg, type=typ, target=f"#{target}", resp="#pipeline", lang="en")
    OUT.parent.mkdir(exist_ok=True)
    etree.ElementTree(tei).write(str(OUT), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
