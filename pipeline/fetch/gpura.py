#!/usr/bin/env python3
"""Fetch stage: a Gpura item link -> items/<slug>/ with item.json, page images and Gpura's own text.

    python3 pipeline/fetch/gpura.py https://gpura.org/item/<slug> [--pages 17-19,25] [--items-dir items]

Uses only Gpura's public interfaces:
  Omeka S API   https://gpura.org/api/items?property[0]...=<slug>   -> Dublin Core metadata
  IIIF manifest https://gpura.org/iiif-presentation/3/item/<id>/manifest -> canvases, image services,
                per-canvas text (supplementing annotation), full-text rendering
Prints the item folder path on the last line (run.py reads it).
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = "https://gpura.org/api/items"
MANIFEST = "https://gpura.org/iiif-presentation/3/item/{id}/manifest"
UA = {"User-Agent": "gpura-corpus-pipeline (+https://github.com/beniza/gpura-corpus)"}


def get(url, binary=False, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                data = r.read()
            return data if binary else data.decode("utf-8")
        except Exception as e:  # network hiccups: retry, then fail loudly
            if k == tries - 1:
                raise SystemExit(f"fetch failed: {url}: {e}")
            time.sleep(2 * (k + 1))


def slug_of(link):
    m = re.search(r"gpura\.org/(?:s/[^/]+/)?item/([^/?#]+)", link)
    return urllib.parse.unquote(m.group(1)) if m else link.strip("/")


def omeka_item(slug):
    if slug.isdigit():
        return json.loads(get(f"{API}/{slug}"))
    q = urllib.parse.urlencode({"property[0][property]": "dcterms:identifier", "property[0][type]": "eq",
                                "property[0][text]": slug})
    hits = json.loads(get(f"{API}?{q}"))
    if not hits:
        raise SystemExit(f"no Gpura item with identifier {slug!r}")
    return hits[0]


def is_mal(s):
    return any("ഀ" <= c <= "ൿ" for c in s)


def values(item, prop):
    return [v.get("@value") or v.get("@id") for v in item.get(prop, []) if (v.get("@value") or v.get("@id"))]


def pick(item, prop, malayalam):
    vs = values(item, prop)
    hit = [v for v in vs if is_mal(v) == malayalam]
    return hit[0] if hit else (vs[0] if vs else None)


def parse_pages(spec, n):
    if not spec:
        return list(range(1, n + 1))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return [p for p in out if 1 <= p <= n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("link", help="Gpura item URL, identifier (slug) or numeric Omeka id")
    ap.add_argument("--pages", help="viewer page (canvas) numbers, e.g. 17-19,25. Default: all")
    ap.add_argument("--items-dir", default=str(REPO / "items"))
    a = ap.parse_args()

    item = omeka_item(slug_of(a.link))
    slug = values(item, "dcterms:identifier")[0]
    man = json.loads(get(MANIFEST.format(id=item["o:id"])))
    canvases = man["items"]
    pages = parse_pages(a.pages, len(canvases))
    out = Path(a.items_dir) / slug
    for d in ("images", "ocr", "page", "tei"):
        (out / d).mkdir(parents=True, exist_ok=True)

    first = canvases[0]["id"]
    canvas_base = re.sub(r"/canvas/\d+$", "/canvas/{n}", first)
    svc = canvases[0]["items"][0]["items"][0]["body"]["service"][0]["id"]
    image_base = re.sub(r"\d+\.jpg$", "", svc)
    rendering = {r.get("format"): r["id"] for r in man.get("rendering", [])}

    title_ml = pick(item, "dcterms:title", True)
    title_en = pick(item, "dcterms:title", False)
    strip_year = lambda t: re.sub(r"^\s*\d{4}\s*-\s*", "", t or "").strip()
    meta = {
        "title": strip_year(title_ml),
        "title_en": strip_year(title_en),
        "author": pick(item, "dcterms:creator", False),
        "author_ml": pick(item, "dcterms:creator", True),
        "translator": pick(item, "gpura:translator", False),
        "translator_ml": pick(item, "gpura:translator", True),
        "publisher": pick(item, "dcterms:publisher", False),
        "publisher_ml": pick(item, "dcterms:publisher", True),
        "printer": pick(item, "bibo:producer", False),
        "date": (values(item, "dcterms:issued") or [None])[0],
        "pages_total": len(canvases),
        "dimensions": (values(item, "dcterms:format") or [None])[0],
        "holding": (values(item, "dcterms:coverage") or [None])[0],
        "digitized": (values(item, "dcterms:available") or [None])[0],
        "language": (values(item, "dcterms:language") or ["ml"])[0],
        "gpura_item": f"https://gpura.org/item/{slug}",
        "gpura_api": f"{API}/{item['o:id']}",
        "iiif_manifest": MANIFEST.format(id=item["o:id"]),
        "iiif_image_base": image_base,
        "canvas_base": canvas_base,
        "canvases_encoded": pages,
        "rights": "Public domain (per Gpura)",
    }
    for k, who in (("title", "author_ml"), ("title_en", "author")):   # Gpura titles often end "- <author>"
        if meta.get(k) and meta.get(who) and meta[k].endswith(meta[who]):
            meta[k] = meta[k][: -len(meta[who])].rstrip(" -–")
    meta = {k: v for k, v in meta.items() if v not in (None, "")}
    meta["source_label"] = f"'{meta.get('title_en') or meta.get('title')}' (Malayalam, {meta.get('date', 'n.d.')})"
    meta["status"] = ("Automatic encoding: line boxes detected by the pipeline, text is Gpura's existing OCR aligned "
                      "to those lines. Not reviewed by a person.")

    # keep anything a person added to an existing item.json (e.g. a pinned 'generated' timestamp)
    old = {}
    if (out / "item.json").exists():
        old = json.loads((out / "item.json").read_text(encoding="utf-8"))
    meta = {**meta, **{k: v for k, v in old.items() if k not in meta or k in ("generated", "status")}}
    meta["canvases_encoded"] = sorted(set(pages) | set(old.get("canvases_encoded", [])))
    (out / "item.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    full = out / "ocr" / "gpura_full.txt"
    if "text/plain" in rendering and not full.exists():
        full.write_text(unicodedata.normalize("NFC", get(rendering["text/plain"])), encoding="utf-8", newline="\n")
    for n in pages:
        c = canvases[n - 1]
        img = out / "images" / f"p{n:03d}.jpg"
        if not img.exists():
            body = c["items"][0]["items"][0]["body"]
            img.write_bytes(get(body["service"][0]["id"] + "/full/max/0/default.jpg", binary=True))
        txt = out / "ocr" / f"gpura_existing_{n:04d}.txt"
        if not txt.exists():
            tb = [a["body"] for ap_ in c.get("annotations", []) for a in ap_.get("items", [])
                  if a.get("motivation") == "supplementing" and a["body"].get("format") == "text/plain"]
            txt.write_text(get(tb[0]["id"]) if tb else "", encoding="utf-8", newline="\n")
        print(f"  canvas {n}: {img.name}, {txt.name}", flush=True)
    print(out)


if __name__ == "__main__":
    main()
