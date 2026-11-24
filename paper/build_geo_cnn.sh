#!/bin/sh
# Render the same manuscript source to an editable document and a PDF.
set -eu
cd "$(dirname "$0")"
python ../research/cpu_delivery/audit.py

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/geo-cnn-paper.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
export SOURCE_DATE_EPOCH=1795478400
export FORCE_SOURCE_DATE=1

pandoc geo_cnn_paper.md --standalone --fail-if-warnings \
  --output="$build_dir/geo_cnn_paper.docx"
pandoc geo_cnn_paper.md --standalone --fail-if-warnings \
  --include-in-header=preamble.tex --variable=geometry:margin=22mm \
  --variable=fontsize:10pt --variable=papersize:a4 --variable=colorlinks:true \
  --output="$build_dir/geo_cnn_paper.tex"

for pass in 1 2; do
  pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error \
    -file-line-error -output-directory="$build_dir" "$build_dir/geo_cnn_paper.tex" \
    > "$build_dir/console.log" 2>&1 || {
      cat "$build_dir/console.log"
      exit 1
    }
done
if grep -E 'Overfull|undefined references' "$build_dir/geo_cnn_paper.log"; then
  exit 1
fi

cp "$build_dir/geo_cnn_paper.docx" "$build_dir/geo_cnn_paper.pdf" .
echo "Built geo_cnn_paper.docx and geo_cnn_paper.pdf"
