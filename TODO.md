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

## Reproduction benchmark (pipeline/tools/repro_bench.py, repro_cases.json)

- [ ] Many-column pages (weekly, newspaper): text placement 43–76 %. Our line boxes (Surya) and Sarvam's
  lines disagree; use Sarvam's block coordinates and reading order for regions and columns.
- [ ] Sarvam sometimes reflows a paragraph into one long line (English picture page, back cover): split it
  over the detected lines, or fall back to the AI step for those lines.
- [ ] Sarvam invents text on blank lower halves of pages (show-through); the pipeline already keeps it out
  (unplaced). Exclude unplaced Sarvam blocks from the benchmark reference, or flag them as suspect.
- [ ] Contents pages where Tesseract cannot read the rows (Narayana p. 14): place the source lines by order
  and geometry instead of by Tesseract similarity.
- [ ] Title pages with large display type: ink coverage 58 %.

## Site

- [ ] **Edit in the Reading (from TEI) view** (deferred, 3 Nov 2026): correct a line in the browser and
  export the corrections as a file the pipeline imports as reviewed readings with the reviewer's name.
  A shared online database (several reviewers at once) would need a hosted service.
- [ ] PDF view: the reading edition is left out when a page selection is given (`print.html?...&pages=`);
  slice the TEI reading text by page instead.
- [ ] PDF view of a whole long book is slow to lay out in the browser (Paged.js); offer per-chapter ranges.

## Evaluate other tools (research, 3 Nov 2026)

Tesseract only matches Gpura's text to detected lines; replacing it would not change text quality. The
open questions are line/layout detection and text for books Gpura has no text for.

- [x] **Line and layout detection benchmark** (`pipeline/tools/bench_lines.py`, `bench_overlay.py`):
  our projection-profile detector vs **Kraken** 7.1 (default model) vs **Surya** 0.23 on 17 pages: the
  reviewed 1971 pages (scored), and newspapers, a two/four-column weekly, pictures, contents pages and
  ruled tables (judged from side-by-side overlays).

  | Page type | ours | Kraken | Surya |
  |---|---|---|---|
  | Plain prose (scored, 67 lines) | 65 found | 62 | 63 |
  | Newspaper (3) | fails: bands across all columns | partial, misses small print | **good** |
  | Multi-column weekly (3) | fails / lines cross the gap | partial | **good** |
  | Pictures (3) | fails: lines through pictures | good | **good** |
  | Contents (4) | **rows whole on 3**, fails on a bordered cover | rows broken | rows whole only with dotted leaders, else cells |
  | Ruled tables (2) | cells merged across columns | one box per cell | one box per cell |

  Speed: ours < 1 s/page; Surya ~6 s/page plus ~10 s start-up (Surya 0.23 barely uses the GPU: its time is
  pre- and post-processing); Kraken ~30 s/page. Kraken's default model is not worth adding.
- [x] **Surya in the pipeline, switched on automatically** for complex pages (`auto_lines.py`
  `page_complexity`): a page goes to Surya when our detected lines are over 4 character heights tall
  (glued by columns, pictures or ornament) or a vertical gap with text on both sides runs through the text
  block. On 62 test pages it sent every newspaper, column, picture and decorated page to Surya and kept
  every plain text and contents page (except one dotted-leader contents page, which Surya handles well).
  Surya cells in contents rows are rejoined into rows; reading order by XY-cut with a column fallback.
  `detector` in item.json or `GPURA_DETECTOR` = auto | ours | surya.
- [ ] Multi-column reading order and regions: on a four-column weekly page some Surya lines bridge a
  narrow column gap, so a few regions span columns. Needs a column/region step (Surya's layout model).
- [ ] Ruled-table pages are not flagged as complex (our detector merges their cells across columns).
- [ ] Hand-checked answers for 2–3 complex pages (newspaper, table, picture) so the comparison is scored.
- [x] **Sarvam Vision** for books with no Gpura text (done 3 Nov 2026: `sarvam` stage; output identical to
  Gpura's own text; whole Newton book encoded with it; see the paper, sections 6.5–6.6). Original note:: Indic document model (22 languages + English) with
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
- **Tool comparison.** Line detection on 17 pages of six types (ours vs Kraken vs Surya; see above) and the
  automatic switch to Surya for complex pages; Sarvam Vision vs Claude on Malayalam print still to run.
