#!/usr/bin/env bash
# Fetch Tesseract models (tessdata_best) for Malayalam and English into .cache/tessdata.
set -euo pipefail
cd "$(dirname "$0")/../.."
DEST=.cache/tessdata
mkdir -p "$DEST/script"
TMP=$(mktemp -d)
git clone -q --depth 1 --filter=blob:none --sparse https://github.com/tesseract-ocr/tessdata_best "$TMP/tdb"
git -C "$TMP/tdb" sparse-checkout set --no-cone /mal.traineddata /eng.traineddata /osd.traineddata /script/Malayalam.traineddata
cp "$TMP/tdb/mal.traineddata" "$TMP/tdb/eng.traineddata" "$TMP/tdb/osd.traineddata" "$DEST/"
cp "$TMP/tdb/script/Malayalam.traineddata" "$DEST/script/"
cp "$TMP/tdb/script/Malayalam.traineddata" "$DEST/"
rm -rf "$TMP"
ls -l "$DEST" "$DEST/script"
