# TODO

## Pipeline

- [ ] **Recognise contents pages and tables.** Detect pages where most rows end in a page number after
  leader dots, or where line segments form steady columns; encode them as a `TableRegion` in PAGE-XML
  and as `<list type="toc">` / `<table>` in TEI, with page numbers marked as such. For ambiguous pages,
  one AI call on the whole page image could classify the layout and map it onto the existing line IDs
  (about 2k tokens through the API). Needs examples from several books first. See Known issues in README.
- [ ] Batch-API script for the AI step (`run.py --ai sonnet`), for books with no Gpura text: about
  $0.02 per page, against ~12k plan tokens per page through Claude Code agents.
- [ ] Send very short line fragments to the AI step with surrounding context; alone they read badly.
- [ ] Line detection: two printed lines occasionally merge into one box (Newton p. 39).
- [ ] Smaller site images (`docs/specimen/*/pNNN.jpg`, up to 0.8 MB each): lower quality or WebP.
- [ ] Multi-column pages, maps, illustrations and reader handwriting (see README, "Not handled yet").

## Evaluate other tools (research, 3 Nov 2026)

Tesseract only matches Gpura's text to detected lines; replacing it would not change text quality. The
open questions are line/layout detection and text for books Gpura has no text for.

- [ ] **Line and layout detection benchmark** (`pipeline/tools/bench_lines.py`): our projection-profile
  detector vs **Kraken** (baseline segmentation, writes PAGE-XML, trainable on our reviewed pages) vs
  **Surya** (lines, layout incl. tables, reading order; claims 90+ languages). Pages with a known answer:
  the reviewed 1971 pages, the Newton contents page, ordinary text pages, and a multi-column page (still
  to choose). Score lines found (IoU ≥ 0.5), extra detections, and contents rows kept whole.
  - First run (3 Nov 2026; `bash pipeline/tools/setup_bench.sh`, then `python pipeline/tools/bench_lines.py`):

    | Detector | 1971 p. 17 (29) | 1971 p. 18 (38) | Newton contents (14 rows) | s/page (CPU) |
    |---|---|---|---|---|
    | ours | 29, 3 extra | 36, 1 extra | 14, 1 extra | < 1 |
    | Kraken 7.1 default model | 28, 0 extra | 34, 1 extra | 8, 19 extra, 4 split | 27–33 |
    | Surya detection | 28, 1 extra | 35, 3 extra | 7, 32 extra, 1 split | 15–72 |

    On body text all three are close. On the contents page Surya finds each **cell** (number, title, page
    number) as its own line, and Kraken mixes whole rows and cells. Surya's cells could feed table
    recognition, combined with our row grouping. Still to add: a multi-column page, Surya's layout model
    (table regions), and Kraken retrained on our reviewed pages.
- [ ] **Sarvam Vision** for books with no Gpura text: Indic document model (22 languages + English) with
  layout blocks, reading order and tables. Company-reported Malayalam word accuracy 91.6 vs Gemini 3 Pro
  87.1, Google Cloud Vision 88.3, Surya 83.8, Claude Opus 4.5 82.9 (Sarvam Indic OCR Bench). Test on pages
  that have Gpura text (score like the Sonnet test), then on Newton. Needs an API key; price unknown;
  hosted API: 10 pages per PDF, 10 requests a minute. Its text would replace Gpura's in the alignment step.
- [ ] OpenCV-style clean-up of our own detector (deskew, dewarp) if the benchmark shows tilt or curl losses.

## Technical paper: points to cover

The corpus and pipeline will be described in a technical paper. Challenges met so far:

- **Layout structure vs. line reading.** Contents pages and tables: the line detector cuts rows at wide
  gaps and the automatic region typing knows only page number, running head, heading and paragraph, so
  a contents page loses its table structure even when every line is read correctly. Rows are now kept
  whole (aligned narrow right-hand column on three or more rows); recognising the table itself is open.
- **Gpura's text vs. fresh OCR.** Gpura's existing OCR is far better than Tesseract on these books
  (0.5–0.8% vs 12–25% character error), so the pipeline aligns Gpura's text to detected lines rather
  than re-reading the page.
- **Books with no Gpura text.** AI reading of numbered line strips: Claude Sonnet 1.6% character error
  against Gpura's text on a 60-line test (Haiku 3.2%, Tesseract 12.7%). Cost per page through agents
  vs. the Batch API; non-text pages (covers, endpapers) skipped by Tesseract confidence.
- **Provenance.** Every reading says where it came from (Gpura, Tesseract or a named AI model) and how
  certain it is; AI readings are tied to a line's box and dropped if detection changes.
- **Script encoding.** Pre-reform and reformed glyph shapes (ൻറ, ററ, dot reph) encoded as standard
  Unicode sequences; samvruthokaram kept.
- **Tool comparison.** Results of the line-detection benchmark (ours vs Kraken vs Surya) and of Sarvam
  Vision vs Claude on Malayalam print, once run.
