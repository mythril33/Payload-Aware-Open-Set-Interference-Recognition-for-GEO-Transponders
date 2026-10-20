# Project agent briefs

These are reusable project-level instructions for the agent roles used during
development. They can be supplied to coding agents in a supported host. They
are not a standalone agent server or a copy of the host's internal runtime.

The primary agent acts as integrator: define the next small working capability,
divide independent files, establish API contracts, integrate changes, run the
full relevant checks and physical smoke run, document outcomes, then push the
tested milestone. Reuse existing checkout and authentication.

| Brief | Responsibility |
|---|---|
| [Dataset integrity](dataset-integrity.md) | Generation, provenance, artifacts and safe resume |
| [Open-set methods](open-set-methods.md) | Scoring, calibration and open-set metrics |
| [ML integration](ml-integration.md) | Model/checkpoint compatibility and experiment execution |
| [Independent review](review.md) | Physics, leakage, numerical correctness and integration review |

Never assign overlapping files to concurrent agents. Hand off ownership or
coordinate changes through the integrator. Agent findings are evidence to
inspect, not substitutes for running the integrated workflow.
