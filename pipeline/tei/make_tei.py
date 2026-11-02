#!/usr/bin/env python3
"""Build tei/american-aikyanadu-p017-019.tei.xml from ocr/p0NN.lines.json.

The lines.json files are the contract: readings (`text`) and IDs are copied
verbatim; nothing here edits a reading.  Run from anywhere:

    python3 tei/make_tei.py
"""
import os
import json
import re
from pathlib import Path

from lxml import etree

ROOT = Path(os.environ["GPURA_ITEM_DIR"]) if os.environ.get("GPURA_ITEM_DIR") else Path(__file__).resolve().parent.parent
OUT = ROOT / "tei" / "american-aikyanadu-p017-019.tei.xml"
PAGES = ["p017", "p018", "p019"]

TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
NSMAP = {None: TEI}

CANVAS = "https://artifacts.gpura.org/public/1971-american-aikyanadinte-charithram/canvas/{n}"
IMAGE = "https://iiif.gpura.org/iiif/3/1971-american-aikyanadinte-charithram__{n:04d}.jpg/full/max/0/default.jpg"
ITEM = "https://gpura.org/item/1971-american-aikyanadinte-charithram"
MANIFEST = "https://gpura.org/iiif-presentation/3/item/38951/manifest"


# --------------------------------------------------------------------------- helpers
def E(tag, attrib=None, text=None, parent=None, **kw):
    attrib = dict(attrib or {}, **kw)
    a = {}
    for k, v in attrib.items():
        if v is None:
            continue
        if k == "id":
            k = f"{{{XML}}}id"
        elif k == "lang":
            k = f"{{{XML}}}lang"
        a[k] = str(v)
    el = etree.SubElement(parent, f"{{{TEI}}}{tag}", a) if parent is not None else etree.Element(f"{{{TEI}}}{tag}", a, nsmap=NSMAP)
    if text is not None:
        el.text = text
    return el


def add_text(parent, s):
    """Append character data at the current end of `parent` (mixed content)."""
    if not s:
        return
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + s
    else:
        parent.text = (parent.text or "") + s


def pts(poly):
    return " ".join(f"{x},{y}" for x, y in poly)


def rect(b):
    x, y, w, h = b
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


# --------------------------------------------------------------------------- load
data = {p: json.loads((ROOT / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8")) for p in PAGES}
REG = {}   # region id -> region
LINE = {}  # line id -> (line, region, page)
for p in PAGES:
    for r in data[p]["regions"]:
        REG[r["id"]] = r
        for l in r.get("lines", []):
            LINE[l["id"]] = (l, r, p)

back_notes = []   # (target id, note type, text)


# --------------------------------------------------------------------------- flag -> element
def unclear_reason(flag, line, region):
    n = flag.get("note", "").lower()
    reasons = []
    if region["production"] == "handwritten":
        reasons.append("handwriting")
    elif region["type"] == "map-label":
        reasons.append("small-print")
    elif "faint" in n:
        reasons.append("faint")
    elif "broken" in n:
        reasons.append("print-defect")
    elif any(w in n for w in ("stain", "torn", "tear", "lost")):
        reasons.append("damage")
    else:
        reasons.append("glyph-form")
    # an overlapping damage flag on the same line adds "damage"
    for g in line["flags"]:
        if g["type"] == "damage" and g["start"] < flag["end"] and flag["start"] < g["end"] and "damage" not in reasons:
            reasons.append("damage")
    return " ".join(reasons)


def damage_agent(note):
    n = note.lower()
    if "crease" in n:
        return "crease"
    if "torn" in n or "tear" in n:
        return "tear"
    if "stain" in n:
        return "stain"
    return None


def damage_zone(line, page):
    for r in data[page]["regions"]:
        if r["type"] == "damage" and intersects(r["bbox"], line["bbox"]):
            return r["id"]
    return None


def overdraw_zone(line, flag, page):
    """The reader stroke that runs through the flagged characters: an
    annotation-graphic region that intersects the flagged part of the line and
    is not one of this line's own underlines."""
    own = {m.group(0) for g in line["flags"] if g["type"] == "underline"
           for m in [re.search(r"p\d{3}_r\d{2}", g.get("note", ""))] if m}
    x, y, w, h = line["bbox"]
    L = max(len(line["text"]), 1)
    sx = x + w * flag["start"] / L
    ex = x + w * flag["end"] / L
    span_box = [sx, y, ex - sx, h]
    hits = [r["id"] for r in data[page]["regions"]
            if r["type"] == "annotation-graphic" and r["id"] not in own
            and r.get("hand") == flag.get("hand") and intersects(r["bbox"], span_box)]
    return hits[0] if len(hits) == 1 else None


PRIO = {"insert": -1, "underline": 0, "ink-over": 1, "unclear": 2, "damage": 3}


def make_flag_element(parent, item, line, region, page):
    f = item["flag"]
    t = f["type"]
    if t == "underline":
        m = re.search(r"p\d{3}_r\d{2}", f.get("note", ""))
        return E("hi", parent=parent, rend="underline", hand=f"#{f['hand']}",
                 facs=f"#{m.group(0)}" if m else None, cert=f.get("cert"))
    if t == "ink-over":
        z = overdraw_zone(line, f, page)
        return E("hi", parent=parent, rend="overdrawn", hand=f"#{f['hand']}",
                 facs=f"#{z}" if z else None, cert=f.get("cert"))
    if t == "damage":
        z = damage_zone(line, page)
        return E("damage", parent=parent, agent=damage_agent(f.get("note", "")),
                 facs=f"#{z}" if z else None, cert=f.get("cert"))
    if t == "unclear":
        return E("unclear", parent=parent, reason=unclear_reason(f, line, region), cert=f.get("cert"))
    raise ValueError(t)


def emit(parent, text, lo, hi, items, line, region, page):
    """Nest flag spans; a span that overlaps the end of an enclosing span is
    split into fragments (linked later with @next/@prev)."""
    key = lambda it: (it["s"], 0 if it["s"] == it["e"] else 1, -it["e"], PRIO[it["flag"]["type"]])
    pool = sorted(items, key=key)
    pos = lo
    while pool:
        f = pool.pop(0)
        add_text(parent, text[pos:f["s"]])
        if f["s"] == f["e"]:            # point insertion (reader's <add>)
            f["build"](parent)
            pos = f["s"]
            continue
        children, rest = [], []
        for g in pool:
            point = g["s"] == g["e"]
            inside = (f["s"] < g["s"] < f["e"]) if point else (g["s"] < f["e"])
            if not inside:
                rest.append(g)
            elif point or g["e"] <= f["e"]:
                children.append(g)
            else:  # overlap: split
                a = dict(g, e=f["e"])
                b = dict(g, s=f["e"])
                g["frags"].remove(g["self"]) if g["self"] in g["frags"] else None
                for fr in (a, b):
                    fr["self"] = object()
                    g["frags"].append(fr["self"])
                children.append(a)
                rest.append(b)
        el = make_flag_element(parent, f, line, region, page)
        f["frag_el"][f["self"]] = (f["s"], el)
        emit(el, text, f["s"], f["e"], children, line, region, page)
        pos = f["e"]
        pool = sorted(rest, key=key)
    add_text(parent, text[pos:hi])


def line_content(parent, line, region, page, insertions=()):
    text = line["text"]
    items, registry = [], []
    for k, f in enumerate(line["flags"], 1):
        s, e = max(0, f["start"]), min(len(text), f["end"])
        if s >= e:
            continue  # zero-length flags (untranscribed labels) are handled by the caller
        tok = object()
        rec = {"k": k, "frags": [tok], "frag_el": {}}
        registry.append(rec)
        items.append({"s": s, "e": e, "flag": f, "self": tok, "frags": rec["frags"], "frag_el": rec["frag_el"]})
    for off, build in insertions:
        items.append({"s": off, "e": off, "flag": {"type": "insert"}, "build": build, "self": None,
                      "frags": [], "frag_el": {}})
    emit(parent, text, 0, len(text), items, line, region, page)
    # ids, fragment links, notes
    for rec in registry:
        frs = sorted(rec["frag_el"].values(), key=lambda t: t[0])
        base = f"f-{line['id']}-{rec['k']}"
        ids = [base] if len(frs) == 1 else [f"{base}-{chr(97 + i)}" for i in range(len(frs))]
        for i, (_, el) in enumerate(frs):
            el.set(f"{{{XML}}}id", ids[i])
            if len(frs) > 1:
                if i:
                    el.set("prev", f"#{ids[i - 1]}")
                if i < len(frs) - 1:
                    el.set("next", f"#{ids[i + 1]}")
        f = line["flags"][rec["k"] - 1]
        if f["type"] in ("unclear", "damage", "ink-over") and f.get("note"):
            back_notes.append((ids[0], f"ocr-{f['type']}", f["note"]))


# --------------------------------------------------------------------------- body writer
class Flow:
    """Writes printed lines into containers, tracking the previous hyphen_end."""

    def __init__(self):
        self.prev_hyphen = False

    def line(self, parent, lid, indent="\n        ", insertions=()):
        l, r, p = LINE[lid]
        if self.prev_hyphen:
            E("lb", parent=parent, facs=f"#{lid}", **{"break": "no"})
        else:
            add_text(parent, indent)
            E("lb", parent=parent, facs=f"#{lid}")
        line_content(parent, l, r, p, insertions)
        self.prev_hyphen = l["hyphen_end"]

    def pb(self, parent, page, indent="\n        "):
        n = data[page]["printed_page"]
        if self.prev_hyphen:
            E("pb", parent=parent, n=n, facs=f"#{page}", **{"break": "no"})
        else:
            add_text(parent, indent)
            E("pb", parent=parent, n=n, facs=f"#{page}")

    def fw(self, parent, rid, fwtype, place, indent="\n        "):
        r = REG[rid]
        if not self.prev_hyphen:
            add_text(parent, indent)
        fw = E("fw", parent=parent, type=fwtype, place=place, facs=f"#{rid}")
        for l in r["lines"]:
            E("lb", parent=fw, facs=f"#{l['id']}")
            line_content(fw, l, r, LINE[l["id"]][2])
        return fw


def para(parent, region_ids, flow, before=None):
    p = E("p", parent=parent, facs=" ".join(f"#{r}" for r in region_ids))
    flow.prev_hyphen = False
    return p


def handwritten_note(parent, rid, place, indent):
    r = REG[rid]
    add_text(parent, indent)
    n = E("note", parent=parent, type="annotation", hand=f"#{r['hand']}", place=place, facs=f"#{rid}", lang="en")
    for l in r["lines"]:
        line_content(n, l, r, LINE[l["id"]][2])
    return n


# --------------------------------------------------------------------------- header
def header(tei):
    h = E("teiHeader", parent=tei, lang="en")
    fd = E("fileDesc", parent=h)
    ts = E("titleStmt", parent=fd)
    E("title", parent=ts, type="main", lang="ml", text="അമേരിക്കൻ ഐക്യനാടിന്റെ ചരിത്രം")
    E("title", parent=ts, type="sub", text="Extract: printed pages 1–3 (Gpura viewer pages 17–19): a demonstration TEI encoding")
    au = E("author", parent=ts)
    E("persName", parent=au, lang="en", text="C.P. Hill")
    E("persName", parent=au, lang="ml", text="സി.പി. ഹിൽ")
    rs = E("respStmt", parent=ts)
    E("resp", parent=rs, text="translated into Malayalam by")
    E("persName", parent=rs, lang="en", text="Kuttanad K. Ramakrishna Pillai")
    E("persName", parent=rs, lang="ml", text="കുട്ടനാട് കെ. രാമകൃഷ്ണപിള്ള")
    rs = E("respStmt", parent=ts, id="pipeline")
    E("resp", parent=rs, text="OCR (Tesseract 5.3.4), model-made reading review (Claude, Anthropic) and TEI encoding, as an automated digitisation-pipeline demonstration; not human-verified")
    E("name", parent=rs, text="Gpura digitisation pipeline demo")

    ex = E("extent", parent=fd)
    E("measure", parent=ex, unit="pages", quantity="3", text="3 printed pages (pp. 1–3 of 420)")

    ps = E("publicationStmt", parent=fd)
    E("authority", parent=ps, text="Unpublished demonstration encoding produced by a digitisation pipeline demo. This is not a Gpura publication and has not been reviewed or released by Gpura or by Kottayam Public Library.")
    av = E("availability", parent=ps)
    E("p", parent=av, text="The source volume is in the public domain according to its Gpura item record. No separate licence has been assigned to this demonstration encoding.")
    E("date", parent=ps, when="2026-11-02", text="2026-11-02")

    ns = E("notesStmt", parent=fd)
    E("note", parent=ns, type="extent", text="This file encodes an extract only: the opening of the chapter ഭൂപ്രകൃതി, printed pages 1–3 (viewer pages 17–19), ending after the map on p. 3. The text continues on p. 4, which is not encoded.")

    sd = E("sourceDesc", parent=fd)
    bs = E("biblStruct", parent=sd)
    mo = E("monogr", parent=bs)
    au = E("author", parent=mo)
    E("persName", parent=au, lang="en", text="C.P. Hill")
    E("persName", parent=au, lang="ml", text="സി.പി. ഹിൽ")
    E("title", parent=mo, level="m", lang="ml", text="അമേരിക്കൻ ഐക്യനാടിന്റെ ചരിത്രം")
    rs = E("respStmt", parent=mo)
    E("resp", parent=rs, text="translator")
    E("persName", parent=rs, lang="en", text="Kuttanad K. Ramakrishna Pillai")
    E("persName", parent=rs, lang="ml", text="കുട്ടനാട് കെ. രാമകൃഷ്ണപിള്ള")
    rs = E("respStmt", parent=mo)
    E("resp", parent=rs, text="printer")
    E("orgName", parent=rs, text="Balan Press, Trivandrum")
    im = E("imprint", parent=mo)
    pp = E("pubPlace", parent=im)
    E("placeName", parent=pp, lang="en", text="Trivandrum")
    E("placeName", parent=pp, lang="ml", text="തിരുവനന്തപുരം")
    pu = E("publisher", parent=im)
    E("orgName", parent=pu, lang="en", text="State Institute of Languages")
    E("orgName", parent=pu, lang="ml", text="കേരള ഭാഷാ ഇൻസ്റ്റിറ്റ്യൂട്ട്")
    E("date", parent=im, when="1971", text="1971")
    ex = E("extent", parent=mo)
    E("measure", parent=ex, unit="pages", quantity="420", text="420 pages")

    md = E("msDesc", parent=sd, id="copy")
    mi = E("msIdentifier", parent=md)
    E("settlement", parent=mi, text="Kottayam")
    E("repository", parent=mi, text="Kottayam Public Library")
    ai = E("altIdentifier", parent=mi, type="digital")
    E("repository", parent=ai, text="Gpura (Granthappura)")
    E("idno", parent=ai, type="URI", text=ITEM)
    ai = E("altIdentifier", parent=mi, type="iiif-manifest")
    E("idno", parent=ai, type="URI", text=MANIFEST)
    ph = E("physDesc", parent=md)
    od = E("objectDesc", parent=ph, form="codex")
    su = E("supportDesc", parent=od)
    ex = E("extent", parent=su)
    add_text(ex, "420 pages; ")
    dm = E("dimensions", parent=ex, unit="cm", type="leaf")
    E("height", parent=dm, quantity="20.5", text="20.5")
    E("width", parent=dm, quantity="15", text="15")
    add_text(ex, " (20.5 × 15 cm)")
    co = E("condition", parent=su)
    E("p", parent=co, text="In the encoded pages: a crease or tear along the lower left margin of p. 1; brown staining along the upper right edge and a torn, stained lower right margin on p. 2, which partly obscure some line-final characters; show-through from the other side of the leaf on p. 3. Damage areas are recorded as facsimile zones of type 'damage'.")
    hd = E("handDesc", parent=ph)
    E("summary", parent=hd, text="Later reader annotations in two inks. Ink colour was classified automatically from pixel colour and then checked by eye, so the two hands are distinguished by ink only. Whether the annotations are by one reader or by several is unknown.")
    hn = E("handNote", parent=hd, id="blue-ink", medium="blue-ink", scope="minor")
    E("p", parent=hn, text="Blue or violet ballpoint: most of the underlining on pp. 1–2; the letters 'CMS' beside the chapter title and a circled numeral '1' on p. 1; the notes 'Trueman Doctrine' and 'Kennedy.' across the top of p. 3; and a tracing of the Gulf and Atlantic coastline on the map. Attribution to one or more readers is unknown.")
    hn = E("handNote", parent=hd, id="dark-ink", medium="dark-ink", scope="minor")
    E("p", parent=hn, text="Dark (brown or black) ink, possibly pencil in places: some underlining on p. 1, a thin arc over the starts of the last three lines of p. 2, and stray strokes. Attribution to one or more readers, and its relation to the blue-ink hand, is unknown.")
    ad = E("additional", parent=md)
    sg = E("surrogates", parent=ad)
    p = E("p", parent=sg)
    add_text(p, "Digitized on ")
    E("date", parent=p, when="2026-10-22", text="2026-10-22")
    add_text(p, " at the Kottayam Public Library Centre. Gpura item: ")
    E("ref", parent=p, target=ITEM, text=ITEM)
    add_text(p, "; IIIF manifest: ")
    E("ref", parent=p, target=MANIFEST, text=MANIFEST)
    add_text(p, ". Page images and canvases for pages 17–19 are referenced from <facsimile>.")

    # encodingDesc
    ed = E("encodingDesc", parent=h)
    pd = E("projectDesc", parent=ed)
    E("p", parent=pd, text="A demonstration of a digitisation pipeline for the Gpura (Granthappura) archive: page images go through OCR and a model-made reading review, and are then encoded both as PAGE-XML (a separate stage) and as this TEI P5 file. The two encodings share region and line identifiers (for example p018_r03_l001), which are used here as the xml:id values of facsimile zones.")
    E("p", parent=pd, text="Generated by tei/make_tei.py from ocr/p017.lines.json, ocr/p018.lines.json and ocr/p019.lines.json. Those files are the source of every reading, coordinate and identifier in this file.")
    sm = E("samplingDecl", parent=ed)
    E("p", parent=sm, text="Only viewer pages 17–19 (printed pages 1–3) are encoded. On p. 3, only the clearly legible map labels are transcribed. Other labels are present as zones and as <label> elements containing <gap/>. Many small labels (states, rivers) were not inventoried at all. Show-through and soiling are not recorded.")
    edl = E("editorialDecl", parent=ed)
    c = E("correction", parent=edl, status="unknown")
    E("p", parent=c, text="Readings are model-made: Tesseract 5.3.4 OCR, followed by a reading by Claude from zoomed line images, with the archive's existing OCR open for comparison. No human has verified them. Nothing has been corrected. Points of doubt are marked with <unclear> and @cert, and the review notes are kept in the <back>.")
    nz = E("normalization", parent=edl, method="markup")
    E("p", parent=nz, text="Diplomatic transcription: wording, spelling, abbreviations (e.g. യു. എസ്. ഏ.) and spacing around punctuation follow the print, and nothing is modernised (e.g. ബ്രിട്ടന്റെതിനോടു്, ജർമൻകാർ, ആസ്ത്രേലിയ).")
    E("p", parent=nz, text="Character encoding, not spelling: this 1971 print uses the reformed-script glyphs for NTA (drawn as ൻ+റ) and TTA (drawn as റ+റ). They are encoded as the standard sequences ന്റ (U+0D28 U+0D4D U+0D31) and റ്റ (U+0D31 U+0D4D U+0D31). These are glyph-shape conventions, not spelling differences. Standalone chillus are atomic (U+0D7A–U+0D7E). The dot-reph form of ർ printed before a consonant is also encoded as atomic ർ (U+0D7C), not U+0D4E. Visible-virama shapes inside words are encoded as ordinary conjuncts.")
    E("p", parent=nz, text="Samvruthokaram: the word-final u-sign plus chandrakkala is encoded as printed with U+0D41 U+0D4D (e.g. ഉണ്ടു്). A chandrakkala on a bare consonant is plain U+0D4D (e.g. എസ്). No samvruthokaram has been added or removed; words printed without it (e.g. കൊണ്ടു, നിന്നു) stay as printed. Ditto marks in the map legend are transcribed as two commas (,,).")
    hy = E("hyphenation", parent=edl, eol="none")
    E("p", parent=hy, text="The print breaks words at line end without a hyphen. Each printed line begins with <lb facs='#lineID'/>. A line that continues a word from the previous line has <lb break='no'/>, with no whitespace before it. The word split across pp. 1–2 (പതി|പ്പിച്ചിട്ടുണ്ടു്) uses <pb break='no'/> followed by the running head and page number (<fw>) and then <lb break='no'/>. Whitespace before an <lb/> without @break is a word boundary.")
    sg = E("segmentation", parent=edl)
    E("p", parent=sg, text="Each region in the OCR inventory has a <zone> with the same xml:id, and each line has a <zone> nested inside its region's zone. Text elements point to the zones with @facs: <p>, <head>, <fw>, <figure>, <list>, <label> and handwritten <note>/<add> point to regions, and <lb> to lines. Handwritten regions have one line each. Their line zones are nested in the region zone, and the region is what the text element points to. A paragraph that runs across a page break points to both of its regions.")
    it = E("interpretation", parent=edl)
    E("p", parent=it, text="Reader marks: underlines are <hi rend='underline' hand='#blue-ink|#dark-ink'>, and @facs points to the annotation-graphic zone of the stroke. Strokes drawn through printed characters are <hi rend='overdrawn'>; where geometry identifies the stroke, @facs points to it. Underline extents were mapped from stroke x-extent onto the text and snapped to word boundaries, so they are approximate (about ±1 word). Where two such spans overlap, the later span is split at the boundary into fragments linked by @next/@prev. Damage to the paper is <damage>, with @agent where the review note says (crease, tear, stain) and @facs to the damage zone. Uncertain readings are <unclear @reason @cert>. The reason vocabulary: faint, damage, print-defect (broken type), glyph-form (ambiguous print form or encoding decision), small-print (map labels), handwriting.")
    E("p", parent=it, text="Free-standing handwritten notes are <note type='annotation' hand=... place=...>. The circled numeral inserted between words on p. 1 is <add hand='#blue-ink' place='inline' rend='circled'>, placed directly after ഒന്നാമതു്. Removing it restores the printed text exactly. Non-textual reader marks (stray strokes, the arc on p. 2, marks in the corner of p. 3) are recorded as zones and described by notes in the <back>. The coastline tracing on the map is a nested <figure type='reader-mark'>.")
    E("p", parent=it, text="Zones on p. 3 that are printed rotated have @rotate='270'. TEI's @rotate gives the clockwise rotation of the zone relative to the surface. The OCR inventory's orientation 90 (PAGE-XML semantics: rotate 90° clockwise to read upright) therefore corresponds to TEI rotate 270, i.e. text printed rotated 90° anticlockwise and running bottom-to-top.")
    td = E("tagsDecl", parent=ed)
    E("rendition", parent=td, id="underline", scheme="css", text="text-decoration: underline;")
    E("rendition", parent=td, id="overdrawn", scheme="free", text="A reader's pen stroke runs through the printed characters (usually an underline of the line above); the text remains legible.")
    E("rendition", parent=td, id="circled", scheme="free", text="Handwritten character enclosed in a circle.")
    E("rendition", parent=td, id="rot-ccw90", scheme="css", text="transform: rotate(-90deg); /* printed rotated 90° anticlockwise; read by turning the page 90° clockwise */")
    nsd = E("namespace", parent=td, name=TEI)
    tu = E("tagUsage", parent=nsd, gi="hi")
    add_text(tu, "@rend values: 'underline' (= #underline), 'overdrawn' (= #overdrawn). @hand always points to a handNote.")
    tu = E("tagUsage", parent=nsd, gi="add")
    add_text(tu, "@rend 'circled' (= #circled).")
    ai = E("appInfo", parent=ed)
    ap = E("application", parent=ai, ident="tesseract", version="5.3.4")
    E("label", parent=ap, text="Tesseract OCR (tessdata_best; raw output kept in ocr/, not used for this edition)")
    ap = E("application", parent=ai, ident="make_tei", version="1.0")
    E("label", parent=ap, text="tei/make_tei.py")

    pr = E("profileDesc", parent=h)
    lu = E("langUsage", parent=pr)
    E("language", parent=lu, ident="ml", usage="98", text="Malayalam, in Malayalam script (1971 reformed orthography)")
    E("language", parent=lu, ident="en", usage="2", text="English: the reader's handwritten notes, and the editorial metadata, descriptions and notes")

    rd = E("revisionDesc", parent=h)
    E("change", parent=rd, when="2026-11-02", who="#pipeline", text="First demonstration encoding, generated by tei/make_tei.py from the reviewed OCR inventories for pages 17–19.")


# --------------------------------------------------------------------------- facsimile
def facsimile(tei):
    fac = E("facsimile", parent=tei)
    for p in PAGES:
        d = data[p]
        s = E("surface", parent=fac, id=p, n=str(d["canvas"]), ulx=0, uly=0, lrx=d["width"], lry=d["height"],
              corresp=CANVAS.format(n=d["canvas"]))
        E("graphic", parent=s, url=IMAGE.format(n=d["canvas"]), width=f"{d['width']}px", height=f"{d['height']}px",
          mimeType="image/jpeg")
        for r in d["regions"]:
            rot = "270" if r.get("orientation") == 90 else None
            x, y, w, h = r["bbox"]
            z = E("zone", parent=s, id=r["id"], type=r["type"], subtype=r["production"],
                  ulx=x, uly=y, lrx=x + w, lry=y + h, points=pts(r.get("polygon") or rect(r["bbox"])), rotate=rot)
            for l in r.get("lines", []):
                x, y, w, h = l["bbox"]
                lz = E("zone", parent=z, id=l["id"], type="line", ulx=x, uly=y, lrx=x + w, lry=y + h,
                       points=pts(l.get("polygon") or rect(l["bbox"])), rotate=rot)
                if l.get("baseline"):
                    E("path", parent=lz, type="baseline", points=pts(l["baseline"]))


# --------------------------------------------------------------------------- body
def body(text):
    b = E("body", parent=text)
    flow = Flow()
    I1, I2, I3 = "\n      ", "\n        ", "\n          "

    # ---- p. 1 (p017)
    flow.pb(b, "p017", I1)
    flow.fw(b, "p017_r01", "pageNum", "top-right", I1)
    add_text(b, I1)
    ch = E("div", parent=b, type="chapter")
    add_text(ch, I2)
    hd = E("head", parent=ch, facs="#p017_r02")
    for l in REG["p017_r02"]["lines"]:
        E("lb", parent=hd, facs=f"#{l['id']}")
        line_content(hd, l, REG["p017_r02"], "p017")
    handwritten_note(ch, "p017_r05", "right", I2)

    add_text(ch, I2)
    p = para(ch, ["p017_r03"], flow)
    for l in REG["p017_r03"]["lines"]:
        flow.line(p, l["id"], I3)
    add_text(p, I2)

    add_text(ch, I2)
    p = para(ch, ["p017_r04", "p018_r03"], flow)

    def circled_one(parent):
        r = REG["p017_r06"]
        a = E("add", parent=parent, hand="#blue-ink", place="inline", rend="circled", facs="#p017_r06")
        l = r["lines"][0]
        line_content(a, l, r, "p017")

    for l in REG["p017_r04"]["lines"]:
        ins = ()
        if l["id"] == "p017_r04_l005":
            off = l["text"].index("ഒന്നാമതു്") + len("ഒന്നാമതു്")
            ins = [(off, circled_one)]
        flow.line(p, l["id"], I3, ins)
    # ---- p. 2 (p018): word split across the page break
    flow.pb(p, "p018", I3)
    flow.fw(p, "p018_r01", "pageNum", "top-left", I3)
    flow.fw(p, "p018_r02", "header", "top-centre", I3)
    for l in REG["p018_r03"]["lines"]:
        flow.line(p, l["id"], I3)
    add_text(p, I2)

    add_text(ch, I2)
    p = para(ch, ["p018_r04"], flow)
    for l in REG["p018_r04"]["lines"]:
        flow.line(p, l["id"], I3)
    add_text(p, I2)

    add_text(ch, I2)
    sec = E("div", parent=ch, type="section", n="1")
    add_text(sec, I3)
    hd = E("head", parent=sec, facs="#p018_r05")
    flow.prev_hyphen = False
    for i, l in enumerate(REG["p018_r05"]["lines"]):
        flow.line(hd, l["id"], "" if i == 0 else I3)
    add_text(sec, I3)
    p = para(sec, ["p018_r06"], flow)
    for l in REG["p018_r06"]["lines"]:
        flow.line(p, l["id"], I3 + "  ")
    add_text(p, I3)

    # ---- p. 3 (p019): map page
    flow.prev_hyphen = False
    flow.pb(sec, "p019", I3)
    flow.fw(sec, "p019_r01", "header", "top-centre", I3)
    flow.fw(sec, "p019_r02", "pageNum", "top-right", I3)
    handwritten_note(sec, "p019_r14", "top", I3)
    handwritten_note(sec, "p019_r15", "top", I3)

    add_text(sec, I3)
    fig = E("figure", parent=sec, type="map", facs="#p019_r03", rendition="#rot-ccw90")
    I4 = I3 + "  "
    I5 = I4 + "  "
    add_text(fig, I4)
    cap = E("head", parent=fig, type="caption", facs="#p019_r04", rendition="#rot-ccw90")
    for l in REG["p019_r04"]["lines"]:
        E("lb", parent=cap, facs=f"#{l['id']}")
        line_content(cap, l, REG["p019_r04"], "p019")
    add_text(fig, I4)
    E("figDesc", parent=fig, lang="en",
      text="Relief map of the United States, printed rotated 90° on the page (north towards the left edge; read upright by turning the page 90° clockwise) inside a ruled frame. It shows elevation shading in three bands, rivers, state and regional boundaries, and place labels. The caption is printed outside the right edge of the frame.")
    add_text(fig, I4)
    lst = E("list", parent=fig, type="legend", facs="#p019_r05", rendition="#rot-ccw90")
    for l in REG["p019_r05"]["lines"]:
        add_text(lst, I5)
        it = E("item", parent=lst)
        E("lb", parent=it, facs=f"#{l['id']}")
        line_content(it, l, REG["p019_r05"], "p019")
    add_text(lst, I4)
    for r in data["p019"]["regions"]:
        if r["type"] != "map-label":
            continue
        add_text(fig, I4)
        lab = E("label", parent=fig, type="map-label", facs=f"#{r['id']}", rendition="#rot-ccw90")
        for l in r["lines"]:
            E("lb", parent=lab, facs=f"#{l['id']}")
            if l["text"]:
                line_content(lab, l, r, "p019")
            else:
                gid = f"gap-{l['id']}"
                E("gap", parent=lab, id=gid, reason="illegible")
                note = next((f["note"] for f in l["flags"] if f["type"] == "unclear"), r.get("note"))
                if note:
                    back_notes.append((gid, "ocr-untranscribed", "Not transcribed. Tentative identification from the OCR review, not a reading: " + note))
    add_text(fig, I4)
    rm = E("figure", parent=fig, type="reader-mark", facs="#p019_r16", corresp="#blue-ink")
    E("figDesc", parent=rm, lang="en", text="Reader's blue-ink tracing along the map's Gulf and Atlantic coastline (hand: blue-ink).")
    add_text(fig, I3)
    add_text(sec, I2)
    add_text(ch, I1)
    add_text(b, "\n    ")
    return b


def back(text):
    bk = E("back", parent=text, lang="en")
    add_text(bk, "\n      ")
    dv = E("div", parent=bk, type="transcription-notes")
    add_text(dv, "\n        ")
    E("head", parent=dv, text="Notes from the OCR review stage (copied from ocr/p0NN.lines.json)")
    for tgt, typ, txt in back_notes:
        add_text(dv, "\n        ")
        E("note", parent=dv, type=typ, target=f"#{tgt}", text=txt)
    marks = [rid for rid in ("p017_r07", "p018_r08", "p019_r17")]
    add_text(dv, "\n        ")
    E("head", parent=dv, type="sub", text="Non-textual reader marks (described, not transcribed)")
    for rid in marks:
        r = REG[rid]
        add_text(dv, "\n        ")
        E("note", parent=dv, type="reader-mark", target=f"#{rid}", corresp=f"#{r['hand']}",
          text=f"{r['note'][0].upper()}{r['note'][1:]} (hand: {r['hand']}).")
    add_text(dv, "\n      ")
    add_text(bk, "\n    ")


def main():
    tei = E("TEI", lang="ml")
    header(tei)
    facsimile(tei)
    text = E("text", parent=tei)
    body(text)
    back(text)
    # pretty-print the element-only parts (header, facsimile); mixed content keeps its own whitespace
    for part in (tei.find(f"{{{TEI}}}teiHeader"), tei.find(f"{{{TEI}}}facsimile")):
        etree.indent(part, space="  ", level=1)
    tei.text = "\n  "
    for el in tei:
        el.tail = "\n  "
    tei[-1].tail = "\n"
    text.text = "\n    "
    text[0].tail = "\n    "
    text[-1].tail = "\n  "
    doc = etree.ElementTree(tei)
    pi = etree.ProcessingInstruction(
        "xml-model", 'href="../../../schemas/tei/tei_all.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"')
    tei.addprevious(pi)
    OUT.write_bytes(etree.tostring(doc, xml_declaration=True, encoding="UTF-8") + b"\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
