#!/usr/bin/env python3
"""Line-detection benchmark: our detector vs Kraken vs Surya on pages with a known answer.

    python3 pipeline/tools/bench_lines.py [--only ours,kraken,surya]

Reference pages (BENCH below):
  - american-aikyanadu-1971 p017, p018: reviewed by a person against the scan (printed lines only;
    map labels and handwriting excluded).  Ordinary body text with reader underlining.
  - 1957-sir-isaac-newton p007: the contents page.  Reference = the current line inventory, one line per
    contents row, checked by eye against the scan (3 Nov 2026).  Biased towards our detector's box
    geometry, so read it for "rows kept whole", not for box precision.

Scores per page and detector:
  found    reference lines matched by a detection with IoU >= 0.5 (one detection per reference line)
  extra    detections matching no reference line with IoU >= 0.3 (specks, rules, split fragments)
  split    reference lines covered by two or more detections, none matching on its own (cut rows)

Kraken and Surya run from their own virtual environments (see pipeline/tools/setup_bench.sh), so their
dependencies never touch the pipeline's.  A detector that is not installed is skipped.
Unscored pages: any image in .cache/bench/pages/ (complex layouts with no known answer: newspapers,
contents pages, tables, pictures) is run too; its detections are saved for overlays
(pipeline/tools/bench_overlay.py) and simple layout checks, but not scored.
Every run saves the detections: .cache/bench/<detector>/<page>/boxes.json.
Results: .cache/bench/results.json and a table on stdout.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from lxml import etree
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / ".cache" / "bench"
BENCH = [
    ("american-aikyanadu-1971", "p017", "reviewed"),
    ("american-aikyanadu-1971", "p018", "reviewed"),
    ("1957-sir-isaac-newton", "p007", "contents rows, checked by eye"),
]
EXE = ".exe" if os.name == "nt" else ""
BIN = "Scripts" if os.name == "nt" else "bin"


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i) if i else 0.0


def poly_bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def reference(item, page):
    d = json.loads((REPO / "items" / item / "ocr" / f"{page}.lines.json").read_text(encoding="utf-8"))
    return [l["bbox"] for r in d["regions"]
            if r.get("production", "printed") == "printed" and r["type"] not in ("map-label", "legend", "caption")
            for l in r.get("lines", []) if l.get("text")]


def image_path(item, page):
    for ext in ("png", "jpg"):
        f = REPO / "items" / item / "images" / f"{page}.{ext}"
        if f.exists():
            return f
    raise SystemExit(f"missing scan {item}/{page}: run `python run.py items/{item} --stages site` to download it")


# --------------------------------------------------------------------------- detectors
def det_ours(img_path, work):
    os.environ.setdefault("GPURA_ITEM_DIR", str(img_path.parents[1]))
    sys.path.insert(0, str(REPO / "pipeline" / "align"))
    import auto_lines                                   # noqa: E402  (needs GPURA_ITEM_DIR at import)
    lines, _ = auto_lines.detect_lines(Image.open(img_path))
    return [[int(v) for v in l["bbox"]] for l in lines]


def venv_tool(name, tool):
    f = REPO / ".cache" / f"venv-{name}" / BIN / (tool + EXE)
    return f if f.exists() else None


def det_kraken(img_path, work):
    cli = venv_tool("kraken", "kraken")
    if not cli:
        return None
    out = work / "kraken.xml"
    subprocess.run([str(cli), "-x", "-i", str(img_path), str(out), "segment", "-bl"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ns = {"p": etree.parse(str(out)).getroot().nsmap.get(None)}
    boxes = []
    for tl in etree.parse(str(out)).iter(f"{{{ns['p']}}}TextLine"):
        c = tl.find("p:Coords", ns)
        if c is not None:
            pts = [tuple(map(float, p.split(","))) for p in c.get("points").split()]
            boxes.append([int(v) for v in poly_bbox(pts)])
    return boxes


def det_surya(img_path, work):
    cli = venv_tool("surya", "surya_detect")
    if not cli:
        return None
    src = work / "surya_in"; src.mkdir(exist_ok=True)
    shutil.copy(img_path, src / img_path.name)
    subprocess.run([str(cli), str(src), "--output_dir", str(work / "surya_out")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = next((work / "surya_out").rglob("results.json"))
    data = json.loads(res.read_text(encoding="utf-8"))
    pages = next(iter(data.values()))
    boxes = []
    for b in pages[0].get("bboxes", []):
        x1, y1, x2, y2 = b["bbox"]
        boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)])
    return boxes


DETECTORS = {"ours": det_ours, "kraken": det_kraken, "surya": det_surya}


# --------------------------------------------------------------------------- scoring
def score(ref, det):
    used, found, split = set(), 0, 0
    for r in ref:
        best = max(range(len(det)), key=lambda i: iou(det[i], r), default=None)
        if best is not None and best not in used and iou(det[best], r) >= 0.5:
            used.add(best); found += 1
        else:
            parts = [d for d in det if iou(d, r) > 0.05 and d[2] * d[3] < r[2] * r[3]]
            split += len(parts) >= 2
    extra = sum(1 for i, d in enumerate(det) if i not in used and max((iou(d, r) for r in ref), default=0) < 0.3)
    return {"ref": len(ref), "found": found, "extra": extra, "split": split, "detections": len(det)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(DETECTORS))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    pages = [(f"{item}_{page}", image_path(item, page), reference(item, page), kind) for item, page, kind in BENCH]
    pages += [(f.stem, f, None, "unscored") for f in sorted((OUT / "pages").glob("*.jpg"))]
    for name in a.only.split(","):
        for key, img, ref, kind in pages:
            work = OUT / name / key
            work.mkdir(parents=True, exist_ok=True)
            t = time.time()
            try:
                det = DETECTORS[name](img, work)
            except subprocess.CalledProcessError as e:
                print(f"  {name} failed on {item}/{page}: {e}")
                det = None
            if det is None:
                print(f"  {name}: not installed or failed, skipped (see pipeline/tools/setup_bench.sh)")
                break
            (work / "boxes.json").write_text(json.dumps(det) + "\n", encoding="utf-8")
            s = {"detector": name, "page": key, "reference": kind, "seconds": round(time.time() - t, 1),
                 **(score(ref, det) if ref is not None else {"detections": len(det)})}
            results.append(s)
            if ref is not None:
                print(f"  {name:7} {key[:34]:34} found {s['found']:3}/{s['ref']:<3} extra {s['extra']:3}  "
                      f"split {s['split']:2}  ({s['seconds']}s)", flush=True)
            else:
                print(f"  {name:7} {key[:34]:34} {len(det):4} detections (unscored)  ({s['seconds']}s)", flush=True)
    f = OUT / "results.json"                            # keep earlier runs of the other detectors
    ran = {r["detector"] for r in results}
    old = [r for r in (json.loads(f.read_text(encoding="utf-8")) if f.exists() else []) if r["detector"] not in ran]
    f.write_text(json.dumps(old + results, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
