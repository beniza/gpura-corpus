#!/usr/bin/env python3
"""Dictionary pages, step 3: entries + labelled segments -> TEI dictionary encoding, checked and validated.

    GPURA_ITEM_DIR=items/<item> python3 pipeline/dict/make_dict_tei.py p300 [--model "Claude Sonnet 5.5"]

Inputs: dict/<page>.entries.json (step 1: entries from the layout, with their lines) and
dict/<page>.segments.json (step 2: each entry's text labelled as orth, pron, etym, pos, sense, gloss,
example, source, usg, xr_see, xr_syn, subentry, note, furniture; by an AI model or by hand).

Guard: every segment must be an exact, in-order substring of its entry's text (whitespace aside), and the
segments must cover the entry.  An entry that fails is encoded as <entryFree> with its text unlabelled,
so a labelling error can never change or add text.  Every printed line is an <lb facs="#line-id"/>.

Output: tei/<item>.dict.tei.xml (TEI P5 dictionaries module), validated against tei_all, and
dict/<page>.report.json (per-entry check results and segment counts).
"""
import argparse
import json
import re
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ITEM, REPO, canvas_url, item_dir, stamp  # noqa: E402

ROOT = item_dir()
TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"


def E(tag, parent=None, text=None, **attrs):
    a = {({"id": f"{{{XML}}}id", "lang": f"{{{XML}}}lang"}.get(k, k)): str(v) for k, v in attrs.items() if v is not None}
    el = etree.SubElement(parent, f"{{{TEI}}}{tag}", a) if parent is not None else etree.Element(f"{{{TEI}}}{tag}", a, nsmap={None: TEI})
    if text:
        el.text = text
    return el


def locate(entry, segs):
    """Map segments to character spans of the entry text, whitespace-insensitive.  Returns (spans, ok, cover)."""
    text = entry["text"]
    chars = [(i, c) for i, c in enumerate(text) if not c.isspace()]   # non-space chars with their positions
    flat = "".join(c for _, c in chars)
    pos, spans = 0, []
    for s in segs:
        t = re.sub(r"\s+", "", s["text"])
        if not t:
            continue
        k = flat.find(t, pos)
        if k < 0:
            return spans, False, 0.0
        spans.append((s, chars[k][0], chars[k + len(t) - 1][0] + 1))
        pos = k + len(t)
    covered = sum(len(re.sub(r"\s+", "", s["text"])) for s, _, _ in spans)
    return spans, True, covered / max(1, len(flat))


def line_starts(entry):
    starts, p = [], 0
    for l in entry["lines"]:
        starts.append(p)
        p += len(l["text"]) + 1                      # joined with "\n"
    return starts


class Writer:
    """Appends text to the current element, inserting <lb facs/> where a printed line begins."""

    def __init__(self, entry):
        self.text, self.lines, self.starts, self.next = entry["text"], entry["lines"], line_starts(entry), 0

    def put(self, el, a, b):
        while a < b:
            if self.next < len(self.starts) and self.starts[self.next] <= a:
                lb = E("lb", el, facs="#" + self.lines[self.next]["id"])
                lb.tail = ""
                self.next += 1
                continue
            stop = min(b, self.starts[self.next]) if self.next < len(self.starts) else b
            chunk = self.text[a:stop].replace("\n", " ")
            if len(el):
                el[-1].tail = (el[-1].tail or "") + chunk
            else:
                el.text = (el.text or "") + chunk
            a = stop


def build_entry(parent, entry, rec, pid):
    eid = f"{pid}_e{entry['n']:02d}"
    w = Writer(entry)
    spans, ok, cover = locate(entry, rec.get("segments", []))
    if not ok or cover < 0.95:
        ef = E("entryFree", parent, id=eid, type="unlabelled")
        w.put(ef, 0, len(entry["text"]))
        return {"n": entry["n"], "ok": False, "reason": "segment not found in text" if not ok else f"covers {cover:.0%}"}
    if rec.get("kind") == "continuation":
        ent = E("entry", parent, id=eid, type="continued", prev="#" + pid + "_cont")
    else:
        ent = E("entry", parent, id=eid)
    form = sense = cit = cur_re = None
    last = 0
    counts = {}
    host = lambda: cur_re if cur_re is not None else ent

    def sense_el():
        nonlocal sense
        if sense is None:
            sense = E("sense", host())
        return sense

    for s, a, b in spans:
        typ = s["type"]
        counts[typ] = counts.get(typ, 0) + 1
        w.put(host() if typ not in ("gloss", "example", "source", "usg", "xr_see", "xr_syn", "note") or sense is None
              else sense, last, a)                    # whitespace and line breaks between segments
        if typ in ("orth", "pron") and cur_re is None and sense is None:
            form = form if form is not None else E("form", ent, type="lemma")
            el = E("orth" if typ == "orth" else "pron", form, **({"notation": "transliteration"} if typ == "pron" else {}))
        elif typ == "subentry":
            cur_re = E("entry", ent, type="derived")       # TEI P5 4.x: nested entry (re was removed)
            sense = cit = None
            el = E("orth", E("form", cur_re))
        elif typ == "etym":
            el = E("etym", host())
        elif typ == "pos":
            el = E("pos", E("gramGrp", sense if sense is not None else host()))
        elif typ == "sense":
            sense = E("sense", host(), n=re.sub(r"\D", "", s["text"]) or None)
            cit = None
            el = E("lbl", sense, type="senseNumber")
        elif typ == "gloss":
            el = E("def", sense_el(), lang="en")
            cit = None
        elif typ == "example":
            cit = E("cit", sense_el(), type="example")
            el = E("quote", cit, lang="ml")
        elif typ == "source":
            el = E("bibl", cit if cit is not None else sense_el())
            cit = None
        elif typ == "usg":
            el = E("usg", sense_el())
        elif typ in ("xr_see", "xr_syn"):
            el = E("xr", sense_el(), type="see" if typ == "xr_see" else "syn")
        elif typ == "furniture":
            el = E("fw", host())
        else:
            el = E("note", sense_el() if sense is not None else host())
        w.put(el, a, b)
        last = b
    w.put(host(), last, len(entry["text"]))
    return {"n": entry["n"], "ok": True, "cover": round(cover, 3), "segments": counts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--model", default="Claude Sonnet 5.5")
    a = ap.parse_args()
    pid = a.page
    ents = json.loads((ROOT / "dict" / f"{pid}.entries.json").read_text(encoding="utf-8"))
    segs = {r["n"]: r for r in json.loads((ROOT / "dict" / f"{pid}.segments.json").read_text(encoding="utf-8"))}
    lines = json.loads((ROOT / "ocr" / f"{pid}.lines.json").read_text(encoding="utf-8"))

    tei = E("TEI")
    tei.set(f"{{{XML}}}lang", "ml")
    h = E("teiHeader", tei)
    fd = E("fileDesc", h)
    ts = E("titleStmt", fd)
    E("title", ts, ITEM.get("title"), type="main")
    E("title", ts, f"Dictionary encoding of viewer page {lines['canvas']}: entries and their parts", type="sub")
    if ITEM.get("author"):
        E("author", ts, ITEM["author"])
    for rid, resp, name in (("pipeline", "layout, entry boundaries (hanging indent) and encoding", "Gpura corpus pipeline"),
                            ("sarvam", "page text", "Sarvam Vision 2.1 (Sarvam AI)"),
                            ("ai", "labelling of entry parts (headword, etymology, sense, gloss, example, source, cross-reference)", a.model)):
        rs = E("respStmt", ts, id=rid)
        E("resp", rs, resp)
        E("name", rs, name)
    ps = E("publicationStmt", fd)
    E("p", ps, "Unpublished encoding produced by the Gpura corpus pipeline; CC0 1.0. Not reviewed by a person.")
    sd = E("sourceDesc", fd)
    b = E("bibl", sd)
    E("title", b, ITEM.get("title_en") or ITEM.get("title"))
    if ITEM.get("author"):
        E("author", b, ITEM["author"])
    if ITEM.get("date"):
        E("date", b, ITEM["date"])
    E("ref", b, "Gpura item", target=ITEM["gpura_item"])
    ed = E("encodingDesc", h)
    E("p", E("editorialDecl", ed), "Entries are found from the layout (an entry's first line is flush with the column, the rest "
      "indented). Their parts are labelled by an AI model; every labelled part is checked to be an exact, in-order "
      "substring of the printed text, and an entry that fails the check is kept as unlabelled <entryFree>. Text is "
      "diplomatic. Each printed line is an <lb/> pointing to its zone; entries point to their lines.")
    E("change", E("revisionDesc", h), "Generated by pipeline/dict/make_dict_tei.py.", when=stamp()[:10], who="#pipeline")

    fx = E("facsimile", tei)
    s = E("surface", fx, id=pid, facs=canvas_url(lines["canvas"]), ulx=0, uly=0, lrx=lines["width"], lry=lines["height"])
    for r in lines["regions"]:
        for l in r["lines"]:
            x, y, w_, h_ = l["bbox"]
            E("zone", s, id=l["id"], type="line", points=f"{x},{y} {x+w_},{y} {x+w_},{y+h_} {x},{y+h_}")
    body = E("body", E("text", tei))
    div = E("div", body, type="dictionaryPage")
    E("pb", div, n=lines.get("printed_page"), facs="#" + pid)
    for f in ents["furniture"]:
        fw = E("fw", div, f["text"], type="header")
        fw.set("facs", "#" + f["id"])
    report, last_main = [], [None]
    for e in ents["entries"]:
        rec = segs.get(e["n"], {"kind": "entry", "segments": []})
        if rec.get("kind") == "furniture":
            fw = E("fw", div, type="header", facs=" ".join("#" + l["id"] for l in e["lines"]))
            Writer(e).put(fw, 0, len(e["text"]))
            report.append({"n": e["n"], "ok": True, "furniture": True})
            continue
        report.append(build_entry(div, e, rec, pid))
        el = div[-1]
        el.set("facs", " ".join("#" + l["id"] for l in e["lines"]))
        # Gundert-style layout rule: a main entry has a transliteration (pron); a headword without one is a
        # derived word of the main entry above it, and a fragment with no headword continues that entry
        has = {x["type"] for x in rec.get("segments", [])}
        main = last_main[0]
        if main is not None and el.tag == f"{{{TEI}}}entry":
            if rec.get("kind") == "continuation" or "orth" not in has:
                for c in list(el):
                    main.append(c)
                main.set("facs", main.get("facs") + " " + el.get("facs"))
                div.remove(el)
                report[-1]["merged_into"] = main.get(f"{{{XML}}}id")
                continue
            if "pron" not in has:
                el.set("type", "derived")
                main.append(el)
                report[-1]["nested_in"] = main.get(f"{{{XML}}}id")
                continue
        if el.tag == f"{{{TEI}}}entry":
            last_main[0] = el
    out = ROOT / "tei" / f"{ROOT.name}.dict.tei.xml"
    etree.ElementTree(tei).write(str(out), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    rng = etree.RelaxNG(etree.parse(str(REPO / "schemas" / "tei" / "tei_all.rng")))
    valid = rng.validate(etree.parse(str(out)))
    (ROOT / "dict" / f"{pid}.report.json").write_text(json.dumps({"valid": valid, "errors": [str(x) for x in rng.error_log][:20],
                                                                  "entries": report}, ensure_ascii=False, indent=1) + "\n",
                                                      encoding="utf-8", newline="\n")
    good = [r for r in report if r.get("ok") and not r.get("furniture")]
    bad = [r for r in report if not r.get("ok")]
    tot = {}
    for r in good:
        for k, v in r.get("segments", {}).items():
            tot[k] = tot.get(k, 0) + v
    print(f"  {pid}: {len(good)} entries labelled, {len(bad)} kept unlabelled {[(r['n'], r['reason']) for r in bad]}")
    print(f"  segments: {tot}")
    print(f"  {out.name}: tei_all {'VALID' if valid else 'INVALID'}")
    if not valid:
        for x in list(rng.error_log)[:8]:
            print("   ", x)


if __name__ == "__main__":
    main()
