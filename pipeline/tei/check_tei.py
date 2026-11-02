#!/usr/bin/env python3
"""Checks for an item's tei/*.tei.xml against its ocr/*.lines.json.

1. well-formedness (lxml parse)
2. RELAX NG validation against tei/schema/tei_all.rng (lxml)
3. every '#id' pointer (@facs @hand @target @next @prev @rendition @corresp @who @sameAs) resolves
4. contract: every region/line ID in ocr/p0NN.lines.json is a <zone> with the same
   coordinates, line zones nested in their region zone, and each region referenced
5. every printed line has exactly one <lb facs>; the text between that <lb> and the next one
   equals the lines.json `text` exactly (whitespace-normalised)
6. @break="no" on <lb>/<pb> iff the previous flow line has hyphen_end
7. every line flag is encoded, and its element(s) contain exactly text[start:end]

Exit status 1 if any check fails.  Usage: python3 tei/check_tei.py
"""
import os
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

ROOT = Path(os.environ["GPURA_ITEM_DIR"]) if os.environ.get("GPURA_ITEM_DIR") else Path(__file__).resolve().parent.parent
TEIF = Path(sys.argv[1]) if len(sys.argv) > 1 else next((ROOT / "tei").glob("*.tei.xml"))
RNG = Path(os.environ["GPURA_TEI_RNG"]) if os.environ.get("GPURA_TEI_RNG") else Path(__file__).resolve().parents[2] / "schemas" / "tei" / "tei_all.rng"
NS = {"t": "http://www.tei-c.org/ns/1.0"}
T = "{http://www.tei-c.org/ns/1.0}"
XID = "{http://www.w3.org/XML/1998/namespace}id"
POINTER_ATTRS = ["facs", "hand", "target", "next", "prev", "rendition", "corresp", "who", "sameAs"]

errors = []
def err(msg):
    errors.append(msg)

# 1 ---------------------------------------------------------------------------
doc = etree.parse(str(TEIF))          # raises on malformed XML
print("1 well-formed: ok")

# 2 ---------------------------------------------------------------------------
rng = etree.RelaxNG(etree.parse(str(RNG)))
if rng.validate(doc):
    print(f"2 RELAX NG ({RNG.name}, lxml): valid")
else:
    for e in rng.error_log:
        err(f"RNG line {e.line}: {e.message}")

# 3 ---------------------------------------------------------------------------
ids = {el.get(XID): el for el in doc.iter() if el.get(XID)}
dups = [k for k, v in Counter(el.get(XID) for el in doc.iter() if el.get(XID)).items() if v > 1]
for d in dups:
    err(f"duplicate xml:id {d}")
n_ptr, external = 0, set()
for el in doc.iter(tag=etree.Element):
    for a in POINTER_ATTRS:
        v = el.get(a)
        if not v:
            continue
        for tok in v.split():
            if tok.startswith("#"):
                n_ptr += 1
                if tok[1:] not in ids:
                    err(f"unresolved {a}={tok} on <{etree.QName(el).localname}> line {el.sourceline}")
            else:
                external.add(tok)
print(f"3 pointers: {n_ptr} '#' references checked; external URIs: {sorted(external)}")

# 4 ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import page_ids  # noqa: E402
data = {p: json.loads((ROOT / "ocr" / f"{p}.lines.json").read_text(encoding="utf-8")) for p in page_ids()}
def pts(poly):
    return " ".join(f"{x},{y}" for x, y in poly)
def rect(b):
    x, y, w, h = b
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

referenced = defaultdict(int)
for el in doc.iter(tag=etree.Element):
    for a in ("facs", "target"):
        for tok in (el.get(a) or "").split():
            if tok.startswith("#"):
                referenced[tok[1:]] += 1

LINES = {}
for p, d in data.items():
    surf = ids.get(p)
    if surf is None or surf.tag != T + "surface":
        err(f"no surface {p}")
    for r in d["regions"]:
        z = ids.get(r["id"])
        if z is None or z.tag != T + "zone":
            err(f"missing zone {r['id']}"); continue
        if z.getparent() is not surf:
            err(f"zone {r['id']} not on surface {p}")
        if z.get("type") != r["type"]:
            err(f"zone {r['id']} type {z.get('type')} != {r['type']}")
        if z.get("points") != pts(r.get("polygon") or rect(r["bbox"])):
            err(f"zone {r['id']} points differ")
        if (z.get("rotate") == "270") != (r.get("orientation") == 90):
            err(f"zone {r['id']} rotate mismatch")
        if not referenced[r["id"]]:
            err(f"region {r['id']} not referenced by any @facs/@target")
        for l in r.get("lines", []):
            LINES[l["id"]] = (l, r)
            lz = ids.get(l["id"])
            if lz is None or lz.getparent() is not z:
                err(f"line zone {l['id']} missing or not nested in {r['id']}")
            elif lz.get("points") != pts(l.get("polygon") or rect(l["bbox"])):
                err(f"line zone {l['id']} points differ")
zones = doc.findall(".//t:zone", NS)
extra = [z.get(XID) for z in zones if z.get(XID) not in LINES and z.get(XID) not in {r["id"] for d in data.values() for r in d["regions"]}]
if extra:
    err(f"zones not in contract: {extra}")
print(f"4 contract IDs: {len(zones)} zones checked")

# 5 ---------------------------------------------------------------------------
body = doc.find(".//t:body", NS)
lbs = body.findall(".//t:lb", NS)
lb_by_line = Counter(lb.get("facs")[1:] for lb in lbs)
for lid, (l, r) in LINES.items():
    want = 0 if r["production"] == "handwritten" else 1
    if lb_by_line[lid] != want:
        err(f"line {lid}: {lb_by_line[lid]} <lb> (expected {want})")
    if want == 0 and not referenced[r["id"]]:
        err(f"handwritten line {lid}: region not referenced")

buf = defaultdict(str)
SKIP = {T + "note", T + "add", T + "figDesc"}
def walk(el, cur):
    if el.tag == T + "lb":
        cur = el.get("facs")[1:]
    if el.text and el.tag not in SKIP:
        buf[cur] += el.text
    for ch in el:
        if not isinstance(ch.tag, str):
            continue
        if ch.tag in SKIP:
            pass
        elif ch.tag == T + "fw":
            walk(ch, cur)                 # fw carries its own line; flow resumes after it
        else:
            cur = walk(ch, cur)
        if ch.tail:
            buf[cur] += ch.tail
    return cur
walk(body, None)
norm = lambda s: re.sub(r"\s+", " ", s).strip()
bad = 0
for lid, (l, r) in LINES.items():
    if r["production"] == "handwritten":
        continue
    if norm(buf[lid]) != norm(l["text"]):
        bad += 1
        err(f"text mismatch {lid}:\n   tei : {norm(buf[lid])!r}\n   json: {l['text']!r}")
# handwritten: compare note/add string value
for lid, (l, r) in LINES.items():
    if r["production"] == "handwritten":
        el = next((e for e in body.iter() if e.get("facs") == f"#{r['id']}"), None)
        if el is None or norm("".join(el.itertext())) != norm(l["text"]):
            err(f"handwritten text mismatch {lid}")
print(f"5 line text reconstruction: {len(LINES)} lines compared, {bad} printed mismatches")

# 6 ---------------------------------------------------------------------------
def in_fw(el):
    return any(a.tag == T + "fw" for a in el.iterancestors())
prev = None
for el in body.iter(T + "lb", T + "pb"):
    if el.tag == T + "pb":
        expect = bool(prev and LINES[prev][0]["hyphen_end"])
        if (el.get("break") == "no") != expect:
            err(f"pb n={el.get('n')}: break mismatch")
        continue
    lid = el.get("facs")[1:]
    if in_fw(el) or any(a.tag in (T + "figure",) for a in el.iterancestors()):
        if el.get("break"):
            err(f"{lid}: unexpected @break")
        continue
    expect = bool(prev and LINES[prev][0]["hyphen_end"])
    if (el.get("break") == "no") != expect:
        err(f"{lid}: break={el.get('break')} but previous line {prev} hyphen_end={not expect and False or expect}")
    prev = lid
print("6 break=no consistency: checked")

# 7 ---------------------------------------------------------------------------
TYPE_EL = {"underline": ("hi", "underline"), "ink-over": ("hi", "overdrawn"), "damage": ("damage", None), "unclear": ("unclear", None)}
n_flags = 0
for lid, (l, r) in LINES.items():
    for k, f in enumerate(l["flags"], 1):
        s, e = max(0, f["start"]), min(len(l["text"]), f["end"])
        if s >= e:
            gid = f"gap-{lid}"
            if l["text"] == "" and gid not in ids:
                err(f"{lid}: empty reading without <gap>")
            continue
        n_flags += 1
        base = f"f-{lid}-{k}"
        frs = [ids[base]] if base in ids else [ids[i] for i in sorted(ids) if re.fullmatch(re.escape(base) + r"-[a-z]", i)]
        if not frs:
            err(f"flag {base} ({f['type']}) not encoded"); continue
        gi, rend = TYPE_EL[f["type"]]
        for fr in frs:
            if etree.QName(fr).localname != gi or (rend and fr.get("rend") != rend):
                err(f"flag {base}: wrong element <{etree.QName(fr).localname} rend={fr.get('rend')}>")
            if f.get("hand") and r["production"] != "handwritten" and fr.get("hand") != f"#{f['hand']}":
                err(f"flag {base}: hand mismatch")
        got = "".join("".join(fr.itertext()) for fr in frs)
        if got != l["text"][s:e]:
            err(f"flag {base}: text {got!r} != {l['text'][s:e]!r}")
print(f"7 flags: {n_flags} non-empty flags checked")

# counts -----------------------------------------------------------------------
c = Counter(etree.QName(el).localname for el in body.iter(tag=etree.Element))
hi = Counter(el.get("rend") for el in body.iter(T + "hi"))
frag = sum(1 for el in body.iter() if el.get("next") or el.get("prev"))
print("\ncounts (text/body):", {k: c[k] for k in ("pb", "lb", "fw", "head", "p", "hi", "add", "note", "unclear", "damage", "gap", "figure", "label", "item")})
print("  hi by @rend:", dict(hi), f"| elements that are split fragments (@next/@prev): {frag}")
print("  zones:", len(zones), "(regions:", sum(1 for z in zones if z.get("type") != "line"), ", lines:", sum(1 for z in zones if z.get("type") == "line"), ")")
print("  back notes:", len(doc.findall(".//t:back//t:note", NS)))

if errors:
    print(f"\nFAILED: {len(errors)} problem(s)")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("\nALL CHECKS PASSED")
