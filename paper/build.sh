#!/bin/sh
# Documentation rendering only. No data, model, simulator or network calls.
set -eu
cd "$(dirname "$0")"
export SOURCE_DATE_EPOCH=1792972800
export FORCE_SOURCE_DATE=1
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/geo-manuscript.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
pandoc manuscript.md --from=markdown --standalone --citeproc --fail-if-warnings \
  --bibliography=references.bib --include-in-header=preamble.tex \
  --variable=geometry:margin=22mm --variable=fontsize:10pt \
  --variable=colorlinks:true --variable=link-citations:true \
  --output="$build_dir/manuscript.tex"
for pass in 1 2; do
  pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error \
    -file-line-error -output-directory="$build_dir" "$build_dir/manuscript.tex" \
    > "$build_dir/console.log" 2>&1 || {
      cat "$build_dir/console.log"
      exit 1
    }
done
if grep -E 'Overfull|undefined' "$build_dir/manuscript.log"; then
  echo "Refusing a draft with overflow or undefined references."
  exit 1
fi
pdftotext -layout "$build_dir/manuscript.pdf" "$build_dir/manuscript.txt"
for required in 'Figure 1:' 'Figure 2:' 'Figure 3:' 'Figure 4:' \
  'Physical interpretation and representation limits' 'Threats to validity' \
  'Conclusions' 'References' 'Reproducibility and data availability'; do
  grep -Fq "$required" "$build_dir/manuscript.txt" || {
    echo "Missing rendered content: $required"
    exit 1
  }
done
cp "$build_dir/manuscript.tex" manuscript.tex
cp "$build_dir/manuscript.pdf" manuscript.pdf
echo "Built paper/manuscript.tex and paper/manuscript.pdf (two LaTeX passes)."
