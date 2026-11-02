#!/usr/bin/env bash
# Fetch Tesseract models (tessdata_best) for Malayalam and English into .cache/tessdata.
set -euo pipefail
cd "$(dirname "$0")/../.."
DEST=.cache/tessdata
BASE=https://github.com/tesseract-ocr/tessdata_best/raw/main
mkdir -p "$DEST/script"
for f in mal eng osd; do
  [ -s "$DEST/$f.traineddata" ] || curl -fsSL -o "$DEST/$f.traineddata" "$BASE/$f.traineddata"
done
[ -s "$DEST/script/Malayalam.traineddata" ] || curl -fsSL -o "$DEST/script/Malayalam.traineddata" "$BASE/script/Malayalam.traineddata"
cp "$DEST/script/Malayalam.traineddata" "$DEST/Malayalam.traineddata"
ls -l "$DEST" "$DEST/script"
