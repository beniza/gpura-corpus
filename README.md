# Gpura Corpus

A proposal and working harness for a structured, standards-based text corpus of
[Gpura (ഗ്രന്ഥപ്പുര / Granthappura)](https://gpura.org), the Kerala digital archive.

**Site:** https://beniza.github.io/gpura-corpus/ — proposal (English and Malayalam), a walkthrough
of what the current transcription misses, and a working specimen of three pages encoded end to end.

## The idea

For every item, keep three linked layers that share one set of IDs:

| Layer | Format | Records |
|---|---|---|
| Images | IIIF (already served by Gpura) | Page images, manifests |
| Layout | PAGE-XML 2019 (master), ALTO 4.4 (export) | Regions, lines, coordinates, reading order, printed vs handwritten |
| Edition | TEI P5 | Structure, metadata, reader annotations, damage, uncertainty, links back to the image |

## Repository layout

```
run.py                     harness: runs the pipeline for one item
pipeline/
  ocr/run_ocr.py           Tesseract (mal+eng) → hOCR / ALTO / TSV
  ocr/compare.py           CER/WER of Tesseract and the archive's text vs the reviewed reading
  ocr/review/              helper scripts used to build the reviewed line inventory
  page/json2page.py        lines.json → PAGE-XML
  page/page2alto.py        PAGE-XML → ALTO (stock converters fail on these pages; see FORMAT_NOTES)
  tei/make_tei.py          lines.json → TEI P5
  tei/tei2html.py          TEI → reading view
  tei/check_tei.py         link, text and flag checks on the TEI
  tools/                   build_tei_all.py (compile tei_all.rng from TEI sources), fetch_models.sh
schemas/                   PAGE 2019 XSD, ALTO 4.4 XSD, tei_all.rng (see schemas/SOURCES.md)
items/<item>/
  item.json                bibliographic and IIIF metadata
  images/                  full-resolution page scans
  ocr/*.lines.json         reviewed line inventory: the contract every later stage builds from
  page/  tei/              generated encodings
  site/findings.html       item-specific notes shown on the specimen page
docs/                      GitHub Pages site (landing, proposal, walkthrough, specimen)
```

## Running it

```bash
pip install -r requirements.txt
python3 run.py items/american-aikyanadu-1971            # page → alto → tei → html → check → site
python3 run.py items/american-aikyanadu-1971 --stages all   # also re-runs OCR and the comparison
```

OCR needs Tesseract 5 and the Malayalam models: `bash pipeline/tools/fetch_models.sh` puts them in
`.cache/tessdata` (the harness looks there, or wherever `GPURA_TESSDATA` points).

The `check` stage validates every PAGE file against the official PAGE 2019 XSD, every ALTO file against
ALTO 4.4, and the TEI against `tei_all.rng`, then checks that every TEI pointer resolves, every line's
text matches the reviewed inventory, and every flag is encoded.

## The pipeline, stage by stage

1. **ocr** — Tesseract on each page image.
2. **compare** — error rates against the reviewed reading.
3. **review** — not automated. A person (here, a model, pending human verification) reads each line
   against the image and writes `ocr/*.lines.json`: region and line IDs, coordinates, reviewed text,
   and flags for underlines, damage, uncertainty and reader hands. Everything after this is generated.
4. **page**, **alto**, **tei**, **html** — encodings built from `lines.json`.
5. **check** — schema validation and cross-checks.
6. **site** — rebuilds `docs/specimen/<item>/`.

## Status

- One item so far: viewer pages 17–19 of *അമേരിക്കൻ ഐക്യനാടിന്റെ ചരിത്രം* (1971).
- All readings are model-made and **not yet human-verified**.
- Some generators still contain item-specific details (TEI header metadata, page lists). Moving these
  into `item.json` is the next step towards running the harness on any Gpura item.

## Encoding conventions

- Diplomatic transcription: wording and spelling as printed.
- The 1971 reformed script draws NTA as ൻറ and TTA as ററ. These are glyph shapes, encoded with the
  standard sequences ന്റ and റ്റ so the text is searchable.
- Samvruthokaram kept as printed (ഉണ്ടു്). Atomic chillus.
- Details: `items/*/tei/ENCODING_NOTES.md` and `items/*/page/FORMAT_NOTES.md`.

## Sources

Page images and archive text: Gpura (gpura.org), Indic Digital Archive Foundation. The items used are
in the public domain. This is an independent proposal, not a Gpura publication.
