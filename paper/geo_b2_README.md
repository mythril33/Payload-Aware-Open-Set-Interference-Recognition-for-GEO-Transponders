# Separate GEO experimental manuscript

Read/edit [geo_b2_manuscript.md](geo_b2_manuscript.md); read the typeset
[PDF](geo_b2_manuscript.pdf). The original `manuscript.*`, its bibliography and
the independent literature review are preserved.

This draft contains the physical system, recognition and calibration methods,
separate H1/H2/H3 comparisons, existing simulated diagnostics, and validity
limitations. Production recognition results are **NOT RUN**. Mahalanobis is
recommended, not researcher-designated. No production, training, GPU or protected
observation access is needed to render or validate the manuscript.

- [Bibliography](geo_b2_references.bib): fifteen cited primary references.
- [Literature verification](geo_b2_literature_sources.md): metadata/full-text
  access limits and bounded interpretations.
- [Evidence-to-claim map](geo_b2_evidence.md) and
  [machine-readable evidence](geo_b2_evidence.json): eighteen claim groups,
  source hashes, numeric aggregate pointers and figure identity.
- [Publication display specifications](geo_b2_display_specs.md): exact populations,
  denominators, table/figure layouts and unexecuted measurement labels.
- Manuscript §7.3: minimum experiments needed to complete Results and Discussion;
  this list supplies no execution authorization.

## Validate and build

From the repository root, using Python 3.12, Pandoc with citeproc, pdfLaTeX
(`texlive-latex-extra`, `texlive-fonts-recommended`, `lmodern`) and `poppler-utils`:

```sh
python paper/validate_geo_b2.py
python paper/audit_evidence.py
sh paper/build_geo_b2.sh
```

The first command checks only committed documents, scientific source text,
aggregate summaries and derived images; it does not import scientific kernels.
The second preserves validation of the original paper. The new build uses two
LaTeX passes, disables shell escape and rejects rendering overflow or undefined
references. It updates only `geo_b2_manuscript.tex` and `geo_b2_manuscript.pdf`.
The manuscript CI validates and renders both papers independently. Fixed PDF
metadata dates support reproducible rendering; they are not experiment dates.

The Markdown is the editable source. If a cited source changes, review its
scientific effect before updating the corresponding evidence hash. Hash
agreement proves byte consistency, not scientific validity or human approval.
