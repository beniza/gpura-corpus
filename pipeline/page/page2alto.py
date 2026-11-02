#!/usr/bin/env python3
"""PAGE 2019 (page/p0NN.page.xml) -> ALTO 4.4 (page/p0NN.alto.xml).

Own converter, written because OCR-D page-to-alto 2.2.12 aborts on these files
(NoiseRegion unsupported; AttributeError on TextStyle/@textColour) and, even when
worked around, keeps only one String per line and drops orientation, baselines,
production, custom tags, comments and alternative readings.

What it does (see FORMAT_NOTES.md):
  * TextRegion -> TextBlock, ImageRegion/GraphicRegion/NoiseRegion -> Illustration (TYPE),
    the map with its caption/legend/labels -> ComposedBlock TYPE="map".
  * IDs are kept: region/line IDs unchanged; Strings get <lineID>_w<NNN>.
  * PAGE @orientation 90 (rotate clockwise to read) -> ALTO @ROTATION 90 (content rotated
    90 deg counter-clockwise); same number, the two standards state the sense oppositely.
  * Words: TextEquiv index=1 split on spaces; String boxes are ESTIMATED by distributing the
    line box along the baseline direction proportionally to code-point counts (tag geom_est).
  * hyphenEnd -> SUBS_TYPE HypPart1/HypPart2 + SUBS_CONTENT (no HYP: nothing is printed).
  * TextEquiv index=2 (Tesseract) -> String/ALTERNATIVE only where the token count matches.
  * custom flags (underlined/unclear/damage/inkOver) -> one OtherTag per flag instance
    (DESCRIPTION = note + exact code-point span) referenced by every overlapping String.
Usage: python3 page/page2alto.py [p017 p018 p019]   (set GPURA_ITEM_DIR to the item folder, or use run.py)
"""
import os
import re
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROV, item_dir, page_ids, stamp  # noqa: E402

ROOT = item_dir()
PC = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
ALTO = "http://www.loc.gov/standards/alto/ns-v4#"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
N = {"pc": PC}
LANG = {"Malayalam": "ml", "English": "en"}
TAG_RE = re.compile(r"(\w+)\s*\{([^}]*)\}")
STRIP_PUNCT = ".,;:!?)\"'"


def A(parent, tag, **attrs):
    el = etree.SubElement(parent, f"{{{ALTO}}}{tag}")
    for k, v in attrs.items():
        if v is not None:
            el.set(k, str(v))
    return el


def parse_custom(s):
    out = []
    for name, body in TAG_RE.findall(s or ""):
        kv = {}
        for part in body.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                kv[k.strip()] = v.strip()
        out.append((name, kv))
    return out


def points(el):
    c = el.find("pc:Coords", N)
    return [tuple(int(v) for v in p.split(",")) for p in c.get("points").split()]


def box(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def setbox(el, b):
    el.set("HPOS", str(b[0])); el.set("VPOS", str(b[1])); el.set("WIDTH", str(b[2])); el.set("HEIGHT", str(b[3]))


def shape(el, pts):
    A(A(el, "Shape"), "Polygon", POINTS=" ".join(f"{x},{y}" for x, y in pts))


def text_of(el, index):
    for te in el.findall("pc:TextEquiv", N):
        if te.get("index") == str(index):
            u = te.find("pc:Unicode", N)
            return u.text or "" if u is not None else ""
    return None


def tokens(text):
    """[(token, start, end)] code-point offsets, end exclusive."""
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[^ ]+", text)]


class Converter:
    def __init__(self, pid, all_pages):
        self.pid = pid
        self.tree = all_pages[pid]
        self.all = all_pages
        self.page = self.tree.find("pc:Page", N)
        self.tags = {}          # id -> (kind, attrs)
        self.stats = {"strings": 0, "alt_lines": 0, "alt_lines_dropped": 0, "flag_tags": 0}

    # ---------- tags
    def tag(self, tid, kind, **attrs):
        if tid not in self.tags:
            self.tags[tid] = (kind, attrs)
        return tid

    # ---------- hyphenation partner lookup (same region, or continuation region on next page)
    def next_line_first_token(self, line):
        region = line.getparent()
        lines = region.findall("pc:TextLine", N)
        i = lines.index(line)
        if i + 1 < len(lines):
            t = text_of(lines[i + 1], 1) or ""
            return t.split(" ")[0] if t else None
        n = int(self.pid[1:]) + 1
        nxt = self.all.get(f"p{n:03d}")
        if nxt is not None:
            for r in nxt.iter(f"{{{PC}}}TextRegion"):
                if r.get("continuation") == "true":
                    l0 = r.find("pc:TextLine", N)
                    t = text_of(l0, 1) or ""
                    return t.split(" ")[0] if t else None
        return None

    def prev_line_last_token(self, line):
        region = line.getparent()
        lines = region.findall("pc:TextLine", N)
        i = lines.index(line)
        prev = None
        if i > 0:
            prev = lines[i - 1]
        elif region.get("continuation") == "true":
            p = self.all.get(f"p{int(self.pid[1:]) - 1:03d}")
            if p is not None:
                # last line of the last paragraph in reading order on the previous page
                cands = [l for r in p.iter(f"{{{PC}}}TextRegion") if r.get("type") == "paragraph"
                         for l in r.findall("pc:TextLine", N)]
                prev = cands[-1] if cands else None
        if prev is None:
            return None
        if not any(n == "hyphenEnd" for n, _ in parse_custom(prev.get("custom"))):
            return None
        t = text_of(prev, 1) or ""
        return t.split(" ")[-1] if t else None

    # ---------- lines
    def convert_line(self, block, line, rotated, region_tagrefs):
        lpts = points(line)
        lb = box(lpts)
        text = text_of(line, 1)
        tess = text_of(line, 2)
        custom = parse_custom(line.get("custom"))
        tl = A(block, "TextLine", ID=line.get("id"))
        setbox(tl, lb)
        bl = line.find("pc:Baseline", N)
        if bl is not None:
            tl.set("BASELINE", bl.get("points"))
        if line.get("primaryLanguage") in LANG:
            tl.set("LANG", LANG[line.get("primaryLanguage")])
        line_tags = list(region_tagrefs)
        shape(tl, lpts)

        if not text:
            line_tags.append(self.tag("not_transcribed", "OtherTag", TYPE="transcription",
                                      LABEL="not transcribed",
                                      DESCRIPTION="Line geometry only; label too faint/illegible to transcribe. "
                                                  "CONTENT is deliberately empty."))
            s = A(tl, "String", ID=f"{line.get('id')}_w001", CONTENT="")
            setbox(s, lb)
            # flags with zero length still become tags on the empty String
            refs = []
            for k, (name, kv) in enumerate(custom):
                if name in ("readingOrder", "hyphenEnd"):
                    continue
                refs.append(self.flag_tag(line, k, name, kv))
            if refs:
                s.set("TAGREFS", " ".join(refs))
            tl.set("TAGREFS", " ".join(dict.fromkeys(line_tags)))
            return

        line_tags.append(self.tag("geom_est", "OtherTag", TYPE="geometry", LABEL="estimated word boxes",
                                  DESCRIPTION="PAGE source is line-level; String HPOS/VPOS/WIDTH/HEIGHT were "
                                              "estimated by splitting the line box along the baseline in "
                                              "proportion to code-point counts. Do not use for word-level "
                                              "highlighting precision."))
        tl.set("TAGREFS", " ".join(dict.fromkeys(line_tags)))
        toks = tokens(text)
        ttoks = tess.split() if tess else []
        use_alt = bool(tess) and len(ttoks) == len(toks)
        if tess:
            self.stats["alt_lines" if use_alt else "alt_lines_dropped"] += 1

        # flag instances
        flags = []
        for k, (name, kv) in enumerate(custom):
            if name in ("readingOrder", "hyphenEnd"):
                continue
            off, ln = int(kv.get("offset", 0)), int(kv.get("length", 0))
            flags.append((off, off + ln, self.flag_tag(line, k, name, kv)))
        hyph_end = any(n == "hyphenEnd" for n, _ in custom)

        # geometry along the reading direction
        total = sum(len(t) for t, _, _ in toks) + (len(toks) - 1)
        x, y, w, h = lb
        span = h if rotated else w
        pos = 0.0
        for i, (tok, s0, s1) in enumerate(toks):
            frac0, frac1 = pos / total, (pos + len(tok)) / total
            if rotated:   # text runs bottom-to-top
                wy0 = y + h - frac1 * span
                wb = (x, round(wy0), w, max(1, round((frac1 - frac0) * span)))
            else:
                wb = (round(x + frac0 * span), y, max(1, round((frac1 - frac0) * span)), h)
            pos += len(tok) + 1
            s = A(tl, "String", ID=f"{line.get('id')}_w{i + 1:03d}", CONTENT=tok)
            setbox(s, wb)
            refs = [tid for a, b, tid in flags if (a < s1 and b > s0) or (a == b and s0 <= a <= s1)]
            if refs:
                s.set("TAGREFS", " ".join(refs))
            if i == len(toks) - 1 and hyph_end:
                nxt = self.next_line_first_token(line)
                s.set("SUBS_TYPE", "HypPart1")
                if nxt:
                    s.set("SUBS_CONTENT", tok + nxt.rstrip(STRIP_PUNCT))
            if i == 0:
                prv = self.prev_line_last_token(line)
                if prv:
                    s.set("SUBS_TYPE", "HypPart2")
                    s.set("SUBS_CONTENT", prv + tok.rstrip(STRIP_PUNCT))
            if use_alt and ttoks[i] != tok:
                A(s, "ALTERNATIVE", PURPOSE=PROV["alto_alternative"]).text = ttoks[i]
            self.stats["strings"] += 1
            if i < len(toks) - 1:
                sp = A(tl, "SP")
                gap0 = (pos - 1) / total
                if rotated:
                    sp.set("HPOS", str(x)); sp.set("VPOS", str(round(y + h - (gap0 + 1 / total) * span)))
                    sp.set("WIDTH", str(w)); sp.set("HEIGHT", str(max(1, round(span / total))))
                else:
                    sp.set("HPOS", str(round(x + gap0 * span))); sp.set("VPOS", str(y))
                    sp.set("WIDTH", str(max(1, round(span / total)))); sp.set("HEIGHT", str(h))

    def flag_tag(self, line, k, name, kv):
        off, ln = int(kv.get("offset", 0)), int(kv.get("length", 0))
        jtype = {"underlined": "underline", "inkOver": "ink-over"}.get(name, name)
        notes = [c for c in (line.get("comments") or "").split(" | ") if c.startswith(f"[{jtype} {off}-{off + ln}]")]
        desc = f"{name} on code points {off}-{off + ln} (end-exclusive) of TextLine {line.get('id')}"
        for key in ("hand", "cert", "graphic"):
            if key in kv:
                desc += f"; {key}={kv[key]}"
        if notes:
            desc += "; note: " + notes[0].split("] ", 1)[-1]
        self.stats["flag_tags"] += 1
        return self.tag(f"{line.get('id')}_t{k:02d}", "OtherTag", TYPE=name,
                        LABEL=f"{name}" + (f" ({kv['cert']})" if "cert" in kv else ""), DESCRIPTION=desc)

    # ---------- regions
    def region_tagrefs(self, r):
        refs = []
        local = etree.QName(r).localname
        if local == "TextRegion":
            t = r.get("type")
            struct = [kv.get("type") for n, kv in parse_custom(r.get("custom")) if n == "structure"]
            label = struct[0] if struct else t
            refs.append(self.tag(f"lt_{label}", "LayoutTag", TYPE="structure", LABEL=label,
                                 DESCRIPTION=f"PAGE TextRegion/@type={t}" + (f", custom structure {label}" if struct else "")))
            prod = r.get("production")
            if prod:
                refs.append(self.tag(f"prod_{prod}", "OtherTag", TYPE="production", LABEL=prod,
                                     DESCRIPTION=f"PAGE @production={prod}"))
        for n, kv in parse_custom(r.get("custom")):
            if n == "hand":
                refs.append(self.tag(f"hand_{kv['ink']}", "OtherTag", TYPE="hand", LABEL=kv["ink"],
                                     DESCRIPTION="ink colour of the reader's hand (automatic, indicative only)"))
        if r.get("comments"):
            refs.append(self.tag(f"{r.get('id')}_note", "OtherTag", TYPE="note", LABEL="note",
                                 DESCRIPTION=r.get("comments")))
        return refs

    def convert_region(self, parent, r):
        local = etree.QName(r).localname
        rid = r.get("id")
        pts = points(r)
        rot = float(r.get("orientation") or 0)
        refs = self.region_tagrefs(r)
        if local == "TextRegion":
            el = A(parent, "TextBlock", ID=rid)
        else:
            itype = {"ImageRegion": "map" if "map" in (r.get("comments") or "").lower() else "image",
                     "GraphicRegion": r.get("type") or "graphic",
                     "NoiseRegion": "damage"}[local]
            el = A(parent, "Illustration", ID=rid, TYPE=itype)
            if local == "NoiseRegion":
                refs.append(self.tag("noise", "OtherTag", TYPE="structure", LABEL="noise",
                                     DESCRIPTION="PAGE NoiseRegion (physical damage: crease/tear/stain); ALTO has "
                                                 "no noise element, carried as Illustration TYPE=damage"))
        setbox(el, box(pts))
        if rot:
            el.set("ROTATION", f"{rot:g}")
        if local == "TextRegion":
            if r.get("primaryLanguage") in LANG:
                el.set("LANG", LANG[r.get("primaryLanguage")])
            if r.find("pc:TextLine/pc:TextStyle[@textColour='blue']", N) is not None:
                el.set("STYLEREFS", "ts_blue")
        if refs:
            el.set("TAGREFS", " ".join(dict.fromkeys(refs)))
        shape(el, pts)
        if local == "TextRegion":
            for line in r.findall("pc:TextLine", N):
                self.convert_line(el, line, rotated=abs(rot - 90) < 1e-6, region_tagrefs=[])
        return el

    def convert(self, now):
        pg = self.page
        md = self.tree.find("pc:Metadata", N)
        canvas = md.find("pc:MetadataItem[@name='iiif-canvas']", N).get("value")
        pn = md.find("pc:MetadataItem[@name='printed-page-number']", N)
        printed = pn.get("value") if pn is not None else None
        root = etree.Element(f"{{{ALTO}}}alto", nsmap={None: ALTO, "xsi": XSI})
        root.set(f"{{{XSI}}}schemaLocation", ALTO + " http://www.loc.gov/standards/alto/v4/alto-4-4.xsd")
        root.set("SCHEMAVERSION", "4.4")
        desc = A(root, "Description")
        A(desc, "MeasurementUnit").text = "pixel"
        sii = A(desc, "sourceImageInformation")
        A(sii, "fileName").text = pg.get("imageFilename")
        A(sii, "fileIdentifier", fileIdentifierLocation="IIIF Presentation canvas").text = canvas
        p1 = A(desc, "Processing", ID="proc_ocr")
        A(p1, "processingCategory").text = "contentGeneration"
        A(p1, "processingStepDescription").text = PROV["alto_step"]
        sw = A(A(p1, "processingSoftware"), "softwareName")
        sw.text = PROV["alto_software"]
        p2 = A(desc, "Processing", ID="proc_conv")
        A(p2, "processingCategory").text = "other"
        A(p2, "processingDateTime").text = now
        A(p2, "processingStepDescription").text = (
            f"PAGE 2019-07-15 -> ALTO 4.4 from page/{self.pid}.page.xml; word boxes estimated (tag geom_est).")
        A(A(p2, "processingSoftware"), "softwareName").text = "page/page2alto.py (Gpura pipeline demo)"
        styles = A(root, "Styles")
        tags_el = A(root, "Tags")
        layout = A(root, "Layout")
        page = A(layout, "Page", ID=self.pid, PAGECLASS=pg.get("type"), PHYSICAL_IMG_NR=int(self.pid[1:]),
                 PRINTED_IMG_NR=printed, WIDTH=pg.get("imageWidth"), HEIGHT=pg.get("imageHeight"),
                 PROCESSINGREFS="proc_ocr proc_conv")
        ps = A(page, "PrintSpace", ID=f"{self.pid}_ps", HPOS=0, VPOS=0,
               WIDTH=pg.get("imageWidth"), HEIGHT=pg.get("imageHeight"))

        regions = [r for r in pg if isinstance(r.tag, str) and etree.QName(r).localname.endswith("Region")]
        by_id = {r.get("id"): r for r in regions}
        ro = [ref.get("regionRef") for ref in pg.findall("pc:ReadingOrder/pc:OrderedGroup/pc:RegionRefIndexed", N)]
        rest = [r.get("id") for r in regions if r.get("id") not in ro]
        image = next((r.get("id") for r in regions if etree.QName(r).localname == "ImageRegion"), None)
        map_members = set()
        if image:
            map_members.add(image)
            for rel in pg.findall("pc:Relations/pc:Relation", N):
                if rel.find("pc:TargetRegionRef", N).get("regionRef") == image:
                    map_members.add(rel.find("pc:SourceRegionRef", N).get("regionRef"))
            for r in regions:
                if "structure {type:map-label;}" in (r.get("custom") or ""):
                    map_members.add(r.get("id"))
        composed = None
        for rid in ro + rest:
            if rid in map_members:
                if composed is None:
                    composed = A(ps, "ComposedBlock", ID=f"{self.pid}_map", TYPE="map")
                    mb = box(points(by_id[image]))
                    setbox(composed, mb)  # extended below
                self.convert_region(composed, by_id[rid])
            else:
                self.convert_region(ps, by_id[rid])
        if composed is not None:
            xs = [float(c.get("HPOS")) for c in composed] + [float(c.get("HPOS")) + float(c.get("WIDTH")) for c in composed]
            ys = [float(c.get("VPOS")) for c in composed] + [float(c.get("VPOS")) + float(c.get("HEIGHT")) for c in composed]
            setbox(composed, (int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))))
            composed.set("ROTATION", "90")
            composed.set("TAGREFS", self.tag("map_group", "OtherTag", TYPE="structure", LABEL="map group",
                                             DESCRIPTION="map image with its caption, legend and printed labels"))
        # reading order -> IDNEXT chain (unordered groups: no ALTO equivalent)
        for a, b in zip(ro[:-1], ro[1:]):
            root.find(f".//*[@ID='{a}']").set("IDNEXT", b)
        # styles & tags
        A(styles, "TextStyle", ID="ts_blue", FONTCOLOR="0000FF")
        for kind in ("LayoutTag", "StructureTag", "OtherTag"):
            for tid, (k, attrs) in self.tags.items():
                if k == kind:
                    A(tags_el, kind, ID=tid, **attrs)
        if not root.findall(".//*[@STYLEREFS='ts_blue']"):
            styles.remove(styles[0])
        return etree.ElementTree(root)


def main():
    pids = sys.argv[1:] or page_ids()
    all_pages = {p.name.split(".")[0]: etree.parse(str(p)) for p in sorted((ROOT / "page").glob("p*.page.xml"))}
    now = stamp()
    for pid in pids:
        c = Converter(pid, all_pages)
        tree = c.convert(now)
        out = ROOT / "page" / f"{pid}.alto.xml"
        tree.write(str(out), xml_declaration=True, encoding="UTF-8", pretty_print=True)
        print("wrote", out, c.stats)


if __name__ == "__main__":
    main()
