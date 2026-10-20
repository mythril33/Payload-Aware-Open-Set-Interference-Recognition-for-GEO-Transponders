# Original project brief — content transcription

**Source:** User-supplied `Payload-Aware Open-Set Interference Recognition for GEO Transponders.docx`, 2 pages.
**Archive hash of the original DOCX (SHA-256):** `de550d2b7556d533746c44d6026880625b28c41272f62ec097769161d6891a53`.
**Source size:** 63,348 bytes. **Document language:** English.

This is a *text-and-table transcription* of the original user's uploaded brief, **not** a revised research claim and **not** the unmodified binary DOCX. The final roadmap is an embedded **image**, summarized separately below; image typography and its exact object bytes are not preserved in Markdown. For corrections and verified research use `docs/plan/P1_literatur.md`, `P8_dis_veri.md`, and `docs/plan/00_ana_plan.md`.

# Payload-Aware Open-Set Interference Recognition for GEO Transponders

## Topic and motivation

The project builds a deep-learning recognizer that detects and classifies interference in a GEO bent-pipe transponder, as seen by an operator's downlink spectrum monitoring, and rejects interference types it was never trained on. Interference (CW, swept carriers, cross-polarization leakage, adjacent-satellite and unauthorized carriers, carrier-under-carrier, payload overdrive) is a daily operational cost for GEO operators. Today it is mostly found by threshold alarms and expert inspection of spectrum-analyzer traces.

## Research gap and contributions

Published Deep Learning interference work is dominated by GNSS receivers; the few GEO studies train on idealized signals that omit the transponder's nonlinear multicarrier behavior, treat recognition as closed-set, and use single-polarization spectra without the operator's carrier plan. Reported accuracies therefore overstate operational performance: payload intermodulation is confused with external interference, cross-pol and unplanned-carrier events are ambiguous, and unseen interferers are silently misclassified. There are 3 possible candidate contributions that can be followed.

- C1 — Payload-realistic, open-source dataset generator: multicarrier DVB-S2 loading, IMUX/OMUX group delay, TWTA AM/AM–AM/PM over an input back-off sweep, phase noise, dual polarization and carrier-plan metadata.
- C2 — Plan-conditioned, dual-polarization open-set recognizer, with an identifiability analysis of which observables each interference class needs.
- C3 — Quantified "payload gap": degradation of models trained without the nonlinear chain, and generalization to unseen back-off, bandwidth and loading.

## Method

A Python simulator models the full bent-pipe path: uplink carriers and interferers entering to the receiver, injection of receiver phase noise, signal passes through the IMUX and TWTA (Saleh model at a set input back-off), gets into the OMUX that is eventually turned into downlink noise, for both polarizations. Each scenario yields a 3-channel time–frequency input (co-pol spectrogram, cross-pol spectrogram, carrier-plan mask) plus a cyclic-spectrum feature vector.

- Models: a plan-conditioned ResNet and a small spectrogram transformer (PyTorch), with an optional cyclic-feature branch.
- Open-set rejection: maximum softmax, energy score and class-conditional Mahalanobis distance on the learned embedding.
- Baselines: CA-CFAR energy detection, and expert spectral/cyclostationary features with gradient boosting.
- Classes: 8 known (clean, CW, swept CW, cross-pol, adjacent-satellite, unauthorized carrier, carrier-under-carrier, overdrive IM); 3 held out as unknown (pulsed, wideband noise, intermittent bursts).

## Data strategy

Training data comes from the simulator, made traceable to the DVB-S2 reference satellite channel. Public data supplies comparison and real-hardware realism; operator data(if possible).

| Role | Source |
|---|---|
| Comparison with prior GEO work | SnT on-board interference and NGSO-to-GSO datasets |
| Measured amplifier nonlinearity | OpenDPD; Chalmers RF WebLab (remote PA measurement) |
| Real interferer recordings | Fraunhofer DARCY GNSS datasets |
| Generic RF pretraining baseline | TorchSig / WidebandSig53 |

## Evaluation

Test sets are split by operating condition, never randomly: unseen input back-off, transponder bandwidth, carrier loading and held-out interferer types. Reported metrics are detection probability at fixed false-alarm rate versus C/I, macro-F1 on known classes, AUROC and OSCR for unknown rejection, and parameters, FLOPs and latency per frame. Ablations isolate each claim: cross-pol channel, plan mask, nonlinear-chain training, cyclic branch, and CNN versus transformer.

## Roadmap, risks and venues

The original section contains a graphical six-phase calendar headed **"Manuscript submitted by mid-December 2026 after six phases"**. Graphic text (readable approximation, not a recreation of the embedded source image):

| Phase | Dates shown | Exit criterion shown |
|---|---|---|
| 1 Scope and literature | 7–18 Oct 2026 | 25–35 papers tabulated, gap and claims frozen |
| 2 Simulator and dataset | 12 Oct–1 Nov 2026 | AM/AM, group delay and back-off checks pass |
| 3 Baselines | 2–8 Nov 2026 | CFAR and expert-feature curves vs C/I |
| 4 Models and ablations | 9–29 Nov 2026 | One ablation table per contribution claim |
| 5 Generalization | 23 Nov–6 Dec 2026 | Unseen-condition, public- and real-data results |
| 6 Write and submission | 30 Nov–15 Dec 2026 | Manuscript submitted |

**Editorial separation:** The claims above belong to the *original proposal*. The dated plans, implementations, physics corrections and license caveats in the repository are later research, not part of this transcription.
