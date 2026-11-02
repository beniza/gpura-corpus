#!/usr/bin/env python3
"""Render the TEI extract to a reading-HTML fragment.

    python3 tei/tei2html.py [in.tei.xml] [out.html]

Defaults: tei/american-aikyanadu-p017-019.tei.xml -> tei/reading.html

The output is one <div class="tei-reading"> with a small embedded <style> (all
rules scoped to .tei-reading) and no scripts. A checkbox turns on the original
line breaks (pure CSS).  Mapping, TEI -> HTML:

    pb + following fw ..... span.page-furniture  (page label, page number, running head;
                            .inline when the page break falls inside a paragraph)
    div[@type=chapter] .... section.chapter / h2      div[@type=section] ... section.section / h3
    p ..................... p.para                    lb ..................... br.lb (hidden unless toggled)
    hi[@rend=underline] ... span.ul.hand-<ink>        hi[@rend=overdrawn] .... span.overdrawn.hand-<ink>
    unclear ............... span.unclear (title = reason, certainty, review note)
    damage ................ span.damage               gap .................... span.gap
    add ................... span.reader-add           note[@type=annotation] . aside.reader-note
    figure[@type=map] ..... figure.map (IIIF crop, caption, description, legend, labels)
    back notes ............ details.tei-notes
"""
import os
import sys
from html import escape
from pathlib import Path

from lxml import etree

HERE = (Path(os.environ["GPURA_ITEM_DIR"]) / "tei") if os.environ.get("GPURA_ITEM_DIR") else Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "american-aikyanadu-p017-019.tei.xml"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "reading.html"

T = "{http://www.tei-c.org/ns/1.0}"
XID = "{http://www.w3.org/XML/1998/namespace}id"
NS = {"t": "http://www.tei-c.org/ns/1.0"}

doc = etree.parse(str(SRC))
IDS = {el.get(XID): el for el in doc.iter() if el.get(XID)}
NOTES = {}  # target id -> review note text
for n in doc.findall(".//t:back//t:note", NS):
    for tok in (n.get("target") or "").split():
        NOTES[tok.lstrip("#")] = n.text or ""
HANDS = {"#blue-ink": "blue ink", "#dark-ink": "dark ink"}
CSS = """
.tei-reading{--ink:#1d1d1f;--muted:#6b6b70;--rule:#d9d6cf;--paper:#fbfaf7;--blue:#2747c9;--dark:#6b4a2b;--warn:#a15c00;
  font-family:"Noto Serif Malayalam","Noto Sans Malayalam","Manjari","Rachana","Meera",serif;color:var(--ink);background:var(--paper);
  line-height:1.9;font-size:1.08rem;max-width:44rem;margin:0 auto;padding:1.25rem 1rem 2rem}
.tei-reading .tei-meta{font-family:system-ui,sans-serif;font-size:.85rem;color:var(--muted);border-bottom:1px solid var(--rule);padding-bottom:.75rem;margin-bottom:1rem;line-height:1.5}
.tei-reading .tei-meta .title{font-family:inherit;font-size:1.35rem;color:var(--ink);margin:0 0 .25rem;font-weight:600}
.tei-reading .tei-meta .title [lang=ml]{font-family:"Noto Serif Malayalam","Manjari","Rachana",serif}
.tei-reading .tei-meta .caveat{margin-top:.5rem;color:var(--warn)}
.tei-reading .controls{font-family:system-ui,sans-serif;font-size:.8rem;color:var(--muted);margin:.5rem 0 1rem}
.tei-reading .tei-text br.lb,.tei-reading .tei-text .lb-hyph{display:none}
.tei-reading #tei-show-lines:checked ~ .tei-text br.lb{display:inline}
.tei-reading #tei-show-lines:checked ~ .tei-text .lb-hyph{display:inline;color:var(--muted)}
.tei-reading .page-furniture{display:flex;gap:1rem;align-items:baseline;margin:1.5rem 0 .75rem;padding-top:.35rem;border-top:1px dashed var(--rule);
  font-family:system-ui,sans-serif;font-size:.78rem;color:var(--muted);line-height:1.4;text-indent:0}
.tei-reading .page-furniture.inline{display:inline-flex;gap:.5em;margin:0 .25em;padding:0 .45em;border:1px solid var(--rule);border-radius:3px;
  font-size:.68rem;vertical-align:.15em;white-space:nowrap}
.tei-reading .page-furniture.inline .fw-header{flex:none}
.tei-reading .page-furniture .pb-label{font-weight:600;letter-spacing:.02em}
.tei-reading .page-furniture .fw-header{flex:1;text-align:center;font-family:"Noto Serif Malayalam","Manjari",serif}
.tei-reading h2.chapter-head{font-size:1.6rem;text-align:center;margin:1rem 0 1.25rem;font-weight:700}
.tei-reading h3.section-head{font-size:1.15rem;margin:1.5rem 0 .75rem;font-weight:700}
.tei-reading p.para{margin:0 0 1rem;text-indent:2em;text-align:start}
.tei-reading .ul{text-decoration-line:underline;text-decoration-thickness:2px;text-underline-offset:.32em}
.tei-reading .ul.hand-blue-ink{text-decoration-color:var(--blue)}
.tei-reading .ul.hand-dark-ink{text-decoration-color:var(--dark)}
.tei-reading .ul .ul{text-decoration-style:double}
.tei-reading .overdrawn{background:linear-gradient(transparent 30%,rgba(39,71,201,.13) 30%,rgba(39,71,201,.13) 52%,transparent 52%)}
.tei-reading .unclear{border-bottom:1px dotted var(--warn);cursor:help}
.tei-reading .unclear.cert-low{background:rgba(161,92,0,.10)}
.tei-reading .unclear::after{content:"?";font-family:system-ui,sans-serif;font-size:.6em;vertical-align:super;color:var(--warn);margin-left:1px}
.tei-reading .damage{background:repeating-linear-gradient(135deg,transparent 0 3px,rgba(120,90,60,.16) 3px 5px);cursor:help}
.tei-reading .gap{font-family:system-ui,sans-serif;font-size:.8em;color:var(--muted);font-style:italic}
.tei-reading .reader-add,.tei-reading .reader-note{font-family:"Segoe Print","Bradley Hand","Comic Neue",cursive,system-ui,sans-serif;color:var(--blue)}
.tei-reading .reader-add{font-size:.8em;margin:0 .2em;padding:0 .3em;border:1px solid currentColor;border-radius:1em;text-indent:0}
.tei-reading .reader-note{display:block;margin:.25rem 0 .75rem auto;max-width:18rem;padding:.3rem .6rem;border-left:3px solid currentColor;
  background:rgba(39,71,201,.05);font-size:.95rem;line-height:1.4}
.tei-reading .reader-note .who,.tei-reading .reader-mark .who{display:block;font-family:system-ui,sans-serif;font-size:.7rem;color:var(--muted);font-style:normal}
.tei-reading figure.map{margin:1rem 0;padding:.75rem;border:1px solid var(--rule);background:#fff}
.tei-reading figure.map img{display:block;width:100%;height:auto;background:#eee}
.tei-reading figure.map figcaption{font-weight:700;text-align:center;margin:.5rem 0}
.tei-reading .figdesc,.tei-reading .reader-mark{font-family:system-ui,sans-serif;font-size:.82rem;color:var(--muted);line-height:1.5}
.tei-reading .reader-mark{color:var(--blue)}
.tei-reading .legend,.tei-reading .map-labels{margin:.5rem 0;padding-left:1.2rem;font-size:.95rem;line-height:1.6}
.tei-reading .list-head{font-family:system-ui,sans-serif;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-top:.75rem}
.tei-reading .rotated-note{font-family:system-ui,sans-serif;font-size:.72rem;color:var(--muted)}
.tei-reading details.tei-notes{margin-top:2rem;font-family:system-ui,sans-serif;font-size:.8rem;color:var(--muted);line-height:1.5}
.tei-reading details.tei-notes li{margin:.2rem 0}
.tei-reading details.tei-notes .ml{font-family:"Noto Serif Malayalam","Manjari",serif}
"""


def H(tag, cls=None, text=None, **attrs):
    el = etree.Element(tag)
    if cls:
        el.set("class", cls)
    for k, v in attrs.items():
        if v is not None:
            el.set(k.rstrip("_").replace("_", "-"), str(v))
    if text:
        el.text = text
    return el


def add_text(parent, s):
    if not s:
        return
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + s
    else:
        parent.text = (parent.text or "") + s


def local(el):
    return etree.QName(el).localname


def hand_cls(el):
    h = el.get("hand")
    return f"hand-{h[1:]}" if h else ""


def iiif_region(zone_id, size="!1600,1600", rotation=None):
    """IIIF Image API crop of a zone from its surface's full-image URL."""
    z = IDS[zone_id]
    surf = next(a for a in z.iterancestors() if local(a) == "surface")
    url = surf.find("t:graphic", NS).get("url")
    base = url.split("/full/")[0]
    x, y = int(z.get("ulx")), int(z.get("uly"))
    w, h = int(z.get("lrx")) - x, int(z.get("lry")) - y
    rot = rotation if rotation is not None else {"270": 90, "90": 270}.get(z.get("rotate"), 0)
    return f"{base}/{x},{y},{w},{h}/{size}/{rot}/default.jpg"


def unclear_title(el):
    bits = ["Uncertain reading"]
    if el.get("reason"):
        bits.append("reason: " + el.get("reason").replace(" ", ", "))
    if el.get("cert"):
        bits.append("certainty: " + el.get("cert"))
    t = "; ".join(bits)
    n = NOTES.get(el.get(XID) or "")
    return t + (f". Note: {n}" if n else "")


def render_children(src, out):
    """Render the mixed content of TEI element `src` into HTML element `out`."""
    add_text(out, src.text)
    kids = [k for k in src if isinstance(k.tag, str)]
    consumed = set()
    for i, ch in enumerate(kids):
        if id(ch) in consumed:
            add_text(out, ch.tail)
            continue
        if local(ch) == "pb":
            if ch.get("break") == "no":
                out.append(H("span", "lb-hyph", "-"))
            inline = local(src) in ("p", "head", "item", "label")
            bar = H("span", "page-furniture" + (" inline" if inline else ""), **{"data-facs": ch.get("facs", "").lstrip("#"), "data-n": ch.get("n")})
            bar.append(H("span", "pb-label", f"p. {ch.get('n')}"))
            j = i + 1
            while j < len(kids) and local(kids[j]) == "fw" and not (kids[j - 1].tail or "").strip():
                bar.append(render(kids[j]))
                consumed.add(id(kids[j]))
                j += 1
            out.append(bar)
            add_text(out, ch.tail)
            continue
        node = render(ch)
        if node is not None:
            out.append(node)
        add_text(out, ch.tail)


def is_leading(lb):
    """lb at the very start of its container, or directly after page furniture."""
    prev = lb.getprevious()
    while prev is not None and not isinstance(prev.tag, str):
        prev = prev.getprevious()
    if prev is None:
        return not (lb.getparent().text or "").strip()
    return local(prev) in ("fw", "pb") and not (prev.tail or "").strip()


def render(el):
    name = local(el)
    if name == "lb":
        if is_leading(el):
            return None
        frag = H("span", "lb-wrap")
        if el.get("break") == "no":
            frag.append(H("span", "lb-hyph", "-"))
        frag.append(H("br", "lb", **{"data-facs": el.get("facs", "").lstrip("#")}))
        return frag
    if name == "fw":
        s = H("span", f"fw fw-{el.get('type')}", **{"data-facs": el.get("facs", "").lstrip("#")})
        render_children(el, s)
        return s
    if name == "div":
        typ = el.get("type")
        sec = H("section", typ, **{"data-n": el.get("n")})
        render_children(el, sec)
        return sec
    if name == "head":
        div = el.getparent()
        tag = "h2" if div.get("type") == "chapter" else "h3"
        h = H(tag, f"{div.get('type')}-head", **{"data-facs": el.get("facs", "").lstrip("#")})
        render_children(el, h)
        return h
    if name == "p":
        p = H("p", "para", **{"data-facs": el.get("facs", "").replace("#", "")})
        render_children(el, p)
        return p
    if name == "hi":
        rend = el.get("rend")
        ink = HANDS.get(el.get("hand"), "unknown ink")
        cls = {"underline": "ul", "overdrawn": "overdrawn"}.get(rend, "hi")
        title = {"underline": f"Reader's underline ({ink})",
                 "overdrawn": f"Reader's stroke drawn through the print ({ink}); text still legible"}.get(rend)
        if rend == "overdrawn" and NOTES.get(el.get(XID) or ""):
            title += ". " + NOTES[el.get(XID)]
        s = H("span", f"{cls} {hand_cls(el)}".strip(), title=title, id=el.get(XID),
              **{"data-facs": (el.get("facs") or "").lstrip("#") or None,
                 "data-part-of": (el.get("next") or el.get("prev")) and "split-span"})
        render_children(el, s)
        return s
    if name == "unclear":
        s = H("span", f"unclear cert-{el.get('cert', 'unknown')}", title=unclear_title(el), id=el.get(XID))
        render_children(el, s)
        return s
    if name == "damage":
        t = "Damaged" + (f" ({el.get('agent')})" if el.get("agent") else "")
        n = NOTES.get(el.get(XID) or "")
        s = H("span", "damage", title=t + (f". Note: {n}" if n else ""), id=el.get(XID))
        render_children(el, s)
        return s
    if name == "gap":
        n = NOTES.get(el.get(XID) or "")
        return H("span", "gap", "[not transcribed]", title=n or None, id=el.get(XID))
    if name == "add":
        s = H("span", "reader-add" + (" circled" if el.get("rend") == "circled" else ""),
              title=f"Reader's addition ({HANDS.get(el.get('hand'), 'unknown ink')})")
        render_children(el, s)
        return s
    if name == "note" and el.get("type") == "annotation":
        a = H("aside", f"reader-note {hand_cls(el)}", lang=el.get("{http://www.w3.org/XML/1998/namespace}lang"),
              **{"data-facs": el.get("facs", "").lstrip("#")})
        a.append(H("span", "who", f"Reader's handwritten note ({HANDS.get(el.get('hand'), 'unknown ink')}; position: {el.get('place')})"))
        inner = H("span", "note-text")
        render_children(el, inner)
        a.append(inner)
        return a
    if name == "figure" and el.get("type") == "map":
        return render_map(el)
    if name == "figure" and el.get("type") == "reader-mark":
        return H("p", "reader-mark", el.findtext("t:figDesc", namespaces=NS))
    # fallback: keep content
    s = H("span", f"tei-{name}")
    render_children(el, s)
    return s


def render_map(fig):
    f = H("figure", "map", **{"data-facs": fig.get("facs").lstrip("#")})
    zid = fig.get("facs").lstrip("#")
    desc = fig.findtext("t:figDesc", namespaces=NS)
    f.append(H("img", src=iiif_region(zid, "!1400,1400"), alt="Page image of the map (IIIF crop, turned upright)", loading="lazy"))
    f.append(H("p", "rotated-note", "Image shown turned upright (the map is printed sideways on the page)."))
    head = fig.find("t:head", NS)
    cap = H("figcaption", **{"data-facs": head.get("facs").lstrip("#")})
    render_children(head, cap)
    f.append(cap)
    f.append(H("p", "figdesc", desc, lang="en"))
    lst = fig.find("t:list[@type='legend']", NS)
    f.append(H("div", "list-head", "Legend (elevation; അ. = അടി, feet)", lang="en"))
    ul = H("ul", "legend", **{"data-facs": lst.get("facs").lstrip("#")})
    for it in lst.findall("t:item", NS):
        li = H("li")
        render_children(it, li)
        ul.append(li)
    f.append(ul)
    f.append(H("div", "list-head", "Map labels (only the clearly legible ones are transcribed)", lang="en"))
    ul = H("ul", "map-labels")
    for lab in fig.findall("t:label", NS):
        li = H("li", **{"data-facs": lab.get("facs").lstrip("#")})
        render_children(lab, li)
        ul.append(li)
    f.append(ul)
    for rm in fig.findall("t:figure[@type='reader-mark']", NS):
        f.append(render(rm))
    return f


def meta():
    hd = doc.find("t:teiHeader", NS)
    m = H("header", "tei-meta", lang="en")
    t = H("div", "title")
    t.append(H("span", None, hd.findtext(".//t:titleStmt/t:title[@type='main']", namespaces=NS), lang="ml"))
    m.append(t)
    m.append(H("div", None, "C.P. Hill, translated by Kuttanad K. Ramakrishna Pillai. Trivandrum: State Institute of Languages, 1971. "
                            "Printed pages 1–3 (Gpura viewer pages 17–19)."))
    m.append(H("div", "caveat", "Demonstration encoding, not a Gpura publication. The readings are model-made (OCR plus Claude review) and have not been verified by a person. "
                                "Underlining and notes in blue or brown are a later reader's marks, not part of the printed book."))
    return m


def main():
    root = H("div", "tei-reading", lang="ml")
    style = H("style")
    style.text = CSS
    root.append(style)
    root.append(meta())
    cb = H("input", id="tei-show-lines", type="checkbox")
    root.append(cb)
    lab = H("label", "controls", " Show the printed line breaks", lang="en", for_="tei-show-lines")
    root.append(lab)
    text = H("div", "tei-text")
    render_children(doc.find(".//t:body", NS), text)
    root.append(text)

    notes = doc.findall(".//t:back//t:note", NS)
    det = H("details", "tei-notes", lang="en")
    det.append(H("summary", None, f"Transcription notes from the OCR review ({len(notes)})"))
    ol = H("ol")
    for n in notes:
        tgt = (n.get("target") or "").lstrip("#")
        li = H("li", **{"data-target": tgt})
        if tgt in IDS and local(IDS[tgt]) != "zone":
            a = H("a", None, "in text", href=f"#{tgt}")
            li.append(a)
            add_text(li, ": ")
        add_text(li, n.text or "")
        ol.append(li)
    det.append(ol)
    root.append(det)

    html = etree.tostring(root, method="html", encoding="unicode")
    DST.write_text(f"<!-- generated by tei/tei2html.py from {SRC.name}; fragment, no external resources except IIIF image -->\n{html}\n",
                   encoding="utf-8")
    print("wrote", DST)


if __name__ == "__main__":
    main()
