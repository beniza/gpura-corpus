# OCR comparison: p017–p019 (printed pp. 1–3)

**Reference.** All scores are measured against the reviewed `text` fields in `ocr/p0NN.lines.json`. That reference is a careful reading made by a model (Claude) from zoomed crops of the scans. **No human has verified it, so it is not ground truth.** Tesseract output and the existing Gpura text were both open as aids while the reading was made. This biases the comparison in favour of the existing text: wherever the reviewer accepted an existing reading that could not be settled from the image, an error shared by both would not be counted. Read the very low CER of the existing text as "agrees with the reviewed reading", not as "measured accuracy".

**Method.** The script is `ocr/compare.py`: `python3 ocr/compare.py --runs <run_ocr temp dir>`. It uses Levenshtein edit distance from rapidfuzz.
- CER = character edits / reference length. WER = word edits / reference word count, with words split on single spaces.
- **Body text** on p017/p018 means the paragraph and heading regions. Page numbers, the running head and handwriting are excluded. On p017 the existing text's first line `ഭൂപ്രകൃതി CMS` is kept because it is the heading, so the merged handwriting counts against it (4 characters).
- For Tesseract, only words whose box centre falls inside a body-line bbox are used, in Tesseract's own order.
- *Normalised* scores collapse whitespace and remove encoding-only differences on both sides:
  - NTA spelt as ൻറ, ൻ്റ, ന്‍റ, or in visual order as ൻെറ / നെറ becomes ന്റ(െ).
  - Bare ററ becomes റ്റ.
  - Chillu written with ZWJ becomes the atomic chillu.
  - Dot-reph U+0D4E becomes ർ.
  - ZWJ and ZWNJ are removed, and the text is NFC-normalised.
- *Raw* scores normalise whitespace only.

## Scores

| Page | Text compared | Hypothesis | CER norm. | WER norm. | CER raw | WER raw | ref chars |
|---|---|---|---:|---:|---:|---:|---:|
| p017 | body (2 paras + title) | Tesseract `mal+eng` psm 6 | 22.2 % | 52.8 % | 28.1 % | 65.0 % | 1731 |
| p017 | body | existing Gpura | 0.75 % | 3.9 % | 0.98 % | 5.0 % | 1731 |
| p018 | body (3 paras + section title) | Tesseract `mal+eng` psm 6 | 24.7 % | 56.6 % | 29.9 % | 72.0 % | 2087 |
| p018 | body | existing Gpura | 0.53 % | 3.6 % | 0.72 % | 4.5 % | 2087 |
| p019 | printed text (head, caption, legend, 2 labels) | Tesseract (psm 11 page + rotated crops) | 52.9 % | 81.3 % | 58.8 % | 93.8 % | 102 |
| p019 | printed text | existing Gpura | 80.4 % | 100 % | 81.4 % | 100 % | 102 |
| p019 | handwriting only | existing Gpura (`Freeman Doctrow Kennedy.`) | 20.0 % | 66.7 % | 20.0 % | 66.7 % | 25 |

**Running head on p018** (`p018_r02_l001`) is scored on its own:
- Tesseract: `അമേരിക്കന്‍ ഐക്യനാടിന്‍െറ ചരിത്രം`. CER is 0 % normalised and 16.7 % raw, so every difference is encoding.
- Existing: `ഐക്യനാടുകളുടെ`. CER is 16.7 % both ways, a real word substitution.

**Tesseract candidates** (normalised body CER) are below. The kept configuration is the one with the lowest CER. Mean word confidence, the script's original criterion, would have chosen `script/Malayalam` psm 3 for p017 and psm 6 for p018, which are worse.

| config | p017 | p018 |
|---|---:|---:|
| mal+eng psm3 | 29.2 % | 31.7 % |
| mal+eng psm4 | 25.8 % | 33.3 % |
| **mal+eng psm6** | **22.2 %** | **24.7 %** |
| script/Malayalam+eng psm3 | 28.0 % | 30.6 % |
| script/Malayalam+eng psm4 | 24.2 % | 31.9 % |
| script/Malayalam+eng psm6 | 22.8 % | 28.0 % |

Tesseract's errors are mostly of three kinds:
- **Lines lost.** Some lines are wholly missing from the page-level segmentation, mostly lines crossed by reader underlines or ink, though `p018_r06_l011` and `p018_r06_l014` are not (`p017_r04_l007`, `p017_r04_l009`, `p018_r06_l011`, `p018_r06_l014`), or reduced to fragments and Latin noise (`p018_r05_l002`, `p018_r06_l001` = `ee ee`, `p018_r06_l007`).
- **Broken u-sign.** The old-style u-sign is misread (ആളകളം for ആളുകളും), and so is samvruthokaram (`*`, `”`, `?` for ്).
- **Merged glyphs.** ൾ is read as ാം/ഠം (അംഗങ്ങാം).

On p019 the caption only became readable after rotating and binarising the crop (`അമേരിക്കന്‍ ഐക്യനാടിനെറ ഭൂപ്രകൃതി`). The legend gave nothing usable, and the page-level psm 11 pass produced only noise from the map hatching.

## Main discrepancies in the existing Gpura text (with line IDs)

| Line | Existing | Reviewed reading | Kind |
|---|---|---|---|
| `p018_r02_l001` (running head) | ഐക്യനാടുകളുടെ | ഐക്യനാടിന്റെ (printed ഐക്യനാടിൻറെ) | word substitution |
| `p017_r02_l001` + `p017_r05` | `ഭൂപ്രകൃതി CMS` | heading ഭൂപ്രകൃതി; CMS is blue-ink handwriting (separate marginalia region) | handwriting merged into print |
| p019 (whole page) | `Freeman Doctrow` / `പ്രകൃതി` / `Kennedy.` | `p019_r14` "Trueman Doctrine" (reader's hand, medium certainty), `p019_r01` printed head ഭൂപ്രകൃതി, `p019_r15` "Kennedy." | handwriting merged with print, ഭൂ dropped, handwriting misread |
| p019 "footnote" | പ്രസിദ്ധീകരണത്തിൻ്റെ ഭാഗമായ | **not on the page** | hallucination. The only other text-like marks are show-through from the reverse of the leaf |
| p019 | "This image contains a map with text labels in Malayalam script." | caption `p019_r04_l001`, legend `p019_r05`, labels `p019_r06…r13` | caption, legend and labels not transcribed; prose description instead |
| `p017_r03_l008` | യുണൈറഡ് | യുണൈറ്റഡ് (printed യുണൈററഡ്) | TTA dropped (real error) |
| `p017_r04_l011` | ഇറാലിയൻമാർ | ഇറ്റാലിയൻമാർ | TTA dropped |
| `p018_r04_l011` | ഇറാലിയൻറെയും | ഇറ്റാലിയനെയും | TTA dropped + wrong word ending |
| `p017_r04_l011` | ജർമ്മൻകാർ | ജർമൻകാർ | spelling normalised, not diplomatic |
| `p017_r04_l005` | വളച്ച | വളർച്ച (dot-reph) | reph dropped |
| `p018_r04_l008` | അവക്കു് | അവർക്കു് (dot-reph) | reph dropped |
| `p018_r06_l007` | കടൽതീരത്തിനും | കടൽതീരത്തിനു് | wrong ending |
| `p018_r06_l010` | ആസ്ട്രേലിയയുടെ | ആസ്ത്രേലിയയുടെ (medium certainty) | conjunct modernised/misread |
| `p017_r04_l004` | ബ്രിട്ടനെറതിനോടു് | ബ്രിട്ടന്റെതിനോടു് | encoding only (visual-order NTA); counted only in the raw score |
| `p017_r03_l006`, `p017_r03_l007`, `p018_r03_l001`, `p018_r04_l005`, `p018_r04_l012`, `p018_r06_l011` | തന്നെയാണ്; ഉദാഹരണത്തിന്; രണ്ട്; പാർപ്പ്; മാറ്റിയത്; മാത്രമാണ് | …ു് forms | samvruthokaram written as plain ് (modernised; the print has the u-sign). Several of these u-signs are faint and are flagged in the JSON. |
| p018 (several) | പട്ടണത്തിൻറെ, സെൻറു് (chillu + RRA) | ന്റ | encoding only |

The existing text also has the right line breaks and paragraphing, which made line-by-line alignment possible on p017 and p018.

## Caveats
- The reference reading has open uncertainties. Every `unclear` / `damage` flag in the JSON files marks one, for example 3554000 (a broken digit), കുരുപ്പിടിപ്പിച്ചതും, the first digit of the legend, and the handwriting.
- p019 scores rest on only 102 reference characters. Most map labels were not transcribed, so the p019 numbers say little.
- Underline and damage geometry comes from automatic detection plus checks by eye. It does not affect the CER figures.
