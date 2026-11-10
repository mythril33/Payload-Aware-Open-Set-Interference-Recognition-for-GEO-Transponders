# Pre-registered analysis plan — campaign 3 and the replication set

Written 2026-11-09, **before** any run described here. This amendment follows
[PREREGISTRATION.md](PREREGISTRATION.md) and
[PREREGISTRATION_V2.md](PREREGISTRATION_V2.md); campaigns 1 and 2 are closed
and their results stand. This file must be committed and pushed before the
first run it describes, so the git record shows the order (campaign 1's plan
was committed about 3.5 minutes after its run began; that is not repeated).

It closes the items the peer review of the paper left open:

1. Campaigns 1 and 2 used five seeds. Are their verdicts reproduced on five
   fresh seeds?
2. The Objectosphere arms of campaign 2 differed in the training seed as well
   as in the auxiliary-outlier pool. Does H7 survive when the seed is shared?
3. The paper reads the MLP's chance-level test accuracy as memorisation of
   training *devices*. That needs the counterfactual: accuracy on new frames
   of the *seen* devices.
4. H5 was negative at one shrinkage value. How does Mahalanobis scoring vary
   with the shrinkage?

## Part A — replication of H1–H8 on fresh seeds

- `run_campaign.py` and `run_campaign2.py`, unchanged code, scale `full`,
  **seeds 5, 6, 7, 8, 9**, output in `experiments/campaign_rep/` and
  `experiments/campaign2_rep/`.
- Criterion on the replication set alone: the same as before, predicted sign
  in **at least 4 of 5 seeds**.
- Pooled over all ten seeds (0–9), computed by `pool_replication.py`:
  predicted sign in **at least 8 of 10 seeds**. For reference, the two-sided
  sign-test p is 0.109 at 8/10, 0.021 at 9/10 and 0.002 at 10/10; we report
  the count and these values, not a significance claim.
- A hypothesis is called **replicated** only if it meets the 4/5 criterion on
  seeds 5–9. Anything else is reported as not replicated, whatever the pooled
  count says.

## Part B — campaign 3 (new stages, seeds 0–9, scale `full`)

New code in `rfml/experiments_v3.py` and `experiments/run_campaign3.py`.
Nothing in `rfml/experiments.py` is changed.

**B1. Shared-seed Objectosphere arms.** The three arms of campaign 2 (full
{16PSK, 8PAM}, 16PSK-only, 8PAM-only) are retrained with **one** training
seed, `seed + 101`, on the same data. The arms then differ only in the
auxiliary-outlier pool.

- **H7s:** rejection of 4PAM unknowns is higher under the 8PAM-only arm than
  under the 16PSK-only arm. Criterion: at least 8 of 10 seeds.
- Check, not a hypothesis: the full arm at `seed + 101` must reproduce
  campaign 2's full arm exactly for seeds 0–4 (same seed, same data).

**B2. Seen-device counterfactual.** The MLP and the CNN1D are trained exactly
as in campaign 1 (same data, same seed, same selection on unseen validation
devices). Each trained model is then scored on two test sets at every test
SNR: the campaign-1 test set (frames of **unseen** devices) and new frames of
the **training** devices (3 frames per device per SNR, drawn from a stream
that no other role uses).

- **H9:** MLP accuracy on new frames of seen devices is higher than on unseen
  devices. This is what "the MLP memorised the training devices" predicts. If
  H9 fails, the MLP memorised training *frames*, and the paper's sentence
  must change.
- **H10:** CNN1D accuracy on new frames of seen devices is higher than on
  unseen devices (the device shift costs accuracy).
- Criterion for both: at least 8 of 10 seeds.
- Check, not a hypothesis: the unseen-device accuracies of seeds 0–4 must
  equal campaign 1's exactly.

**B3. Mahalanobis shrinkage sweep (exploratory, no pass/fail).** On the same
CE model as campaign 2, the Mahalanobis score is recomputed for shrinkage
0.01, 0.1, 0.5, 0.9 and 1.0. At 1.0 the covariance is a scaled identity, so
its AUROC must equal the Euclidean score's (a check). We report AUROC per
value with per-seed spread and label the result exploratory: the values were
chosen after seeing campaign 2.

## Reporting rules

Unchanged: no seed dropped; a failed stage is recorded under `failures`;
every rate names its positive class, denominator and n; unknown test classes
influence no fit, selection or threshold; sample standard deviations
(ddof = 1); the seed is the unit of replication. Synthetic data only.
