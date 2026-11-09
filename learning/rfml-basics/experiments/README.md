# Experiments

Three pre-registered campaigns and a replication, all on synthetic data from
`rfml/signals.py`. Each analysis plan fixes its hypotheses and pass criteria;
read the plans first.

| Plan | Covers | Seeds |
| --- | --- | --- |
| [PREREGISTRATION.md](PREREGISTRATION.md) | campaign 1: separately trained open-set variants, closed-set and fingerprinting checks (H1–H4) | 0–4 |
| [PREREGISTRATION_V2.md](PREREGISTRATION_V2.md) | campaign 2: five post-hoc scores on one network, three outlier pools (H5–H8) | 0–4 |
| [PREREGISTRATION_V3.md](PREREGISTRATION_V3.md) | replication of H1–H8 on fresh seeds; campaign 3: shared-seed outlier pools (H7s), seen-device counterfactual (H9, H10), shrinkage sweep (exploratory) | 5–9; 0–9 |

The plans of campaigns 2 and 3 and of the replication were committed before
their runs. Campaign 1's plan was written before its run but committed about
3.5 minutes after the run began.

## Reproduce everything

```bash
bash setup.sh                                   # once (Windows: setup.ps1)
PY=.venv/bin/python                             # Windows: .venv\Scripts\python

$PY experiments/run_campaign.py  --seeds 0 1 2 3 4                                  # campaign 1
$PY experiments/run_campaign2.py --seeds 0 1 2 3 4                                  # campaign 2
$PY experiments/run_campaign.py  --seeds 5 6 7 8 9 --out experiments/campaign_rep   # replication
$PY experiments/run_campaign2.py --seeds 5 6 7 8 9 --out experiments/campaign2_rep
$PY experiments/run_campaign3.py --seeds 0 1 2 3 4 5 6 7 8 9                        # campaign 3 (resumes)
$PY experiments/pool_replication.py --original experiments/campaign \
    --replication experiments/campaign_rep --out experiments/pooled/campaign1
$PY experiments/pool_replication.py --original experiments/campaign2 \
    --replication experiments/campaign2_rep --out experiments/pooled/campaign2

sh paper/build.sh                               # numbers, figures and paper.pdf (needs LaTeX)
```

The five campaign runs took 1045, 749, 1093, 505 and 1176 s on four CPU
threads (about 76 minutes in total); the exact times are in each
`aggregate.json`. A smoke run of any runner: add `--scale quick --seeds 0 1
--out experiments/<name>_smoke`.

## Outputs

| Path | Content |
| --- | --- |
| `campaign*/aggregate.json` | per-seed metrics, mean / sd / min / max, paired differences of the hypotheses, provenance (git commit, library versions, scale, seeds) |
| `campaign*/aggregate_summary.md` | the same as a table (generated; do not edit) |
| `campaign*/<stage>_seed<k>.json` | per-stage result without the per-frame score arrays (committed) |
| `campaign*/raw/<stage>_seed<k>.json` | the full result with per-frame scores (not committed, except campaign 2 seed 0, which two figures use; delivered in the results bundle) |
| `pooled/campaign{1,2}/` | the ten-seed pooling: original, replication and pooled counts per hypothesis |

Stages: campaign 1 runs `modulation`, `modulation_ideal`, `fingerprint`,
`fingerprint_ideal` and `open_set`; campaign 2 runs `scorer_bench`;
campaign 3 runs `arm_control` and `split_counterfactual`.

## Other scripts

| Script | Purpose |
| --- | --- |
| `make_figures.py` | the paper's figures (PDF and PNG) from the per-seed files |
| `export_dataset.py` | the data of one seed as `.npz` files with a SHA-256 manifest (`--closed-set` adds the campaign-1 data) |
| `make_bundle.py` | `release/rfml-openset-benchmark.zip`: paper, figures, results, raw scores, the seed-0 data and the code, with a manifest |

## Determinism and honesty rules

- Same arguments give the same JSON numbers (CPU, fixed thread count,
  per-role `SeedSequence` streams). Each aggregate records the git commit.
- A stage that raises is recorded under `failures`; it is never dropped, and
  no seed is excluded. Pooling refuses a campaign with failures.
- Every rate names its positive class, denominator and n; missing metrics are
  `null`, never NaN.
- Unknown test classes influence no fit, no model selection and no threshold.
