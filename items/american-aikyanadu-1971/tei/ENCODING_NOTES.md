# Encoding notes: american-aikyanadu-p017-019.tei.xml

TEI P5 encoding of printed pp. 1–3 (Gpura viewer pages 17–19) of *അമേരിക്കൻ ഐക്യനാടിന്റെ ചരിത്രം* (C.P. Hill, translated by Kuttanad K. Ramakrishna Pillai; State Institute of Languages, Trivandrum, 1971). This is a demonstration encoding, not a Gpura publication.

## Files
| file | role |
|---|---|
| `american-aikyanadu-p017-019.tei.xml` | the edition. It is generated, so do not hand-edit it. Re-run `make_tei.py` instead. |
| `make_tei.py` | builds the TEI from `ocr/p0NN.lines.json`, the contract. |
| `check_tei.py` | validation and contract checks (see below). |
| `tei2html.py` → `reading.html` | reading-HTML fragment. |
| `schema/tei_all.rng` | tei_all compiled locally from official TEI sources (see Validation). |

## Source and identity
- Readings (`text`), IDs and coordinates come verbatim from `lines.json`. `text_tesseract` is not used.
- Each lines.json region and line has a `<zone>` whose xml:id is exactly the contract ID (`p018_r03`, `p018_r03_l001`). Line zones are nested inside their region zone. `@type` is the region type, or `line` for lines. `@subtype` is `production`. Zones carry ulx/uly/lrx/lry from the bbox and `@points` from the polygon. Where a line has no polygon, `@points` is the bbox rectangle. Baselines are `<path type="baseline">`.
- `<surface xml:id="p017|p018|p019" n="17|18|19" corresp="…/canvas/NN">` holds `<graphic url="…__00NN.jpg/full/max/0/default.jpg" width="2374px" height="3495px">`. `@corresp` was chosen over `@sameAs` because a IIIF canvas is not a TEI element.

## Transcription
- Diplomatic transcription: spelling, abbreviations and spacing are as printed, with nothing modernised.
- NTA and TTA (1971 reformed glyphs ൻ+റ and റ+റ) are encoded as ന്റ and റ്റ. These are glyph conventions, not spelling. Chillus are atomic. Dot-reph is encoded as ർ (U+0D7C).
- Samvruthokaram is encoded as printed (ു്). It is never added or removed.
- Ditto marks in the legend are transcribed as `,,`.

## Structure
- `<pb n="printed page" facs="#p0NN"/>`, followed by `<fw type="pageNum|header" place=… facs="#region">`.
- Chapter `<div type="chapter">` with `<head>` ഭൂപ്രകൃതി. On p. 2, `<div type="section" n="1">` opens with a two-line `<head>`, and the section runs on through the p. 3 map.
- A paragraph that crosses a page points to both of its regions, e.g. `<p facs="#p017_r04 #p018_r03">`.

## Line breaks
- Every printed line, including those in fw, head, caption, legend items and labels, begins with `<lb facs="#lineID"/>`.
- `hyphen_end` on the previous line gives `<lb break="no"/>` with no whitespace before it.
- The cross-page split പതി|പ്പിച്ചിട്ടുണ്ടു് is encoded as `പതി<pb break="no"/><fw/><fw/><lb break="no"/>പ്പി…`. A consumer must treat `<fw>` as out of the text flow to rejoin the word.

## Reader marks (hands)
- Two handNotes in `msDesc/physDesc/handDesc`: `#blue-ink` and `#dark-ink`. They are distinguished by ink colour only, and attribution to one or more readers is unknown.
- **Underline:** `<hi rend="underline" hand="#…" facs="#graphic-zone">`. Spans are approximate (±1 word).
- **Ink-over:** `<hi rend="overdrawn" hand="#…">`. `@facs` points to the stroke zone only where the geometry finds a single candidate (3 of 4). For p018_r06_l006 no stroke zone was found, so that one has no `@facs`.
- **Overlapping spans:** underlines in the same line that overlap (p018_r04_l002, _l011, _l013; p018_r06_l006) are split into fragments `f-LINE-K-a`/`-b`, linked by `@next`/`@prev`. In each line the earlier span stays whole and the later one is split.
- **Handwritten notes:** `<note type="annotation" hand place facs="#region">`. These are CMS on p. 1, and Trueman Doctrine and Kennedy. on p. 3. Uncertain letters are in `<unclear cert>`, and Trueman is `cert="medium"`.
- **Circled numeral 1:** `<add hand="#blue-ink" place="inline" rend="circled">`, glued directly after ഒന്നാമതു്. Removing it restores the printed text exactly.
- **Coastline tracing:** a nested `<figure type="reader-mark" facs="#p019_r16" corresp="#blue-ink">`.
- **Stray marks** (p017_r07, p018_r08, p019_r17): zones plus `<note type="reader-mark" target="#zone">` in `<back>`.

## Uncertainty and damage
- `<unclear reason cert>`. Reason vocabulary:
  - `faint`
  - `damage`
  - `print-defect`
  - `glyph-form`: ambiguous print form or encoding decision, e.g. dot-reph or spelling-as-printed
  - `small-print`: map labels
  - `handwriting`

  `damage` is added when a damage flag overlaps.
- `<damage agent="crease|tear|stain" facs="#damage-zone" cert>`. The zone is found by bbox intersection.
- Every flag element has `xml:id="f-LINE-K"`, where K is the 1-based index of the flag in the line's `flags`. The review stage's note for each unclear, damage or ink-over flag is kept as `<back>//note[@target]`.

## Map page (p. 3)
- **Figure:** `<figure type="map" facs="#p019_r03" rendition="#rot-ccw90">` contains:
  - `<head type="caption">`
  - `<figDesc>` (English)
  - `<list type="legend">` with one `<item>` per line
  - `<label type="map-label">` per label region
- **Untranscribed labels:** `<label><lb/><gap reason="illegible"/></label>`, with no invented text. The OCR stage's tentative identifications ("probably Boston") appear only in `<back>` notes, which are explicitly marked as not being readings.
- **Rotation:** rotated zones have **`@rotate="270"`, not 90**. TEI `@rotate` is the zone's clockwise rotation relative to the surface. The OCR inventory's `orientation: 90` uses PAGE semantics (rotate 90° clockwise to read upright), so the text itself is rotated 270° clockwise, i.e. 90° anticlockwise. `tagsDecl/rendition#rot-ccw90` documents this.

## Validation (`python3 tei/check_tei.py`)
1. Well-formed.
2. RELAX NG valid against `schema/tei_all.rng`, using both lxml and jing (`pyjing`, from pip `jingtrang`).
3. All 266 `#` pointers resolve.
4. Every contract ID is a zone with identical points and rotate, nested correctly, and every region is referenced.
5. Each printed line's text, reassembled from the TEI, equals `lines.json` `text`.
6. `@break="no"` holds if and only if `hyphen_end`.
7. Each of the 59 non-empty flags is encoded, with exactly `text[start:end]`.

**Not validated:**
- No Schematron. The TEI ODD constraints are not checked; RELAX NG only.
- No check against Gpura's actual IIIF canvas and image URLs. They follow the given pattern and were not fetched.
- No human check of the readings.

**Schema provenance:** `tei_all.rng` was compiled here from TEIC/TEI branch `released` (P5 4.12.0, rev 113e933), using TEIC/Stylesheets 7.62.0a `odd2odd` and `odd2relax` under SaxonC-HE. tei-c.org and GitHub release downloads were blocked. It is the standard tei_all build path, but it is not the tei-c.org release artifact.
