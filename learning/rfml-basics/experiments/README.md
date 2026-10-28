# Experiments

Reproducible multi-seed campaigns over the `rfml` stages. The analysis plan
(hypotheses H1–H4, success criteria, reporting rules) was fixed in
[PREREGISTRATION.md](PREREGISTRATION.md) before the campaign ran; read it
first.

## Reproduce the campaign

```bash
bash setup.sh                       # once: creates .venv, installs requirements
.venv/bin/python experiments/run_campaign.py --scale full --seeds 0 1 2 3 4
```

Wall time is roughly 20–40 minutes on a 4-core CPU (exact time is recorded in
`campaign/aggregate.json` → `wall_time_s`). A fast smoke run:

```bash
.venv/bin/python experiments/run_campaign.py --scale quick --seeds 0 1 \
    --out experiments/campaign_smoke
```

## Outputs (under `campaign/`)

| File | Content |
| --- | --- |
| `aggregate.json` | per-seed metrics, mean/sd/min/max, H1–H4 paired differences, provenance (git commit, library versions, scale, seeds) |
| `aggregate_summary.md` | the same as a readable table (generated; do not edit) |
| `<stage>_seed<k>.json` | per-stage result without bulky score arrays (committed) |
| `raw/<stage>_seed<k>.json` | full result including per-frame scores (not committed; regenerate with the command above) |

Stages per seed: `modulation` (impaired), `modulation_ideal` (ablation),
`fingerprint`, `fingerprint_ideal` (control), `open_set` (CE+MSP,
CE+distance, Objectosphere+MSP at xi=10, lam=0.1, target 0.95).

## Determinism and honesty rules

- Same arguments → same JSON numbers (CPU, fixed thread count, per-role
  `SeedSequence` streams). The aggregate records the exact git commit.
- A stage that raises is recorded under `failures` in the aggregate and in
  the summary; it is never silently dropped, and no seed is excluded.
- Every rate in the stage outputs names its positive class, denominator and
  n; missing metrics are `null`, never NaN.
