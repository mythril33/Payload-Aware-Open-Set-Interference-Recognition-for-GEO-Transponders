#!/bin/sh
# GEO manuscript rendering only; preserves the existing manuscript package.
set -eu
cd "$(dirname "$0")"
export SOURCE_DATE_EPOCH=1793059200
export FORCE_SOURCE_DATE=1
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/geo-b2-paper.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
pandoc geo_b2_manuscript.md --from=markdown --standalone --citeproc --fail-if-warnings \
  --bibliography=geo_b2_references.bib --include-in-header=preamble.tex \
  --include-in-header=geo_b2_preamble.tex \
  --variable=geometry:margin=22mm --variable=fontsize:10pt \
  --variable=colorlinks:true --variable=link-citations:true \
  --output="$build_dir/geo_b2_manuscript.tex"
for pass in 1 2; do
  pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error \
    -file-line-error -output-directory="$build_dir" "$build_dir/geo_b2_manuscript.tex" \
    > "$build_dir/console.log" 2>&1 || {
      cat "$build_dir/console.log"
      exit 1
    }
done
if grep -E 'Overfull|undefined' "$build_dir/geo_b2_manuscript.log"; then
  echo "Refusing GEO PDF with overflow or undefined references."
  exit 1
fi
pdftotext -layout "$build_dir/geo_b2_manuscript.pdf" "$build_dir/paper.txt"
for required in 'Figure 1:' 'Figure 2:' 'NOT RUN' 'NOT DESIGNATED' \
  'Threats to Validity' 'Reproducibility' 'References' 'Conclusion'; do
  grep -Fq "$required" "$build_dir/paper.txt" || {
    echo "Missing rendered GEO content: $required"
    exit 1
  }
done
cp "$build_dir/geo_b2_manuscript.tex" geo_b2_manuscript.tex
cp "$build_dir/geo_b2_manuscript.pdf" geo_b2_manuscript.pdf
echo "Built separate GEO manuscript TeX/PDF (two LaTeX passes)."
