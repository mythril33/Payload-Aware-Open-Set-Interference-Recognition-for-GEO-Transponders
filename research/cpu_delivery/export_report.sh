#!/bin/sh
# Export the audited CPU results; no simulations or fitting.
set -eu
cd "$(dirname "$0")/../.."
python research/cpu_delivery/audit.py
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/geo-cpu-report.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
export XDG_CACHE_HOME="$build_dir/cache"
mkdir -p "$XDG_CACHE_HOME"
cpu_report_source=docs/results/CPU_DELIVERY_2026-11-04.md
pandoc "$cpu_report_source" --standalone --fail-if-warnings --resource-path=docs/results \
  --output="$build_dir/report.docx"
pandoc "$cpu_report_source" --standalone --fail-if-warnings --resource-path=docs/results \
  --pdf-engine=xelatex --pdf-engine-opt=-no-shell-escape --variable='mainfont:DejaVu Sans' \
  --variable='monofont:DejaVu Sans Mono' --variable=geometry:margin=20mm \
  --variable=fontsize:10pt --output="$build_dir/report.pdf"
cp "$build_dir/report.docx" docs/results/CPU_DELIVERY_2026-11-04.docx
cp "$build_dir/report.pdf" docs/results/CPU_DELIVERY_2026-11-04.pdf
echo "Built the CPU experiment report in PDF and Word."
