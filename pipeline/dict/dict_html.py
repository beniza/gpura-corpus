#!/usr/bin/env python3
"""Dictionary pages, step 4: render the TEI dictionary encoding as a readable, colour-coded page.

    GPURA_ITEM_DIR=items/<item> python3 pipeline/dict/dict_html.py

Reads tei/<item>.dict.tei.xml and writes docs/specimen/<item>/dictionary.html (and a copy of the TEI
beside it) showing every entry with its parts marked: headword, transliteration, etymology, part of
speech, sense numbers, English glosses, examples with their sources, usage labels, cross-references,
and derived words as nested entries.  Each entry links to its page in the explorer.
"""
import html
import shutil
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ITEM, REPO, item_dir  # noqa: E402

ROOT = item_dir()
NS = "{http://www.tei-c.org/ns/1.0}"
XID = "{http://www.w3.org/XML/1998/namespace}id"
CLS = {"orth": "orth", "pron": "pron", "etym": "etym", "pos": "pos", "lbl": "num", "def": "gloss", "quote": "ex",
       "bibl": "src", "usg": "usg", "xr": "xr", "note": "note", "fw": "fw"}


def text_of(el):
    return " ".join("".join(el.itertext()).split())


def render(el):
    out = []
    for c in el:
        tag = c.tag.replace(NS, "")
        if tag == "lb":
            continue
        if tag in ("form", "gramGrp", "cit"):
            out.append(f'<span class="{tag}">{render(c)}</span>')
        elif tag == "sense":
            out.append(f'<span class="sense">{render(c)}</span>')
        elif tag == "entry":
            out.append(f'<div class="sub">{render(c)}</div>')
        elif tag in CLS:
            label = {"xr": ("= " if c.get("type") == "syn" else "→ ")}.get(tag, "")
            out.append(f'<span class="{CLS[tag]}" title="{tag}{" " + c.get("type") if c.get("type") else ""}">'
                       f'{label}{html.escape(text_of(c))}</span>')
    return " ".join(out)


def main():
    src = ROOT / "tei" / f"{ROOT.name}.dict.tei.xml"
    t = etree.parse(str(src))
    body = t.find(f".//{NS}body")
    pid = t.find(f".//{NS}pb").get("facs").lstrip("#")
    cards = []
    for e in body.iter(f"{NS}entry", f"{NS}entryFree"):
        if e.getparent().tag in (f"{NS}entry",):
            continue                                   # derived entries are rendered inside their entry
        kind = "free" if e.tag.endswith("entryFree") else e.get("type", "")
        inner = html.escape(text_of(e)) if kind == "free" else render(e)
        cards.append(f'<article class="entry {kind}" id="{e.get(XID)}"><a class="loc" href="index.html#{pid}" '
                     f'title="Open the page with its lines">{e.get(XID)}</a>{inner}</article>')
    out = REPO / "docs" / "specimen" / ROOT.name
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, out / src.name)
    title = html.escape(ITEM.get("title_en") or ITEM.get("title", ""))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dictionary Entries</title>
<meta name="description" content="Entries of a dictionary page encoded in TEI, with headword, etymology, senses, glosses, examples and cross-references marked.">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&family=Noto+Serif+Malayalam:wght@400;700&display=swap">
<script src="../../nav.js" defer></script>
<style>
:root{{--bg:#F4F5F3;--surface:#fff;--fg:#1B2220;--muted:#5A6662;--line:#D3D9D5;--accent:#2B6A8A;
  --orth:#1B2220;--pron:#6b3fa0;--etym:#7a6a4a;--pos:#2f7a4f;--gloss:#1f4f8f;--ex:#8a3a2a;--src:#8a5a00;--usg:#2B6A8A;--xr:#a1372c}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#141917;--surface:#1C2320;--fg:#E4EAE7;--muted:#9AA7A2;--line:#33403B;--accent:#7DB8D6;
  --orth:#E4EAE7;--pron:#c7a6f0;--etym:#cdbb8e;--pos:#7cc79a;--gloss:#8fb8f0;--ex:#f0a090;--src:#e0b060;--usg:#7DB8D6;--xr:#f08a7e;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#141917;--surface:#1C2320;--fg:#E4EAE7;--muted:#9AA7A2;--line:#33403B;--accent:#7DB8D6;
  --orth:#E4EAE7;--pron:#c7a6f0;--etym:#cdbb8e;--pos:#7cc79a;--gloss:#8fb8f0;--ex:#f0a090;--src:#e0b060;--usg:#7DB8D6;--xr:#f08a7e;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 "IBM Plex Sans",system-ui,sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:40px 16px 80px;display:flex;flex-direction:column;gap:22px}}
h1{{font-family:Spectral,Georgia,serif;font-size:clamp(1.8rem,4vw,2.4rem);margin:0;line-height:1.2}}
p{{margin:0;max-width:74ch}} a{{color:var(--accent)}}
.lede{{color:var(--muted)}}
.legend{{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:.85rem}}
.entries{{columns:2 420px;column-gap:24px}}
.entry{{break-inside:avoid;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:0 0 12px;position:relative}}
.entry.free{{border-style:dashed;color:var(--muted)}}
.loc{{position:absolute;right:8px;top:6px;font-size:.68rem;color:var(--muted);text-decoration:none}}
.sub{{margin:6px 0 0 14px;padding-left:10px;border-left:2px solid var(--line)}}
.sense{{display:inline}}
[lang="ml"] .orth,.orth{{font-family:"Noto Serif Malayalam",serif;font-weight:700;font-size:1.08rem;color:var(--orth)}}
.pron{{font-style:italic;color:var(--pron)}}
.etym{{color:var(--etym);font-size:.88rem}}
.pos{{color:var(--pos);font-variant:small-caps;font-weight:600}}
.num{{font-weight:700}}
.gloss{{color:var(--gloss)}}
.ex{{color:var(--ex);font-family:"Noto Serif Malayalam",serif}}
.src{{color:var(--src);font-size:.82rem;font-weight:600}}
.usg{{color:var(--usg);font-size:.82rem;border:1px solid currentColor;border-radius:4px;padding:0 4px}}
.xr{{color:var(--xr)}}
.note{{color:var(--muted);font-size:.85rem}}
.fw{{color:var(--muted)}}
html[data-lipi] .orth,html[data-lipi] .ex{{font-family:inherit}}
</style></head><body>
<main class="wrap">
  <header style="display:flex;flex-direction:column;gap:10px">
    <span style="font-size:.75rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:600">Showcase · dictionary page</span>
    <h1>{title}: the entries of one page</h1>
    <p class="lede">Viewer page {int(pid[1:])}. Entries were found from the layout (first line flush, the rest indented); their parts were labelled by an AI model and checked to be exact, in-order pieces of the printed text. The page's text is Sarvam Vision's; the small type has some OCR errors. Derived words are shown as nested entries. Nothing here has been reviewed by a person.</p>
    <p><a href="index.html#{pid}">Open the page with its lines</a> · <a href="{src.name}">Download the TEI (dictionaries module)</a></p>
    <div class="legend"><span class="orth">headword</span><span class="pron">transliteration</span><span class="etym">etymology</span>
      <span class="pos">part of speech</span><span class="num">1.</span><span>sense</span><span class="gloss">English gloss</span><span class="ex">example</span>
      <span class="src">source</span><span class="usg">usage</span><span class="xr">→ cross-reference</span></div>
  </header>
  <section class="entries" lang="ml">{"".join(cards)}</section>
</main></body></html>
"""
    (out / "dictionary.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"  {len(cards)} entries -> docs/specimen/{ROOT.name}/dictionary.html")


if __name__ == "__main__":
    main()
