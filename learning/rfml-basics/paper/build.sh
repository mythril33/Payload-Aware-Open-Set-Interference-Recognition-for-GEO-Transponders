#!/bin/sh
# Build paper.pdf from the campaign aggregates. Rendering only: no training,
# no data generation, no network.
#
#   1. make_numbers.py   every number the text prints, from the aggregates
#   2. make_figures.py   every figure, from the per-seed result files
#   3. pdflatex + bibtex paper.tex
#
# The build fails on an unknown number key, an undefined reference or
# citation, an overfull box wider than 1 pt, or a missing section.
#
# Needs pdflatex, bibtex and pdftotext (Debian/Ubuntu: texlive-latex-base
# texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended
# texlive-publishers poppler-utils).
set -eu
cd "$(dirname "$0")"
PY="${PYTHON:-../.venv/bin/python}"

"$PY" make_numbers.py
"$PY" ../experiments/make_figures.py

run_latex() {
    pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -file-line-error paper.tex \
        > build.log 2>&1 || { tail -30 build.log; exit 1; }
}
run_latex
bibtex paper > bibtex.log 2>&1 || { cat bibtex.log; exit 1; }
run_latex
run_latex

if grep -E "LaTeX Warning: (Reference|Citation) .* undefined|There were undefined" paper.log; then
    echo "Refusing a build with undefined references or citations."
    exit 1
fi
if grep -E "^Overfull \\\\hbox \(([1-9][0-9]*\.[0-9]+|[0-9]{2,})pt" paper.log | grep -vE "\((0|1)\.[0-9]+pt"; then
    echo "Refusing a build with an overfull box wider than 1 pt."
    exit 1
fi
if grep -iE "warning--" bibtex.log; then
    echo "Refusing a build with BibTeX warnings."
    exit 1
fi

pdftotext -layout paper.pdf paper.txt
for required in "Abstract" "Introduction" "Related Work" "System Model" "Experimental Setup" \
    "Results" "Limitations" "Conclusion" "References"; do
    grep -Fq "$required" paper.txt || { echo "Missing section: $required"; exit 1; }
done
pages=$(pdfinfo paper.pdf | awk '/^Pages:/ {print $2}')
rm -f paper.txt paper.aux paper.blg paper.out paper.log build.log bibtex.log
echo "built paper.pdf (${pages} pages)"
