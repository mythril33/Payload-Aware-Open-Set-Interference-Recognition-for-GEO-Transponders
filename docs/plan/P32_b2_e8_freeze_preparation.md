# P32 — E8 scientific-protocol freeze preparation and production resource readiness

Date: 2026-10-24. Base `main` `4a1cc95913b430fee5c5e7d2e54cf48c9feeb8d8`. `benchmark_complete=false`. This is a preparation contract: it grants no
authorization, edits no frozen protocol (P18-P22, P28, P31 are untouched), changes no gate, and adds no file under `src/` or `configs/` (a new `src` file
would change every checkpoint provenance and the production lock, P29 section 1).

## 1. Deliverables (all additive)

| Deliverable | File |
|---|---|
| Decision-approval document (matrix, recommended primary protocol, templates) | [B2_E8_DECISION_APPROVAL.md](B2_E8_DECISION_APPROVAL.md) |
| Candidate production configuration (UNAPPROVED, non-loadable, outside `configs/`) | [b2_e8_candidate_production_config.json](b2_e8_candidate_production_config.json) |
| Host/resource assessment and width-explicit arithmetic | [B2_E8_HOST_RESOURCE_ASSESSMENT.md](B2_E8_HOST_RESOURCE_ASSESSMENT.md), `scripts/b2_e8_budget.py`, [b2_e8_resource_budget.json](../results/b2_e8_resource_budget.json) |
| Read-only hardware/environment inventory | `scripts/b2_host_inventory.py`; sandbox evidence `docs/results/b2_e8_host_inventory_sandbox_{generation,training}.json` |
| Exact bounded GPU-probe specification (executor not implemented) | [b2_e8_gpu_probe_spec.json](b2_e8_gpu_probe_spec.json) |
| Updated readiness checklist | [B2_E6_PRODUCTION_READINESS_CHECKLIST.md](B2_E6_PRODUCTION_READINESS_CHECKLIST.md) (regenerated from [b2_e6_audit_findings.json](b2_e6_audit_findings.json)) |
| Go/no-go report and the exact commands | [B2_E8_GO_NO_GO.md](B2_E8_GO_NO_GO.md) |
| Tests | `tests/test_b2_e8_tools.py` |

## 2. Rules the work follows

1. Recommendation is not decision: every researcher-controlled value stays `UNAPPROVED`; the gates JSON `decisions` object and every `approval` field are unchanged.
2. No test-informed choice: no test, test-only, matched or val-calib outcome was read; recommendations follow P18/P20/P6 and committed analytic or fixture evidence.
3. No GPU computation, no data generation, no fit, no LOKO. The inventory runs at most one fixed `nvidia-smi --query-gpu` driver query and imports neither torch nor CUDA.
4. Widths are never mixed: the E5 6 GPU-h figure belongs to width 8 and is withdrawn for width 16 (assessment section 1).
5. Records are reconciled, not rewritten: the PR #24 CI (run 40064513568, 1771 passed, 7 skipped) is entered in the gates JSON and the findings; earlier records keep their text and gain a `superseded_by` pointer.

## 3. Change control

No P18 section 10 entry: E8 changes no semantics, version, seed, label, count, request layout or hyperparameter. A future approval of a value that departs
from the P6 / `TrainConfig` / P20 defaults needs the prior section 10 entry and version name before the first fit (list in the candidate config).
Any later edit under `src/` (for example the executor milestone) creates a new lock and invalidates every earlier checkpoint identity.
