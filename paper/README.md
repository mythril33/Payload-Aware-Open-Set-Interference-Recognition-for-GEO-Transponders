# Complete manuscript V1

**Observable-Dependent Interference Detection: Measured GNSS Evidence and
Payload-Aware GEO Simulation** — 26 October 2026.

Read [manuscript.pdf](manuscript.pdf). Edit [manuscript.md](manuscript.md);
[manuscript.tex](manuscript.tex) is generated from it. This is a complete
approximately 5,300-word, 13-page first draft with abstract, introduction,
related work, datasets/rights, RF and detector methods, statistics, results,
interpretation, discussion, validity threats, conclusions, availability and
references. It is not submission approval. Author names are deliberately not
invented; the rendered anonymous author line is a publication blocker.

## Scope frozen for this draft

Three separate evidence streams: measured GNSS LC/FIOT; measured solid-state
PA input/output and their existing fits; controlled GEO simulation summaries.
All three previously fixed scores are reported on both native GNSS populations.
No primary scorer is selected from held-out outcomes. No new model, data,
recognition claim or numbered milestone is introduced. Publication category:
**reproducibility/comparative-methods paper or data/methods note**, subject to a
venue's novelty threshold. The evidence does not support a new-recognizer
article, confirmed C2/C3 advantage, measured GEO validation or executed
cross-dataset generalization.

The manuscript baseline is `7f58150bbcb674cb9985bcfa4ed56391f3b91c8a`;
PR44 and PR45 were independently confirmed merged. Source code, historical
results, protocols, approvals and compute gates are preserved. Actual detector
code/protocol commitment before metrics is `13f79f9ffc824029d91c74299cbfe83131ea4cc6`.

## Package and traceability

| Material | Purpose |
|---|---|
| `manuscript.md`, `.tex`, `.pdf` | Editable source, compilable generated TeX and complete rendered paper |
| `references.bib`, [literature_audit.md](literature_audit.md) | Fourteen primary citations; metadata/full-text/access limits and honest novelty assessment |
| `evidence.json`, `audit_evidence.py` | Twenty hashed source files, 206 exact JSON-pointer values, 29 claim groups; aggregate-only numerical audit |
| `figures/` | Four existing derived figures, PNG/PDF pairs copied byte-for-byte; original paths/source hashes in evidence manifest |
| `build.sh`, `preamble.tex` | Document rendering only, two LaTeX passes, no shell escape; no simulations, data downloads or fitting |

Claim IDs map to the paper as follows:

| Manuscript material | Manifest IDs and source |
|---|---|
| T1 and data coverage | `T1.*`, `M.acquisition_report`, `M.loader`; committed public-data report/JSON and native reader |
| T2 and T2b, all six rows | `T2.lc.*`, `T2.fiot.*`, `T2.protocol`, `T2.resources`; exact aggregate JSON pointers |
| Detector methods | `M.features`, `M.protocol_file`; pre-score baseline, feature order, fixed calibration/seed |
| T3 measured PA fits | `T3.apa`, `T3.dpa`, `M.P17_assumptions`, `methods.pa_normalization`; fitted artifact/P17/derivation source |
| T4 physical diagnostics | `T4.npr`, `.asi`, `.cuc`, `.cancellation`; distinct committed simulator summaries |
| S1 exploratory failures | `S1.*`; historical pilot count matrices/results or explicitly preserved Pilot A report |
| Historical B2 boundary | `M.P18_boundary`, `M.scientific_boundary`; frozen protocol and ratification register |

The verifier checks hashes and exact values, reconstructs all six AUROC/AP/FPR95
summaries from stored grouped ROC endpoints, checks rate/count/class arithmetic,
coverage, NPR slope, CuC medians, cancellation pairs, figure identities and exact
rounding/transcription of manuscript T2/T2b. It does **not** reconstruct raw
calibration order statistics, rerun bootstrap replicates, fit models or read
observations. Those thresholds/intervals remain traced to their committed results.
Hash equality establishes consistency with a source, not independent truth of it.

## Verify and build

From the repository root:

```sh
python paper/audit_evidence.py
sh paper/build.sh
git diff --check
```

The numerical audit uses only Python's standard library and committed summaries.
Rendering requires Pandoc with citeproc, pdfLaTeX, the common LaTeX extra/font
packages and `pdftotext` (Poppler). On Debian/Ubuntu these are `pandoc`,
`texlive-latex-extra`, `texlive-fonts-recommended`, `lmodern`, `poppler-utils`.
Pandoc resolves the bibliography into the generated TeX, so compiling that TeX
does not require a separate BibTeX run. Rendering from `paper/` can also use:

```sh
pdflatex -no-shell-escape -halt-on-error manuscript.tex
pdflatex -no-shell-escape -halt-on-error manuscript.tex
```

Prefer `build.sh`: intermediates stay in its temporary directory, overflow and
undefined-reference notices fail the build, and extracted PDF text must contain
all four figure captions and key concluding sections. Fixed PDF metadata dates
make the rendering date stable; they are not experiment timestamps. PDF bytes
need not match across TeX/font versions. Authoritative editing is in Markdown.
The paper-specific GitHub workflow audits and renders this package; it invokes
no scientific execution command or existing expensive B2 suite.

## Independent review and actual verification

Separate read-only model agents verified primary-source identity/novelty and
aggregate arithmetic; a further independent scientific reviewer compared the
manuscript against sources. One material finding was incomplete source binding
for methods/archive counts/hardware metadata. It was repaired by adding the
committed method/P17/source-audit/protocol identities; T3 explicitly attributes
hardware details to the preserved project audit. No human authorship, scientific
release or publication approval is implied.

Local verification executes the aggregate audit and two-pass rendering, checks
PDF text completeness and visually inspects result/physical-figure pages. An
initial rendering overflow clipped a figure/body continuation; it was corrected
before delivery, and the build now refuses overflow or missing content. A
source-text anchor in the added PA-normalization evidence was corrected to the
actual sum-of-squares expression before the final successful audit. No numerical
result or scientific source was altered. Final command timings/environment and
CI evidence are recorded in the delivery PR; earlier green PRs are not presented
as checks of the manuscript head. Full repository B2 tests were not rerun for
this paper-only change.

Final local commands (both exit0), measured with Python monotonic time and
`os.wait4` because GNU `time` is unavailable:

| Command | Wall / CPU | Child peak RSS |
|---|---|---|
| `python paper/audit_evidence.py` | 0.071 / 0.071 s | 13824 KiB |
| `sh paper/build.sh` | 7.814 / 7.556 s | 82048 KiB |

Peak RSS is the child's `wait4` value, not a sum of concurrent process memory.
Environment: Python3.12.14, Pandoc3.1.11.1, pdfTeX1.40.26 (TeX Live2025/dev),
Poppler25.03.0. The final build has no overflow or undefined-reference notices,
all four extracted figure captions/required sections are present, all14 cited
bibliography keys resolve and local package links pass. No pytest count is
invented for these documentation/arithmetic checks.

## Remaining publication blockers

1. **Rights:** clarify the Fraunhofer API/README CC BY-SA versus CC BY-NC-SA
   discrepancy for the intended derived publication; retain attribution and
   avoid raw-file redistribution. OpenDPD code licensing is not a new independent
   measurement-data license. This package does not relicense third-party data.
2. **Authorship and venue:** agree authors, affiliations, contributions and a
   reproducibility/comparative-methods venue. Primary-source checks do not prove
   priority or sufficient novelty for a new-method research article.
3. **Optional satellite comparison:** official SmartSpace files remain behind
   Microsoft sign-in. The [unsent request](../docs/plan/P8_dis_veri.md#smartspace-erişim-kararı-ve-hazır-talep--2026-10-26)
   asks for lawful access, native schema/label direction/group pairing and
   publication/processing terms. No metrics are fabricated. The scoped paper
   may omit this unavailable comparison rather than indefinitely postpone writing.
4. **Interpretation limits:** independent sessions, GNSS-to-GEO transfer, real
   satellite measurements and full C2/C3 confirmation are absent. They require
   new evidence and authorization if future authors choose those stronger claims;
   they are not secretly assumed by this draft.

No full B2 production, GPU discovery/training, LOKO, D-5 or protected held-out
evaluation occurred. `benchmark_complete=false`; current compute gates remain
closed. The next action is human manuscript/rights review, not a new architecture.
