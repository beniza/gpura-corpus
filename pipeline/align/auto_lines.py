#!/usr/bin/env python3
"""Align stage: page image + Gpura's existing text -> ocr/<page>.lines.json (automatic, unreviewed).

For each page:
  1. find printed text lines by projection profiles on near-black, low-chroma pixels
     (coloured reader ink - blue/violet ballpoint - is ignored, so underlines do not merge lines);
  2. run Tesseract once on the page (psm 6) and attach its words to the detected lines by box centre;
     the Tesseract text is used only to decide which archive line belongs to which detected line;
  3. align Gpura's own text lines to the detected lines (dynamic programming on fuzzy similarity);
  4. write lines.json in the same contract the reviewed specimen uses.

Lines that match nothing are reported, not hidden:
  - a detected line with no archive line keeps the Tesseract reading, flagged unclear (cert low);
  - an archive line with no detected line goes to "unplaced" (the text may not be on the page).

    python3 pipeline/align/auto_lines.py [p017 p018 ...]   (GPURA_ITEM_DIR set; run.py does this)
"""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ITEM, REPO, canvas_no, item_dir, page_id, page_image  # noqa: E402

ROOT = item_dir()
_ai = ROOT / "ocr" / "ai_readings.json"          # AI readings for lines Gpura has no text for (pipeline/ai/)
AI_READINGS = json.loads(_ai.read_text(encoding="utf-8")) if _ai.exists() else {}
# the same reading found by its box: a line ID changes when region grouping changes, its box does not
AI_BY_BOX = {(k.split("_")[0], tuple(v["bbox"])): v for k, v in AI_READINGS.items()}
TESSDATA = os.environ.get("GPURA_TESSDATA") or str(REPO / ".cache" / "tessdata")
NON_TEXT_CONF = 0.45  # a page with no Gpura text and a median Tesseract confidence below this is not text
MIN_SIM = 35          # below this a detected line and an archive line are never paired
END_PUNCT = tuple(".?!:;”’\"')]")
WORD_FINAL = ("്", "ം", "ൻ", "ർ", "ൽ", "ൾ", "ൺ", "ഃ")   # shapes that end Malayalam words


# --------------------------------------------------------------------------- text normalisation
CHILLU_ZWJ = {"ണ്\u200d": "ൺ", "ന്\u200d": "ൻ", "ര്\u200d": "ർ", "ല്\u200d": "ൽ", "ള്\u200d": "ൾ", "ക്\u200d": "ൿ"}


def encode(s):
    """Apply the corpus encoding rules to archive text (see README 'Encoding conventions')."""
    s = unicodedata.normalize("NFC", s)
    for a, b in CHILLU_ZWJ.items():
        s = s.replace(a, b)
    s = s.replace("\u0d4e", "ർ")                       # dot reph -> atomic chillu RR
    s = s.replace("ൻ്റ", "ന്റ").replace("ൻറ", "ന്റ")   # NTA, however the archive spelled it
    s = s.replace("ററ", "റ്റ")                         # TTA in reformed-script print
    return re.sub(r"[ \t]+", " ", s).strip()


BASE = str.maketrans({"ൻ": "ന", "ർ": "ര", "ൽ": "ല", "ൾ": "ള", "ൺ": "ണ", "ൿ": "ക", "്": None,
                      "\u200c": None, "\u200d": None, "ു": None})


def key(s):
    """Loose form for similarity only: encoding differences and punctuation removed."""
    s = encode(s).translate(BASE)
    return re.sub(r"[^\w]", "", s)


def sim(a, b):
    a, b = key(a), key(b)
    if not a or not b:
        return 0.0
    return fuzz.ratio(a, b)


# --------------------------------------------------------------------------- line detection
def otsu(v):
    hist = np.bincount(v.ravel(), minlength=256).astype(float)
    p = hist / hist.sum()
    w = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (mu[-1] * w - mu) ** 2 / (w * (1 - w))
    return int(np.nanargmax(s))


def runs(mask):
    """[start, end) runs of True in a 1-D bool array."""
    d = np.diff(np.concatenate([[0], mask.astype(int), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def smooth(v, k):
    return np.convolve(v, np.ones(k) / k, mode="same") if k > 1 else v


def detect_lines(img):
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    mx, mn = a.max(axis=2), a.min(axis=2)
    t = otsu(mx.astype(np.uint8))
    ink = (mx < t * 0.85) & ((mx - mn) < 70)          # dark and grey: print, not coloured ballpoint
    H, W = ink.shape
    # text area: ignore scanner borders / gutter shadow (columns or rows that are mostly ink)
    colfrac = ink.mean(axis=0)
    rowfrac = ink.mean(axis=1)
    ink[:, colfrac > 0.5] = False
    ink[rowfrac > 0.5, :] = False
    cols = smooth(ink.sum(axis=0).astype(float), 25)
    xs = np.where(cols > 0.01 * H)[0]
    if not len(xs):
        return [], ink
    x0, x1 = int(xs[0]), int(xs[-1]) + 1
    rows = smooth(ink[:, x0:x1].sum(axis=1).astype(float), 5)
    bands = [(s, e) for s, e in runs(rows > 0.004 * (x1 - x0))]
    if not bands:
        return [], ink
    hs = np.array([e - s for s, e in bands])
    med = float(np.median(hs[hs > np.percentile(hs, 30)])) if len(hs) > 3 else float(hs.max())
    # merge diacritic slivers into the nearest neighbour band
    merged = []
    for s, e in bands:
        if merged and (s - merged[-1][1] < 0.18 * med or (e - s) < 0.35 * med and s - merged[-1][1] < 0.45 * med):
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    out = []
    for s, e in merged:
        h = e - s
        if h < 0.3 * med and rows[s:e].max() < 0.02 * (x1 - x0):
            continue                                   # specks
        k = max(1, int(round(h / (med * 1.15)))) if h > 1.6 * med else 1
        for i in range(k):                             # touching lines: cut at the profile minima
            if k == 1:
                out.append((s, e))
                break
            lo = s + int(h * (i + 0.5) / k) if i else s
            hi_ = s + int(h * (i + 0.5 + 1) / k) if i < k - 1 else e
            if i:
                w0 = max(s, s + int(h * i / k) - int(med * 0.3))
                w1 = min(e, s + int(h * i / k) + int(med * 0.3))
                lo = w0 + int(np.argmin(rows[w0:w1]))
            if i < k - 1:
                w0 = max(s, s + int(h * (i + 1) / k) - int(med * 0.3))
                w1 = min(e, s + int(h * (i + 1) / k) + int(med * 0.3))
                hi_ = w0 + int(np.argmin(rows[w0:w1]))
            out.append((lo, hi_))
    # horizontal segments within each band (page number | running head, table cells ...)
    gap = max(int(2.5 * med), int(0.06 * W))          # wider than any word space: page number | running head
    band_segs = []
    for s, e in out:
        c = ink[s:e, x0:x1].sum(axis=0) > 0
        segs = []
        for cs, ce in runs(c):
            if segs and cs - segs[-1][1] < gap:
                segs[-1] = (segs[-1][0], ce)
            else:
                segs.append((cs, ce))
        band_segs.append(segs)
    # table rows (a contents page: title ........ page number): a narrow last segment ending at the
    # right edge of the text, repeated on 3 or more bands with aligned right edges, is a column of the
    # same row, not a separate line.  Keep the row as one line.  Running heads (one band) are unaffected.
    tw = x1 - x0
    rows_ = set()
    tails = [(bi, sg[-1][1]) for bi, sg in enumerate(band_segs)
             if len(sg) > 1 and sg[-1][1] - sg[-1][0] < 0.25 * tw and sg[-1][1] > 0.75 * tw]
    if len(tails) >= 3:
        edge = float(np.median([r for _, r in tails]))
        rows_ = {bi for bi, r in tails if abs(r - edge) < 0.04 * tw}
        if len(rows_) >= 3:
            for bi in rows_:
                band_segs[bi] = [(band_segs[bi][0][0], band_segs[bi][-1][1])]
        else:
            rows_ = set()
    lines = []
    for bi, (s, e) in enumerate(out):
        segs = band_segs[bi]
        for cs, ce in segs:
            sub = ink[s:e, x0 + cs:x0 + ce]
            if sub.sum() < 0.05 * med * med:
                continue                               # stray mark
            r = np.where(sub.sum(axis=1) > 0)[0]
            ys, ye = s + int(r[0]), s + int(r[-1]) + 1
            prof = sub.sum(axis=1)
            base = s + int(np.where(prof > 0.35 * prof.max())[0][-1])
            lines.append({"band": bi, "bbox": [x0 + int(cs), ys, int(ce - cs), ye - ys], "baseline_y": min(max(base, ys), ye),
                          "table_row": bi in rows_})
    for l in lines:
        l["pitch"] = med
    return lines, ink


# --------------------------------------------------------------------------- complex pages and Surya
SURYA_VENVS = ("venv-surya-gpu", "venv-surya")       # set up with pipeline/tools/setup_bench.sh


def page_complexity(lines, ink):
    """Reasons our projection-profile detector is likely wrong on this page (empty list: simple page).

    It reads a page as horizontal stripes of ink, so it fails where something stands beside the text:
    a second column, a picture, an advertisement box.  Two symptoms show it: boxes much taller than a
    line (lines glued together by a picture or a neighbouring column), and a vertical gap through the
    text block (columns).  A contents page whose rows were recognised is left to our detector: a
    neural detector cuts its rows into cells.
    """
    if not lines:
        return []
    from scipy import ndimage
    H, W = ink.shape
    # character height from connected components: independent of how well the lines were found
    sl = ndimage.find_objects(ndimage.label(ink)[0])
    hs = np.array([s[0].stop - s[0].start for s in sl]); ws = np.array([s[1].stop - s[1].start for s in sl])
    ok = (hs >= 0.004 * H) & (hs < 0.05 * H) & (ws < 0.1 * W)
    if ok.sum() < 50:
        return []                                      # too little text to judge
    ch = float(np.median(hs[ok]))
    pitch = lines[0]["pitch"]
    reasons = []
    if pitch > 4 * ch:                                 # simple pages: 2.1-2.8 character heights per line
        reasons.append(f"detected lines are {pitch / ch:.0f} character heights tall (lines glued together "
                       f"by columns, pictures or ornament)")
    xs0 = min(l["bbox"][0] for l in lines); xs1 = max(l["bbox"][0] + l["bbox"][2] for l in lines)
    ys0 = min(l["bbox"][1] for l in lines); ys1 = max(l["bbox"][1] + l["bbox"][3] for l in lines)
    block = ink[ys0:ys1, xs0:xs1]
    if block.size and (xs1 - xs0) > 40 * ch:           # a contents page's page-number column sits at the edge
        prof = smooth(block.sum(axis=0).astype(float), max(3, int(ch)))
        med = np.median(prof)
        for s, e in runs(prof < 0.08 * med):
            left, right = s / len(prof), 1 - e / len(prof)
            if e - s >= 0.4 * ch and left > 0.2 and right > 0.2:     # text on both sides: columns
                reasons.append("a vertical gap runs through the text block (columns)")
                break
    return reasons


def surya_python():
    for v in SURYA_VENVS:
        for sub in ("Scripts/python.exe", "bin/python"):
            f = REPO / ".cache" / v / sub
            if f.exists():
                return f
    return None


def surya_boxes(pids):
    """Surya line boxes for these pages, cached per page in ocr/<page>.surya.json."""
    out, todo = {}, []
    for pid in pids:
        c = ROOT / "ocr" / f"{pid}.surya.json"
        if c.exists():
            out[pid] = json.loads(c.read_text(encoding="utf-8"))
        else:
            todo.append(pid)
    if todo:
        py = surya_python()
        if not py:
            return out
        tmp = ROOT / "ocr" / "_surya_batch.json"
        paths = [str(page_image(p)) for p in todo]
        print(f"  surya: detecting lines on {len(todo)} complex page(s)", flush=True)
        subprocess.run([str(py), str(REPO / "pipeline" / "align" / "surya_lines.py"), str(tmp)] + paths, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = json.loads(tmp.read_text(encoding="utf-8"))
        tmp.unlink()
        for pid, p in zip(todo, paths):
            rec = {"surya": res["surya"], "boxes": res["pages"][p]}
            (ROOT / "ocr" / f"{pid}.surya.json").write_text(json.dumps(rec) + "\n", encoding="utf-8", newline="\n")
            out[pid] = rec
    return out


def xycut(boxes):
    """Reading order by recursive XY-cut: split at a full-width horizontal gap (top to bottom) or, failing
    that, a full-height vertical gap (left to right); boxes are [x, y, w, h]."""
    if len(boxes) <= 1:
        return list(boxes)
    for axis in (1, 0):
        iv = sorted(((b[axis], b[axis] + b[axis + 2]) for b in boxes))
        end, cut = iv[0][1], None
        for s, e in iv[1:]:
            if s > end:
                cut = end
                break
            end = max(end, e)
        if cut is not None:
            a = [b for b in boxes if b[axis] + b[axis + 2] <= cut]
            return xycut(a) + xycut([b for b in boxes if b[axis] + b[axis + 2] > cut])
    # no clean cut (a headline or box crosses the column gaps): columns by left edge, then top to bottom
    span = max(b[0] + b[2] for b in boxes) - min(b[0] for b in boxes)
    xs = sorted(b[0] for b in boxes)
    starts = [xs[0]] + [x for p, x in zip(xs, xs[1:]) if x - p > 0.04 * span]
    col = lambda b: max(i for i, s in enumerate(starts) if s <= b[0])
    return sorted(boxes, key=lambda b: (col(b), b[1], b[0]))


def lines_from_surya(rec, W):
    """Surya boxes -> our line records: drop specks, rejoin contents rows split into cells, order."""
    boxes = [[x1, y1, x2 - x1, y2 - y1] for x1, y1, x2, y2 in rec["boxes"] if x2 > x1 and y2 > y1]
    if not boxes:
        return []
    med = float(np.median([b[3] for b in boxes]))
    boxes = [b for b in boxes if b[3] >= 0.4 * med and b[2] >= 0.6 * med]       # border ornaments, specks
    # rows: boxes sharing most of their height
    rows = []
    for b in sorted(boxes, key=lambda b: (b[1] + b[3] / 2, b[0])):
        cy = b[1] + b[3] / 2
        for r in rows:
            if abs(r["cy"] - cy) < 0.5 * med and all(o[0] + o[2] <= b[0] or b[0] + b[2] <= o[0] for o in r["boxes"]):
                r["boxes"].append(b)
                break
        else:
            rows.append({"cy": cy, "boxes": [b]})
    # a contents row cut into cells (number | title | page number): the same rule as detect_lines, a narrow
    # last cell ending on an aligned right edge on 3+ rows.  Rows of a multi-column page are not touched.
    xs0 = min(b[0] for b in boxes); tw = max(b[0] + b[2] for b in boxes) - xs0
    tails = []
    for i, r in enumerate(rows):
        r["boxes"].sort(key=lambda b: b[0])
        last = r["boxes"][-1]
        if len(r["boxes"]) > 1 and last[2] < 0.25 * tw and last[0] + last[2] - xs0 > 0.75 * tw:
            tails.append((i, last[0] + last[2]))
    merged = set()
    if len(tails) >= 3:
        edge = float(np.median([e for _, e in tails]))
        merged = {i for i, e in tails if abs(e - edge) < 0.04 * tw}
        if len(merged) < 3:
            merged = set()
    out = []
    for i, r in enumerate(rows):
        if i in merged:
            bs = r["boxes"]
            x0_ = min(b[0] for b in bs); y0_ = min(b[1] for b in bs)
            out.append([x0_, y0_, max(b[0] + b[2] for b in bs) - x0_, max(b[1] + b[3] for b in bs) - y0_])
        else:
            out.extend(r["boxes"])
    lines = []
    for bi, (x, y, w, h) in enumerate(xycut(out)):
        lines.append({"band": bi, "bbox": [int(x), int(y), int(w), int(h)], "baseline_y": int(y + 0.8 * h),
                      "pitch": med, "table_row": False})
    return lines


# --------------------------------------------------------------------------- tesseract
def tesseract_bin():
    for c in (os.environ.get("GPURA_TESSERACT"), shutil.which("tesseract"),
              r"C:\Program Files\Tesseract-OCR\tesseract.exe", "/usr/bin/tesseract", "/opt/homebrew/bin/tesseract"):
        if c and Path(c).exists():
            return c
    raise SystemExit("Tesseract not found: install it or set GPURA_TESSERACT")


def ocr_lines(img, lines, pid):
    """One Tesseract call per page on a strip of the detected line crops stacked vertically (psm 6).

    Every detected line gets a reading, which the page-level layout analysis does not guarantee."""
    cache = ROOT / "ocr" / f"{pid}.tess.tsv"
    pad = 30
    grey = img.convert("L")
    t = otsu(np.asarray(grey))
    grey = grey.point(lambda v: 255 if v > t else v)    # paper -> white, print keeps its grey levels
    crops = [grey.crop((x - 8, y - 8, x + w + 8, y + h + 8)) for x, y, w, h in (l["bbox"] for l in lines)]
    width = max((c.width for c in crops), default=1) + 2 * pad
    offs, y = [], pad
    for c in crops:
        offs.append(y)
        y += c.height + pad
    key_ = json.dumps([l["bbox"] for l in lines], default=int)
    if not cache.exists() or not cache.with_suffix(".key").exists() or cache.with_suffix(".key").read_text() != key_:
        # Tesseract cannot take an image taller than ~32k pixels (a newspaper page has 800+ lines), so the
        # stack is read in chunks of at most 20,000 pixels; word tops are shifted back to strip coordinates
        chunks, start = [], 0
        for k, (c, o) in enumerate(zip(crops, offs)):
            if o + c.height - offs[start] > 20000 and k > start:
                chunks.append((start, k)); start = k
        chunks.append((start, len(crops)))
        header, rows_out = None, []
        tmp = ROOT / "ocr" / f"{pid}.strip.png"
        for a, b in chunks:
            top = offs[a] - pad
            strip = Image.new("L", (width, offs[b - 1] + crops[b - 1].height + pad - top), 255)
            for c, o in zip(crops[a:b], offs[a:b]):
                strip.paste(c, (pad, o - top))
            strip.save(tmp)
            r = subprocess.run([tesseract_bin(), str(tmp), "stdout", "--tessdata-dir", TESSDATA, "-l", "mal+eng",
                                "--psm", "6", "-c", "tessedit_create_tsv=1"], capture_output=True, check=True)
            out = r.stdout.decode("utf-8").splitlines()
            if not out:
                continue
            header = header or out[0]
            cols = out[0].split("\t")
            ti = cols.index("top")
            for row in out[1:]:
                f = row.split("\t")
                if len(f) == len(cols):
                    f[ti] = str(int(f[ti]) + top)
                    rows_out.append("\t".join(f))
        tmp.unlink(missing_ok=True)
        cache.write_text((header or "") + "\n" + "\n".join(rows_out) + "\n", encoding="utf-8", newline="\n")
        cache.with_suffix(".key").write_text(key_)
    rows = csv.DictReader(io.StringIO(cache.read_text(encoding="utf-8")), delimiter="	", quoting=csv.QUOTE_NONE)
    words = [w for w in rows if w["level"] == "5" and w["text"].strip()]
    for l in lines:
        l["words"] = []
    for w in words:
        cy = int(w["top"]) + int(w["height"]) / 2
        for l, o, c in zip(lines, offs, crops):
            if o - pad / 2 <= cy < o + c.height + pad / 2:
                l["words"].append((int(w["left"]), w["text"], float(w["conf"])))
                break
    for l in lines:
        ws = sorted(l["words"])
        l["text_tesseract"] = " ".join(t for _, t, _ in ws)
        cs = [c for _, _, c in ws if c >= 0]
        l["conf"] = round(sum(cs) / len(cs) / 100, 3) if cs else None


# --------------------------------------------------------------------------- archive text
def archive_lines(n):
    """The page's existing text, one entry per printed line: Gpura's OCR, or where Gpura has none, the
    Sarvam Vision reading written by the sarvam stage (pipeline/fetch/sarvam_text.py)."""
    out, block = [], 0
    order = (("gpura", ROOT / "ocr" / f"gpura_existing_{n:04d}.txt"), ("sarvam", ROOT / "ocr" / f"sarvam_{n:04d}.txt"))
    if ITEM.get("text_source") == "sarvam":          # e.g. Gpura's text for this book has lost its line breaks
        order = order[::-1]
    for src, f in order:
        if not f.exists() or not f.read_text(encoding="utf-8").strip():
            continue
        for raw in f.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                block += 1
                continue
            out.append({"raw": raw.strip(), "text": encode(raw), "block": block, "src": src})
        return out
    return out


def align(lines, arch):
    """Monotone alignment of archive lines to detected lines; returns {line index: archive index}."""
    n, m = len(lines), len(arch)
    S = [[sim(l["text_tesseract"], g["text"]) for g in arch] for l in lines]
    best = np.zeros((n + 1, m + 1))
    move = np.zeros((n + 1, m + 1), dtype=np.int8)
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            c = []
            if i and j and S[i - 1][j - 1] >= MIN_SIM:
                c.append((best[i - 1][j - 1] + S[i - 1][j - 1] - MIN_SIM + 1, 1))
            if i:
                c.append((best[i - 1][j], 2))
            if j:
                c.append((best[i][j - 1], 3))
            best[i][j], move[i][j] = max(c)
    pairs, i, j = {}, n, m
    while i or j:
        mv = move[i][j]
        if mv == 1:
            pairs[i - 1] = (j - 1, S[i - 1][j - 1])
            i, j = i - 1, j - 1
        elif mv == 2:
            i -= 1
        else:
            j -= 1
    return pairs


def fill_gaps(lines, arch, pairs):
    """Between two matched lines (and before the first / after the last), if as many detected lines as
    source lines are left unmatched, pair them in order.  Tesseract reads some lines too badly to match
    (contents rows full of leader dots), but the order and the count still say which is which.  Such
    pairs keep their low similarity, so they are flagged as weak matches."""
    anchors = sorted(pairs.items())
    bounds = [(-1, -1)] + [(i, j) for i, (j, _) in anchors] + [(len(lines), len(arch))]
    filled = dict(pairs)
    for (i0, j0), (i1, j1) in zip(bounds, bounds[1:]):
        di = list(range(i0 + 1, i1)); dj = list(range(j0 + 1, j1))
        if not dj or not (0 <= len(di) - len(dj) <= 2):
            continue
        # every source line in the gap goes to one detected line, in order; up to two detected lines
        # (a column label, a rule) are left out, choosing the placement with the highest total similarity
        S = [[sim(lines[i]["text_tesseract"], arch[j]["text"]) for j in dj] for i in di]
        n, m = len(di), len(dj)
        f = [[-1e9] * (m + 1) for _ in range(n + 1)]
        f[0][0] = 0
        for a in range(1, n + 1):
            for b in range(0, min(a, m) + 1):
                f[a][b] = max(f[a - 1][b], f[a - 1][b - 1] + S[a - 1][b - 1] if b else -1e9)
        a, b = n, m
        while b:
            if f[a][b] == f[a - 1][b - 1] + S[a - 1][b - 1]:
                filled[di[a - 1]] = (dj[b - 1], S[a - 1][b - 1])
                b -= 1
            a -= 1
    return filled


def align_any_order(lines, arch):
    """Best one-to-one matches regardless of order, for pages whose reading order is uncertain
    (multi-column pages detected by Surya): pairs taken greedily, highest similarity first."""
    cand = sorted(((sim(l["text_tesseract"], g["text"]), i, j) for i, l in enumerate(lines) for j, g in enumerate(arch)),
                  reverse=True)
    pairs, used = {}, set()
    for s_, i, j in cand:
        if s_ < MIN_SIM + 15:                              # stricter than the ordered alignment: no order to lean on
            break
        if i not in pairs and j not in used:
            pairs[i] = (j, s_)
            used.add(j)
    return pairs


# --------------------------------------------------------------------------- hyphenation estimate
TOKEN = re.compile(r"[\u0d00-\u0d7f\u200c\u200d]+")
_LEX = None


def lexicon():
    """Word counts from the whole book's archive text, excluding line-initial/final tokens (often fragments)."""
    global _LEX
    if _LEX is None:
        _LEX = Counter()
        f = ROOT / "ocr" / "gpura_full.txt"
        src = f.read_text(encoding="utf-8") if f.exists() else "\n".join(
            p.read_text(encoding="utf-8") for p in (ROOT / "ocr").glob("gpura_existing_*.txt"))
        for line in src.splitlines():
            toks = TOKEN.findall(encode(line))
            _LEX.update(toks[1:-1])
    return _LEX


def word_split(a_line, b_line):
    """True if a_line's last word continues on b_line (the print uses no hyphen)."""
    if not a_line or not b_line or a_line.rstrip().endswith(END_PUNCT):
        return False
    ta, tb = TOKEN.findall(a_line), TOKEN.findall(b_line)
    if not ta or not tb or not a_line.rstrip()[-1:].strip() or not TOKEN.fullmatch(a_line.split()[-1]) or \
            not TOKEN.match(b_line.split()[0]):
        return False
    a, b = ta[-1], tb[0]
    if unicodedata.category(b[0]) in ("Mn", "Mc"):
        return True                                    # next line starts with a vowel sign: cannot start a word
    if len(b) > 2 and b[1] == "്" and b[0] == b[2]:
        return True                                    # starts with a doubled consonant (ന്ന, ട്ട ...)
    lex = lexicon()
    ca, cb, cj = lex[a], lex[b], lex[a + b]
    if cj and cj >= min(ca, cb):
        return True                                    # the joined word is at least as common as a half
    if ca or a.endswith(WORD_FINAL):
        return False                                   # the line ends on a known word or a word-final shape
    return len(a) <= 6                                 # a short piece that never occurs as a word: a fragment


# --------------------------------------------------------------------------- page -> lines.json
def build_page(pid, prev_tail, det):
    n = canvas_no(pid)
    img = Image.open(page_image(pid))
    W, H = img.size
    lines = det["lines"]
    ocr_lines(img, lines, pid)
    arch = archive_lines(n)
    surya = det["info"]["name"] == "surya"
    pairs = align_any_order(lines, arch) if surya else fill_gaps(lines, arch, align(lines, arch))

    kept = []
    for i, l in enumerate(lines):
        if i in pairs:
            j, s = pairs[i]
            l.update(text=arch[j]["text"], raw=arch[j]["raw"], block=arch[j]["block"], score=round(s, 1), arch=j,
                     src=arch[j]["src"])
            kept.append(l)
        elif (surya or (l["conf"] and (l["conf"] >= 0.6 or not arch))) and len(key(l["text_tesseract"])) >= 2:
            l.update(text=encode(l["text_tesseract"]), raw=None, block=None, score=None, arch=None)
            kept.append(l)                             # printed line Gpura's text lacks
    confs = sorted(l["conf"] or 0 for l in kept)      # the same lines the AI export measures
    non_text = None
    surya_text = det["info"]["name"] == "surya" and len(kept) >= 15   # Surya finds text, not texture
    if not arch and confs and confs[len(confs) // 2] < NON_TEXT_CONF and not surya_text:
        non_text = round(confs[len(confs) // 2], 2)   # cover, endpaper or plate: Tesseract reads only noise
        kept = []
    used = {pairs[i][0] for i in pairs}
    unplaced = [{"text": g["text"], "archive_line": j + 1, "source": g["src"]} for j, g in enumerate(arch) if j not in used]

    # regions: consecutive lines of one archive block, same column, no large vertical gap
    pitch = lines[0]["pitch"] if lines else 80
    body_w = max((l["bbox"][2] for l in kept), default=W)
    regions, cur = [], None
    for l in kept:
        x, y, w, h = l["bbox"]
        alone = sum(1 for o in kept if o["band"] == l["band"]) > 1
        prev = cur["lines"][-1]["bbox"] if cur else None
        new_column = det["info"]["name"] == "surya" and prev is not None and \
            (y < prev[1] or min(x + w, prev[0] + prev[2]) - max(x, prev[0]) < 0.5 * min(w, prev[2]))
        if cur is None or alone or cur["alone"] or new_column or l["block"] != cur["block"] or \
                y - (prev[1] + prev[3]) > 0.9 * pitch:
            cur = {"lines": [], "block": l["block"], "alone": alone}
            regions.append(cur)
        cur["lines"].append(l)

    out_regions = []
    for ri, r in enumerate(regions, 1):
        ls = r["lines"]
        xs = [l["bbox"][0] for l in ls]; ys = [l["bbox"][1] for l in ls]
        xe = [l["bbox"][0] + l["bbox"][2] for l in ls]; ye = [l["bbox"][1] + l["bbox"][3] for l in ls]
        bbox = [min(xs), min(ys), max(xe) - min(xs), max(ye) - min(ys)]
        txt = " ".join(l["text"] for l in ls)
        top, bottom = bbox[1] < 0.12 * H, bbox[1] > 0.88 * H
        if len(ls) == 1 and re.fullmatch(r"[\d൦-൯]{1,4}", key(txt) or "x") and (top or bottom):
            typ = "page-number"
        elif len(ls) == 1 and top and ri <= 2 and (r["alone"] or bbox[1] < 0.07 * H):
            typ = "header"
        elif len(ls) == 1 and bbox[2] < 0.7 * body_w and not txt.rstrip().endswith((".", ",")):
            typ = "heading"
        else:
            typ = "paragraph"
        rid = f"{pid}_r{ri:02d}"
        rec = {"id": rid, "type": typ, "production": "printed", "orientation": 0, "bbox": bbox,
               "polygon": [[bbox[0], bbox[1]], [bbox[0] + bbox[2], bbox[1]], [bbox[0] + bbox[2], bbox[1] + bbox[3]],
                           [bbox[0], bbox[1] + bbox[3]]], "reading_order": ri, "lines": []}
        for li, l in enumerate(ls, 1):
            x, y, w, h = l["bbox"]
            lid = f"{rid}_l{li:03d}"
            flags, ai = [], AI_READINGS.get(lid)
            if not ai or list(ai["bbox"]) != [int(x), int(y), int(w), int(h)]:
                ai = AI_BY_BOX.get((pid, (int(x), int(y), int(w), int(h))))
            if l["raw"] is None and ai and list(ai["bbox"]) == [int(x), int(y), int(w), int(h)]:
                if not ai["text"].strip():
                    continue                      # the model saw no text: a rule, border or speck, not a line
                l["text"] = encode(ai["text"])        # the box is unchanged, so the reading belongs to this line
                flags.append({"type": "unclear", "start": 0, "end": len(l["text"]), "cert": "medium",
                              "source": "ai", "note": ("Gpura has no text for this page; " if not arch else
                                       "No line in Sarvam's text for this page matches this printed line; " if arch[0]["src"] == "sarvam" else
                                                       "No line in Gpura's text matches this printed line; ") +
                              f"the reading was made by an AI model ({ai['model']}) from the line image. Not reviewed."})
            elif l["raw"] is None:
                flags.append({"type": "unclear", "start": 0, "end": len(l["text"]), "cert": "low",
                              "note": ("Gpura has no text for this page; " if not arch else
                                       "No line in Sarvam's text for this page matches this printed line; " if arch[0]["src"] == "sarvam" else
                                       "No line in Gpura's text matches this printed line; ") +
                                      "the reading is raw Tesseract output."})
            elif l["score"] < 60:
                flags.append({"type": "unclear", "start": 0, "end": len(l["text"]), "cert": "medium",
                              "note": f"Weak match between Gpura's line and the Tesseract reading of this line (similarity {l['score']})."})
            line = {"id": lid, "bbox": [x, y, w, h], "baseline": [[x, l["baseline_y"]], [x + w, l["baseline_y"]]],
                    "text_tesseract": l["text_tesseract"], "conf": l["conf"], "text": l["text"], "hyphen_end": False,
                    "flags": flags}
            if l.get("src") == "sarvam":
                line["source"] = "sarvam"                  # Gpura has no text here; Sarvam Vision's reading
            if l["raw"] and l["raw"] != l["text"]:
                line["text_archive"] = l["raw"]
            if l["score"] is not None:
                line["match"] = l["score"]
            if flags and flags[0].get("source") == "ai":
                line["source"], line["ai_model"] = "ai", ai["model"]
            rec["lines"].append(line)
        if rec["lines"]:
            out_regions.append(rec)

    # hyphenation: within the running text flow (paragraph lines, in order)
    flow = [l for r in out_regions if r["type"] in ("paragraph", "heading") for l in r["lines"]]
    for a_, b_ in zip(flow, flow[1:]):
        a_["hyphen_end"] = word_split(a_["text"], b_["text"])
    paras = [r for r in out_regions if r["type"] == "paragraph"]
    if prev_tail and paras:
        pr, pl = prev_tail
        if not pl["text"].rstrip().endswith(END_PUNCT):
            paras[0]["continues"] = pr["id"]
            pl["hyphen_end"] = word_split(pl["text"], paras[0]["lines"][0]["text"])
    tail = (paras[-1], paras[-1]["lines"][-1]) if paras else None

    data = {"page": pid, "canvas": n, "printed_page": next((r["lines"][0]["text"] for r in out_regions
                                                             if r["type"] == "page-number"), None),
            "width": W, "height": H, "automatic": True, "detector": det["info"],
            "regions": out_regions, "unplaced": unplaced,
            **({"non_text": f"No lines encoded: Gpura has no text for this page and Tesseract's median confidence "
                            f"is {non_text} (below {NON_TEXT_CONF}), so it is treated as a cover, endpaper or plate."}
               if non_text is not None else {}),
            "notes": [
                "AUTOMATIC, NOT REVIEWED. Coordinates are pixels in the full-resolution scan, origin top-left; bbox = [x, y, w, h].",
                ("Line boxes: Surya text-line detector (complex page: " + "; ".join(det["info"]["reasons"]) + "); "
                 "reading order by XY-cut. Baselines are estimated." if det["info"]["name"] == "surya" else
                 "Line boxes: projection profiles on dark, low-chroma pixels (coloured reader ink ignored). Baselines are estimated."),
                "text = Gpura's existing OCR line (or, where Gpura has none, Sarvam Vision's reading: source = sarvam), aligned to the detected line by fuzzy match against Tesseract (mal+eng, psm 6); "
                "text_archive keeps Gpura's original where the corpus encoding rules changed it; match = similarity 0-100.",
                "Encoding rules applied to Gpura's text: NFC; chillu+ZWJ and dot reph -> atomic chillus; NTA (ൻറ, ൻ്റ) -> ന്റ; TTA (ററ) -> റ്റ.",
                "hyphen_end is ESTIMATED from the book's own vocabulary (Gpura's full text) and Malayalam script rules; the print uses no hyphen.",
                "unplaced = Gpura text lines that matched no detected printed line: they may be mis-OCR, reader handwriting, or text that is not on the page.",
            ]}
    return data, tail


def main():
    pages = sys.argv[1:] or [page_id(n) for n in ITEM.get("canvases_encoded", [])]
    # detector: "auto" (default) uses ours and switches a page to Surya when it looks complex;
    # "ours" or "surya" forces one.  Set in item.json ("detector") or GPURA_DETECTOR.
    mode = os.environ.get("GPURA_DETECTOR") or ITEM.get("detector", "auto")
    reviewed = {pid for pid in pages if (ROOT / "ocr" / f"{pid}.lines.json").exists() and
                not json.loads((ROOT / "ocr" / f"{pid}.lines.json").read_text(encoding="utf-8")).get("automatic")}
    dets = {}
    for pid in pages:
        if pid in reviewed:
            continue
        lines, ink = detect_lines(Image.open(page_image(pid)))
        reasons = ["forced (detector = surya)"] if mode == "surya" else page_complexity(lines, ink) if mode == "auto" else []
        dets[pid] = {"lines": lines, "info": {"name": "projection-profiles"}, "reasons": reasons}
    complex_ = [pid for pid, d in dets.items() if d["reasons"]]
    if complex_:
        found = surya_boxes(complex_)
        missing = [pid for pid in complex_ if pid not in found]
        if missing:
            print(f"  surya not installed (bash pipeline/tools/setup_bench.sh surya): {len(missing)} complex page(s) "
                  f"keep the projection-profile lines: {', '.join(missing)}")
        for pid in complex_:
            d = dets[pid]
            if pid in found:
                d["lines"] = lines_from_surya(found[pid], Image.open(page_image(pid)).size[0])
                d["info"] = {"name": "surya", "version": found[pid]["surya"], "reasons": d["reasons"]}
            else:
                d["info"]["looks_complex"] = d["reasons"]
    tail, done = None, []
    for pid in pages:
        out = ROOT / "ocr" / f"{pid}.lines.json"
        if pid in reviewed:
            print(f"  {pid}: reviewed lines.json present, left untouched")
            tail = None
            continue
        data, tail = build_page(pid, tail, dets[pid])
        done.append((out, data))      # written at the end: the next page can still set this page's last hyphen_end
    for out, data in done:
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=int) + "\n", encoding="utf-8", newline="\n")
        pid = data["page"]
        nl = sum(len(r["lines"]) for r in data["regions"])
        na = sum(1 for r in data["regions"] for l in r["lines"] if l.get("source") == "ai")
        nt = sum(1 for r in data["regions"] for l in r["lines"] if "match" not in l) - na
        print(f"  {pid}: [{data['detector']['name']}] {len(data['regions'])} regions, {nl} lines ({nt} Tesseract-only, {na} AI), "
              f"{len(data['unplaced'])} archive lines unplaced")


if __name__ == "__main__":
    main()
