# Gpura Corpus

A proposal and working harness for a structured, standards-based text corpus of
[Gpura (ഗ്രന്ഥപ്പുര / Granthappura)](https://gpura.org), the Kerala digital archive.

**Site:** https://beniza.github.io/gpura-corpus/ — proposal (English and Malayalam), a walkthrough
of what the current transcription misses, a reviewed specimen, and automatic encodings of any Gpura book.

## The idea

For every item, keep three linked layers that share one set of IDs:

| Layer | Format | Records |
|---|---|---|
| Images | IIIF (already served by Gpura) | Page images, manifests |
| Layout | PAGE-XML 2019 (master), ALTO 4.4 (export) | Regions, lines, coordinates, reading order, printed vs handwritten |
| Edition | TEI P5 | Structure, metadata, reader annotations, damage, uncertainty, links back to the image |

## Running it on any Gpura book

```bash
pip install -r requirements.txt
bash pipeline/tools/fetch_models.sh          # Malayalam + English Tesseract models → .cache/tessdata
python3 run.py https://gpura.org/item/1957-sir-isaac-newton --pages 15-17
```

Give it a Gpura item link (or just the slug). Without `--pages` it encodes every page. It creates
`items/<slug>/`, runs every stage, validates the output and builds `docs/specimen/<slug>/`. Three pages
take about 40 seconds. Re-run an item already fetched with `python3 run.py items/<slug>`.

Needs Tesseract 5 on `PATH`, or set `GPURA_TESSERACT`. On Windows: `winget install UB-Mannheim.TesseractOCR`.

### What the automatic path does

1. **fetch**: reads the item from Gpura's Omeka S API (Dublin Core metadata) and its IIIF manifest
   (canvases, image service, Gpura's per-page OCR text, full-text rendering).
2. **align**: finds printed text lines by projection profiles on dark, grey pixels. Coloured reader ink
   (ballpoint underlining) is ignored, so it does not merge lines. One Tesseract pass reads the detected
   lines. Each line then gets **Gpura's own text**, aligned to it by fuzzy matching against the Tesseract
   reading. Gpura's OCR is far better than Tesseract on these books, so Tesseract is used only to
   decide which line is which. Anything that does not match is reported, not hidden:
   - a printed line Gpura's text lacks keeps the Tesseract reading, marked `<unclear cert="low">`;
   - a line of Gpura's text found nowhere on the page is listed as **unplaced**.
     This is how the specimen's invented footnote and misread handwriting surface automatically.
   - Words split across lines (the print uses no hyphen) are **estimated** from the book's own vocabulary.
3. **page**, **alto**, **tei**, **html**, **check**, **site**: as for the specimen (below).

**Measured** on the three specimen pages, scored against the reviewed inventory with `pipeline/tools/score_auto.py`:
- 90% of printed lines found (93% and 92% on the two text pages; the map page is not handled);
- 0.83% character error rate on those lines;
- word-split estimate agrees with the review on 55 of 62 lines.

On *നാരായണ വാമന തിലക്* (1950), viewer pages 20–22, 88 of Gpura's 89 text lines were placed (that test item is in the git history, commit 7adf224).

**Not handled yet:** multi-column pages, maps and illustrations, tables, and reader handwriting. Some
Gpura items have no OCR text; for those, every line is a Tesseract reading marked unclear unless the
optional AI step (below) is run, as for *സർ ഐസക്ക് ന്യൂട്ടൻ* (1957), viewer pages 15–17.

## Repository layout

```
run.py                     harness: link or item folder → all stages
pipeline/
  common.py                item.json, page list, IIIF URLs, timestamps (shared by every stage)
  fetch/gpura.py           Gpura API + IIIF manifest → item.json, images, Gpura's text
  align/auto_lines.py      line detection + alignment of Gpura's text → ocr/*.lines.json
  page/json2page.py        lines.json → PAGE-XML
  page/page2alto.py        PAGE-XML → ALTO (stock converters fail on these pages; see FORMAT_NOTES)
  tei/make_tei.py          lines.json → TEI P5 (any item)
  tei/custom/              hand-built TEI encoders for reviewed items (named in item.json "tei_builder")
  tei/tei2html.py          TEI → reading view
  tei/check_tei.py         link, text and flag checks on the TEI
  ocr/                     specimen research stages: Tesseract runs, CER comparison, review helpers
  tools/                   fetch_models.sh, build_tei_all.py, score_auto.py
schemas/                   PAGE 2019 XSD, ALTO 4.4 XSD, tei_all.rng (see schemas/SOURCES.md)
items/<item>/
  item.json                metadata, IIIF URLs, provenance wording; nothing item-specific lives in pipeline/
  images/                  page scans (not in git; run.py downloads missing ones from Gpura's IIIF service)
  ocr/*.lines.json         line inventory: the contract every later stage builds from
  page/  tei/              generated encodings
docs/                      GitHub Pages site (landing, proposal, walkthrough, specimens)
```

## The reviewed specimen

```bash
python3 run.py items/american-aikyanadu-1971                  # align skips reviewed pages; output is byte-identical
python3 run.py items/american-aikyanadu-1971 --stages ocr,compare  # re-run its OCR research
```

Its `lines.json` files were reviewed by reading each line against the image (a model, pending human
verification). They record handwriting, underlines, damage, map labels and uncertainty that the automatic
path does not. Its TEI is built by `pipeline/tei/custom/american_aikyanadu_1971.py`.

The `check` stage validates every PAGE file against the official PAGE 2019 XSD, every ALTO file against
ALTO 4.4, and the TEI against `tei_all.rng`. It then checks that every TEI pointer resolves, every line's
text matches the inventory, and every flag is encoded.

## Status

- Automatic encoding works on single-column Gpura books from their link.
- The reviewed specimen: viewer pages 17–19 of *അമേരിക്കൻ ഐക്യനാടിന്റെ ചരിത്രം* (1971).
  Its readings are model-made and **not yet human-verified**.
- No automatic reading has been checked by a person.

## Known issues

- **Contents pages and tables lose their structure.** Each row is kept as one line (a narrow, aligned
  right-hand column on three or more rows marks a table row), but the page is still encoded as headings
  and paragraphs, not as a table or contents list. Example: Newton, viewer p. 7. See `TODO.md`.
- AI readings are not reviewed; very short fragments can be misread (e.g. ന്യൂട്ടനും read as നൃത്തനം).
- Line detection occasionally merges two printed lines into one box.

The open work is listed in `TODO.md`.

## Encoding conventions

- Diplomatic transcription: wording and spelling as printed.
- The 1971 reformed script draws NTA as ൻറ and TTA as ററ. These are glyph shapes, encoded with the
  standard sequences ന്റ and റ്റ so the text is searchable.
- Samvruthokaram kept as printed (ഉണ്ടു്). Atomic chillus.
- Details: `items/*/tei/ENCODING_NOTES.md` and `items/*/page/FORMAT_NOTES.md`.

## Sources

Page images and archive text: Gpura (gpura.org), Indic Digital Archive Foundation. The items used are
in the public domain. This is an independent proposal, not a Gpura publication.

## Licence

- Code (`run.py`, `pipeline/`): MIT. See `LICENSE`.
- Data and encodings (`items/*/` transcriptions, PAGE, ALTO, TEI, `lines.json`) and the site text in
  `docs/`: CC0 1.0. See `LICENSE-data`.
- Vendored schemas in `schemas/` keep their own licences. Page images remain Gpura's and are public domain.

## Optional AI step: lines Gpura has no text for

Where Gpura has no text for a printed line, the automatic path falls back to Tesseract (about 13% of characters wrong on this book). The AI step replaces only those readings:

    python3 run.py items/<item> --stages ai-export        # numbered strips of the lines that need it -> <item>/ai/
    # a vision model reads <item>/ai/strips/ per <item>/ai/PROMPT.md and writes <item>/ai/readings.json
    GPURA_ITEM_DIR=items/<item> python3 pipeline/ai/import_readings.py --model "Claude Sonnet 5.5"
    python3 run.py items/<item>                           # rebuild; readings are kept in ocr/ai_readings.json

Each reading is tied to its line's box and used only while the box is unchanged. In TEI such a line is `<unclear cert="medium" reason="ai-reading" resp="#ai">`, with the model named in the header; PAGE-XML labels it the same way. On a 60-line test against Gpura's text (two pages of *നാരായണ വാമന തിലക്*), Claude Sonnet got 1.6% of characters wrong (Haiku 3.2%, Tesseract 12.7%). Very short fragments read badly without the rest of the line.

## Complex pages: Surya, switched on automatically

Our line detector reads a page as horizontal stripes of ink. That is fast and right for single-column
books, but newspapers, multi-column periodicals and pages with pictures defeat it. For those pages the
align stage switches to [Surya](https://github.com/datalab-to/surya)'s text-line detector:

    bash pipeline/tools/setup_bench.sh surya        # or surya-gpu: reuses an installed CUDA PyTorch

A page is sent to Surya when our detected lines are more than four character heights tall (lines glued
together by columns, pictures or ornament) or a vertical gap with text on both sides runs through the
text block. Contents rows that Surya cuts into cells are rejoined; reading order is by XY-cut. Each
page's `lines.json` records the detector and the reason (`"detector"`). Force a detector with
`"detector": "ours" | "surya"` in `item.json` or `GPURA_DETECTOR`. Without Surya installed, complex pages
keep our lines and the run says which pages they are. Benchmark: `pipeline/tools/bench_lines.py`; results
in `TODO.md`.

## Site: Showcase, PDF view and script style

- **Showcase** (navigation bar): one encoded page per layout type, listed in `docs/showcase.json`,
  followed by every book. Pages with no Gpura text are AI-read, so none shows raw OCR.
- **PDF view** (`docs/print.html`): A4 pages to print or save as PDF. `print.html?doc=paper` shows the
  paper; `print.html?item=<book>[&pages=7,15-17]` shows a book as a *layout facsimile* (each page
  re-typeset from its PAGE-XML coordinates, beside the scan) followed by a *reading edition* from TEI.
  Pagination by [Paged.js](https://pagedjs.org/).
- **Old script / New script** toggle (navigation bar and PDF view): the same Unicode text drawn in RIT
  Rachana (traditional orthography; passes all of Glyph-Sleuth's Malayalam shaping checks) or Noto Serif
  Malayalam (reformed orthography: detached ു/ൂ signs). RIT Rachana 1.5.2 is served from `docs/fonts/`
  under its OFL licence (`docs/fonts/rit-rachana/LICENSE.txt`).

## Text for pages Gpura has no text for: Sarvam Vision

    bash: echo SARVAM_API_KEY=... > .env           # once; .env is git-ignored
    python3 run.py items/<item> --stages sarvam,align,page,alto,tei,html,check,site

The `sarvam` stage sends each page with no Gpura text to Sarvam AI's Document AI *Parse* (Sarvam Vision)
and keeps the result (`ocr/sarvam_NNNN.json`, `.txt`). Its text is used exactly like Gpura's and is
labelled as Sarvam's in PAGE-XML and TEI. Sarvam's output matched Gpura's existing text character for
character on the pages compared, so the corpus stays consistent. About 0.50 credits (₹0.50) per page.
Reproduction benchmark: `python3 pipeline/tools/repro_bench.py` (cases in `pipeline/tools/repro_cases.json`).

## Dictionary pages: entries and their parts (TEI dictionaries module)

    GPURA_ITEM_DIR=items/<item> python3 pipeline/dict/entries_from_layout.py p300   # entries from hanging indent
    # an AI model labels each entry's parts -> dict/p300.segments.json (see the prompt in the commit history)
    GPURA_ITEM_DIR=items/<item> python3 pipeline/dict/make_dict_tei.py p300         # checked, validated TEI
    GPURA_ITEM_DIR=items/<item> python3 pipeline/dict/dict_html.py                  # colour-coded entry view

Every labelled part must be an exact, in-order piece of the printed text or the entry is kept unlabelled
(`<entryFree>`), so labelling can never change the text. Parts: headword, transliteration, etymology,
part of speech, sense number, gloss, example with its source, usage label, cross-reference (see / =),
derived words as nested entries. Example: Gundert's dictionary (1872), p. 264, in the Showcase.

## Sample corpus downloads

`python3 pipeline/tools/package.py` (also run by the `site` stage) writes `docs/downloads/<item>.zip` for
every book: README (contents, provenance of the text, licence, how to give feedback), `item.json`, TEI,
PAGE-XML and ALTO for every page, plain text in reading order, IIIF image links and the CC0 licence; and
`docs/downloads/gpura-corpus-sample.zip` with all of them. Linked from the Showcase and each book's page.
Feedback: GitHub issue form `.github/ISSUE_TEMPLATE/corpus-feedback.md`.

## Reading the corpus online

- `library/`: every book, with cover, extent, review status and Read / About / ZIP.
- `book/?b=<item>`: the book's home: catalogue details, contents (from the TEI headings; stamps and
  catalogue numbers left out), where its text comes from, validation, citation, downloads, feedback.
- `read/?b=<item>#pNNN`: the reader: the scan with its line boxes beside the page's text, line by line;
  hover either side to find the other; chapter and page menus, `[` `]` or arrow keys; a link to the page
  view (the encoding inspector) and to report a problem on the page. Loads one small file per page
  (`docs/specimen/<item>/data/pNNN.json`, written by the site stage with `book.json`).
