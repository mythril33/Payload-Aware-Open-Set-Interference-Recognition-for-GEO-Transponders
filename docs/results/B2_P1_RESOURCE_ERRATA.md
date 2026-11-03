# P1 / M-11 — resource-arithmetic clarification (non-authoritative estimate)

Date: 2026-11-03. Baseline main `8aa6645718def6c49ca6ae6653bbb2cf2cb91b16`. **No production-resource budget, GPU qualification, compute gate or scientifically approved record is changed.**

The canonical E9 scientific-approval JSON at `docs/plan/b2_e9_approved_scientific_protocol.json`, line 430, records an **estimated** 7.0 hours for nine fits and mistakenly describes it as "roughly 1.9x" a 6 GPU-hour reservation. The arithmetic is:

| Quantity | Arithmetic | Interpretation |
| --- | --- | --- |
| E9 point estimate vs 6 h | 7.0 / 6.0 = **1.1667×** (about **1.17×**) | Correct value for the 7.0 h point estimate |
| Earlier upper bound vs 6 h | 11.5 / 6.0 = **1.9167×** (about **1.9×**) | The 1.9× phrase applies only to the earlier 11.5 h upper estimate |
| Difference of point estimate vs reservation | 7.0 − 6.0 = **1.0 h** | Arithmetic difference, not a validated GPU shortfall |

**Uncertainty:** 5.88, 6.8–10.4, 7.0, 7.9–11.5 and 10–22 h originate from different stages, widths, assumptions and measurement scopes. They must not be treated as interchangeable measured GPU fit durations. In particular, a CPU/preprocessing timing extrapolation is not a qualified width-16 GPU training measurement. A fresh host- and recipe-specific resource profile is still required before any compute approval.

**Immutable evidence rule:** The existing approved JSON remains unchanged, so its recorded identity and historical approval are not silently rewritten. This document is a dated **erratum** to the arithmetic and the interpretation of the phrase, not a replacement for the source record.

See also `docs/research/B2_E10_CRITICAL_FINDINGS_CLOSURE.md` §6 (E-1/E-2), `docs/research/B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md` (M-11), and `docs/plan/B2_E8_HOST_RESOURCE_ASSESSMENT.md`. DR-04/DR-05, GPU qualification, full LOKO and final held-out evaluation remain NO-GO.
