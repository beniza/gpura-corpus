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
