#!/usr/bin/env python3
"""Layout-encoding stage: ocr/p0NN.lines.json -> page/p0NN.page.xml (PAGE 2019-07-15).

Readings and IDs are copied verbatim from the OCR-stage JSON (the contract).
Usage: python3 page/json2page.py            (set GPURA_ITEM_DIR to the item folder, or use run.py)
"""
import os
import json
import re
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ITEM, PROV, canvas_url, image_url, item_dir, page_ids, stamp  # noqa: E402

ROOT = item_dir()
NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOC = NS + " " + NS + "/pagecontent.xsd"

TEXT_TYPE = {  # lines.json type -> (PAGE TextRegion @type, structure tag or None)
    "paragraph": ("paragraph", None),
    "heading": ("heading", None),
    "header": ("header", None),
    "page-number": ("page-number", None),
    "caption": ("caption", None),
    "marginalia": ("marginalia", None),
    "legend": ("other", "legend"),
    "map-label": ("other", "map-label"),
}
# Per-region facts that used to be hard-coded here now live in lines.json:
#   production_detail  PAGE @production for handwriting (handwritten-printscript | handwritten-cursive)
#   script             "Latn" (English) or "Zyyy" (undetermined, e.g. a lone digit); default Malayalam
#   continues          id of the region on the previous page that this paragraph continues
FLAG_TAG = {"underline": "underlined", "unclear": "unclear", "damage": "damage", "ink-over": "inkOver"}
LINE_ID_RE = re.compile(r"p\d{3,}_r\d{2,}_l\d{3,}")
REGION_ID_RE = re.compile(r"p\d{3,}_r\d{2,}(?!\d|_l)")


def E(parent, tag, **attrs):
    el = etree.SubElement(parent, f"{{{NS}}}{tag}")
    for k, v in attrs.items():
        if v is not None:
            el.set(k, str(v))
    return el


def pts(poly):
    return " ".join(f"{int(x)},{int(y)}" for x, y in poly)


def rect(b):
    x, y, w, h = b
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def clean(s):
    """Make a string safe inside a PAGE custom-attribute value (Transkribus escaping)."""
    return s.replace("\\", "\\u005c").replace(";", "\\u003b").replace("{", "\\u007b").replace("}", "\\u007d").replace(":", "\\u003a")


def line_custom(idx, line):
    parts = [f"readingOrder {{index:{idx};}}"]
    for f in line.get("flags", []):
        tag = FLAG_TAG.get(f["type"], f["type"])
        kv = [f"offset:{f['start']}", f"length:{f['end'] - f['start']}"]
        if f.get("hand"):
            kv.append(f"hand:{f['hand']}")
        if f.get("cert"):
            kv.append(f"cert:{f['cert']}")
        if f["type"] == "underline":
            m = REGION_ID_RE.search(f.get("note", ""))
            if m:
                kv.append(f"graphic:{m.group(0)}")
        parts.append(f"{tag} {{{'; '.join(kv)};}}")
    if line.get("hyphen_end"):
        # word continues on the next line; the print shows no hyphen
        parts.append(f"hyphenEnd {{offset:{len(line['text'])}; length:0; printed:false;}}")
    return " ".join(parts)


def line_comments(line):
    out = []
    for f in line.get("flags", []):
        if f.get("note"):
            out.append(f"[{f['type']} {f['start']}-{f['end']}] {f['note']}")
    if line.get("hyphen_end"):
        out.append("[hyphen_end] last word continues on the next line without a printed hyphen")
    return " | ".join(out) or None


def continuation_note(prev_rid):
    """Comment for a region that continues a paragraph from the previous page."""
    prev_page = prev_rid.split("_")[0]
    prev = json.loads((ROOT / "ocr" / f"{prev_page}.lines.json").read_text(encoding="utf-8"))
    last = next(r for r in prev["regions"] if r["id"] == prev_rid)["lines"][-1]
    s = f" continues paragraph {prev_rid} ({prev_page}.page.xml)"
    if last.get("hyphen_end"):
        s += f"; first word completes {last['id']} '{last['text'].split()[-1]}-'"
    return s + " "


def build(page_id, now):
    data = json.loads((ROOT / "ocr" / f"{page_id}.lines.json").read_text(encoding="utf-8"))
    n = int(data["canvas"])
    regions = data["regions"]
    line_parent = {l["id"]: r["id"] for r in regions for l in r.get("lines", [])}
    rtype = {r["id"]: r["type"] for r in regions}

    root = etree.Element(f"{{{NS}}}PcGts", nsmap={None: NS, "xsi": XSI})
    root.set(f"{{{XSI}}}schemaLocation", SCHEMA_LOC)
    root.set("pcGtsId", f"{page_id}_pcgts")

    md = E(root, "Metadata")
    E(md, "Creator").text = "Gpura digitisation pipeline demo - layout-encoding stage (page/json2page.py, lxml)"
    E(md, "Created").text = now
    E(md, "LastChange").text = now
    E(md, "Comments").text = (
        f"Source: {ITEM['source_label']}, Gpura archive, IIIF canvas {n}, "
        f"printed page {data['printed_page']}. Layout and readings come from ocr/{page_id}.lines.json: "
        f"{PROV['page_comment']} Coordinates are pixels of the full-resolution "
        f"scan ({data['width']} x {data['height']}) assumed identical to the IIIF full/max image. "
        "Line-level flags (underlined/unclear/damage/inkOver/hyphenEnd) are in TextLine/@custom "
        "(Transkribus-style 'tag {offset:N; length:M; ...}' code-point offsets) with notes in @comments."
    )
    E(md, "MetadataItem", type="other", name="iiif-canvas", value=canvas_url(n))
    if data.get("printed_page"):
        E(md, "MetadataItem", type="other", name="printed-page-number", value=data["printed_page"])

    page = E(root, "Page", imageFilename=image_url(n), imageWidth=data["width"],
             imageHeight=data["height"], type="content", primaryLanguage="Malayalam",
             primaryScript="Mlym - Malayalam", readingDirection="left-to-right", textLineOrder="top-to-bottom")
    page.append(etree.Comment(f" IIIF canvas: {canvas_url(n)} "))

    # ---- ReadingOrder
    ordered = sorted((r for r in regions if r.get("reading_order") is not None), key=lambda r: r["reading_order"])
    if ordered:
        ro = E(page, "ReadingOrder")
        og = E(ro, "OrderedGroup", id=f"{page_id}_ro", caption="printed text flow (lines.json reading_order)")
    i = 0
    for r in ordered:
        E(og, "RegionRefIndexed", index=i, regionRef=r["id"])
        i += 1
    marg = [r for r in regions if r["type"] == "marginalia"]
    if marg:
        ug = E(og, "UnorderedGroupIndexed", id=f"{page_id}_ro_marginalia", index=i,
               caption="handwritten reader marginalia (no reading order)")
        i += 1
        for r in marg:
            E(ug, "RegionRef", regionRef=r["id"])
    labels = [r for r in regions if r["type"] == "map-label"]
    if labels:
        ug = E(og, "UnorderedGroupIndexed", id=f"{page_id}_ro_maplabels", index=i,
               caption="labels printed on the map (no reading order)")
        for r in labels:
            E(ug, "RegionRef", regionRef=r["id"])

    # ---- Relations (graphic/marginalia/damage -> text region they refer to; caption/legend -> image)
    rels = []
    images = [r["id"] for r in regions if r["type"] == "image"]
    for r in regions:
        if r["type"] in ("caption", "legend") and images:
            rels.append((r["id"], images[0], f"{r['type']} of the map/image"))
        if r["type"] in ("annotation-graphic", "marginalia", "damage"):
            texts = [r.get("note", "")] + [f.get("note", "") for l in r.get("lines", []) for f in l.get("flags", [])]
            seen = []
            for t in texts:
                for lid in LINE_ID_RE.findall(t):
                    if lid in line_parent and lid not in seen and line_parent[lid] != r["id"]:
                        seen.append(lid)
            for lid in seen:
                verb = {"annotation-graphic": "reader mark at", "marginalia": "marginal note refers to",
                        "damage": "damage affects"}[r["type"]]
                rels.append((r["id"], line_parent[lid], f"{verb} TextLine {lid}"))
    if rels:
        rs = E(page, "Relations")
        for k, (s, t, c) in enumerate(rels, 1):
            rel = E(rs, "Relation", id=f"{page_id}_rel{k:02d}", type="link", comments=c)
            E(rel, "SourceRegionRef", regionRef=s)
            E(rel, "TargetRegionRef", regionRef=t)

    # ---- Regions (document order = lines.json order)
    for r in regions:
        rid, t = r["id"], r["type"]
        poly = r.get("polygon") or rect(r["bbox"])
        orient = r.get("orientation", 0) or None
        if t in TEXT_TYPE:
            ptype, struct = TEXT_TYPE[t]
            hand = r.get("production") == "handwritten"
            prod = r.get("production_detail", "handwritten-cursive") if hand else "printed"
            lang, script = ("Malayalam", "Mlym - Malayalam")
            if r.get("script") == "Latn":
                lang, script = "English", "Latn - Latin"
            elif r.get("script") == "Zyyy":
                lang, script = None, "Zyyy - Code for undetermined script"
            custom = []
            if r.get("reading_order") is not None:
                custom.append(f"readingOrder {{index:{r['reading_order'] - 1};}}")
            if struct:
                custom.append(f"structure {{type:{struct};}}")
            if r.get("hand"):
                custom.append(f"hand {{ink:{r['hand']};}}")
            reg = E(page, "TextRegion", id=rid, custom=" ".join(custom) or None, comments=r.get("note"),
                    continuation="true" if r.get("continues") else None,
                    orientation=orient, type=ptype, readingDirection="left-to-right",
                    textLineOrder="top-to-bottom", primaryLanguage=lang, primaryScript=script, production=prod)
            if r.get("continues"):
                reg.append(etree.Comment(continuation_note(r["continues"])))
            E(reg, "Coords", points=pts(poly))
            for li, l in enumerate(r.get("lines", [])):
                tl = E(reg, "TextLine", id=l["id"], primaryLanguage=lang, primaryScript=script,
                       readingDirection="left-to-right", production=prod,
                       custom=line_custom(li, l), comments=line_comments(l), index=li)
                E(tl, "Coords", points=pts(l.get("polygon") or rect(l["bbox"])))
                E(tl, "Baseline", points=pts(l["baseline"]))
                if l["text"]:
                    tess_only = data.get("automatic") and any(f.get("type") == "unclear" and f.get("cert") == "low" for f in l.get("flags", []))
                    te = E(tl, "TextEquiv", index=1, comments=PROV["text1_ai"] + f" ({l['ai_model']})" if l.get("source") == "ai"
                                 else PROV["text1_tesseract" if tess_only else "text1"])
                    E(te, "Unicode").text = l["text"]
                    if l.get("text_tesseract"):
                        te2 = E(tl, "TextEquiv", index=2,
                                conf=None if l.get("conf") is None else f"{l['conf']:.3f}",
                                comments=PROV["text2"])
                        E(te2, "Unicode").text = l["text_tesseract"]
                    if l.get("text_archive"):
                        E(E(tl, "TextEquiv", index=3, comments=PROV["text3"]), "Unicode").text = l["text_archive"]
                else:
                    tl.append(etree.Comment(" NOT TRANSCRIBED: label too faint/illegible; no TextEquiv emitted "
                                            "on purpose (see @comments for a cautious identification) "))
                if hand and r.get("hand") == "blue-ink":
                    E(tl, "TextStyle", textColour="blue")
            texts = [l["text"] for l in r.get("lines", [])]
            if any(texts):
                te = E(reg, "TextEquiv", index=1, comments="lines joined with newline")
                E(te, "Unicode").text = "\n".join(texts)
        elif t == "image":
            reg = E(page, "ImageRegion", id=rid, comments=r.get("note"), orientation=orient,
                    colourDepth="greyscale", embText="true")
            E(reg, "Coords", points=pts(poly))
        elif t == "annotation-graphic":
            reg = E(page, "GraphicRegion", id=rid, custom=f"hand {{ink:{r['hand']};}}" if r.get("hand") else None,
                    comments=r.get("note"), orientation=orient, type="handwritten-annotation", embText="false")
            E(reg, "Coords", points=pts(poly))
        elif t == "damage":
            reg = E(page, "NoiseRegion", id=rid, custom="structure {type:damage;}", comments=r.get("note"))
            E(reg, "Coords", points=pts(poly))
        else:
            raise SystemExit(f"unmapped region type {t} ({rid})")
    return etree.ElementTree(root)


def main():
    now = stamp()
    for pid in sys.argv[1:] or page_ids():
        tree = build(pid, now)
        out = ROOT / "page" / f"{pid}.page.xml"
        tree.write(str(out), xml_declaration=True, encoding="UTF-8", pretty_print=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
