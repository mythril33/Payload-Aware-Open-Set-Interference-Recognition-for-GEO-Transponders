#!/bin/sh
# Editable thesis/manuscript copies from the same sources as the PDFs.
# Document conversion only: no scientific execution or data access.
set -eu
cd "$(dirname "$0")"
python audit_evidence.py
python validate_geo_b2.py
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/geo-word.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
pandoc manuscript.md --from=markdown --standalone --citeproc --fail-if-warnings \
  --bibliography=references.bib --output="$build_dir/manuscript.docx"
pandoc geo_b2_manuscript.md --from=markdown --standalone --citeproc --fail-if-warnings \
  --bibliography=geo_b2_references.bib --output="$build_dir/geo_b2_manuscript.docx"
cp "$build_dir/manuscript.docx" manuscript.docx
cp "$build_dir/geo_b2_manuscript.docx" geo_b2_manuscript.docx
echo "Built editable Word drafts; review pagination in the target word processor."
