# E8 host and resource assessment — arithmetic and requirements, not a reservation

Date: 2026-10-24. Base `main` `4a1cc95`. `benchmark_complete=false`; no host, GPU or backup target is designated and no ceiling is approved.
Numbers come from `python scripts/b2_e8_budget.py` ([`b2_e8_resource_budget.json`](../results/b2_e8_resource_budget.json), strict JSON, every figure
basis-labelled) and from `scripts/b2_host_inventory.py` (read-only). Basis vocabulary: *analytic* (closed form), *measured_cpu_noisy* (E7a footprint run on a
loaded 4-vCPU sandbox), *plan_assumption*, *extrapolation* (an assumption scaled by an analytic ratio). **No GPU, no production-size generation and no
target-host throughput was measured by this work.**

## 1. The width-8 reservation is withdrawn

E5 reserved **6 GPU-h** for the nine main fits from a 200-1,000 samples/s band stated for the ~80 k-parameter width-8 network, batch 8. The
`TrainConfig`/P6 default is **width 16** (311,705 parameters for `dual_residual`, 3.31x the multiply-accumulates of width 8, saved activations 2x at the
same batch, K18 centre-term ratio D/2 = 128 instead of 64). The 6 GPU-h figure is therefore not carried to width 16 (nor to any width) and no
replacement reservation is proposed until the bounded probe ([spec](b2_e8_gpu_probe_spec.json)) replaces the assumptions.

## 2. Screening bands (extrapolations; the probe replaces them)

GPU pure compute = passes / (width-8 band / MAC ratio); loader = 93 s per epoch at 12,000 train + 1,200 val-select observations, synchronous and
un-overlapped (the trainer has no prefetch). CPU-only = passes / measured warm CPU rate (noisy, loaded sandbox), compute only.

| Campaign (30 epochs) | Fits | Train passes | W8 GPU compute (h) | W16 GPU compute (h) | Synchronous loader (h) | W8 compute + loader (h) | **W16 compute + loader (h)** | W16 CPU-only compute (h) |
|---|---:|---:|---|---|---:|---|---|---:|
| Main: 3 views x 3 seeds | 9 | 3.24 M | 0.9 - 4.5 | 3.0 - 14.9 | 7.0 | 7.9 - 11.5 | **10.0 - 21.9** | 35.2 |
| LOKO, primary view (10,500 train obs) | 21 | 6.62 M | 1.8 - 9.2 | 6.1 - 30.4 | 14.2 | 16.1 - 23.4 | 20.3 - 44.6 | 71.8 |
| LOKO, three views | 63 | 19.8 M | 5.5 - 27.6 | 18.2 - 91.2 | 42.7 | 48.2 - 70.3 | 61.0 - 133.9 | 215.3 |

Reading: even the main campaign at width 16 is roughly **1.7 - 3.7 x the old 6 GPU-h** once the un-overlapped loader is counted, and the loader alone
(7.0 h, E1 rates from a different loaded CPU) exceeds the old reservation; real GPU utilization does not scale with MACs alone, so both ends can move.
The CPU-only column shows that a CPU fallback for the nine fits is not realistic (35 h compute at width 16 before the loader).

## 3. Generation, storage and memory (unchanged from E5 unless stated)

| Item | Figure | Basis |
|---|---|---|
| Generation (21,350 observations, one process, two BLAS threads) | 23.0 / 26.6 / 30.2 h (low / central / high); proposed ceiling 36 h wall, 42 core-h | extrapolation from a 60-observation matched profile; the E7a capped real-physics run cost 4.58 / 5.27 / 4.83 s per observation (known / test-only / matched) as whole-attempt wall including start-up, which neither confirms nor refutes the 3.8 - 5.0 s band |
| Artifacts | 395,264 B float16 arrays per observation = 8.44 GB; 8.7 GB with metadata | analytic from array shapes + one measured artifact |
| Working disk / backup | 25 GiB working + a verified backup of at least 9 GB on a **different device** | plan_assumption (proposal) |
| Training host | its own verified copy of the artifacts (>= 9 GB) + outputs (checkpoints ~1.2 MiB per width-16 fit) + headroom: 25 GiB free proposed | plan_assumption |
| Generator RAM | ~0.6 GiB measured per process (E7a child peak RSS 566 - 582 MiB at two groups); 2 GiB reserved per process, 8 GiB host | measured (tiny) + plan_assumption |
| Training host RAM | one fit ~2 GiB (0.7 GiB baseline + step peak 0.63 GiB at width 16 batch 32 + 128 MiB window); 16 GiB proposed | measured_cpu_noisy step peaks + analytic window; no full-run measurement exists |
| GPU memory | analytic bound for `dual_residual` width 16 batch 32: 452.9 - 881.0 MiB **excluding CUDA context, workspaces and fragmentation**; 8 GiB minimum / 12 GiB preferred proposed | analytic; nothing measured on a GPU |

## 4. Target-host requirements (proposed, UNAPPROVED; the tool compares a machine with them)

| Role | CPU | RAM | Disk | GPU | Other |
|---|---|---|---|---|---|
| Generation host | >= 4 logical CPUs, 2 BLAS threads per process | >= 8 GiB available | >= 25 GiB free working root; backup >= 9 GB on another device; atomic rename + fsync (preflight `resources`) | none | clean checkout, production lock verified, pinned Python/NumPy/SciPy |
| Training host | >= 2 CPUs | >= 16 GiB available | >= 25 GiB free | one CUDA device, >= 8 GiB (12 GiB preferred); driver compatible with the pinned torch build | the synchronous loader is CPU- and disk-bound: local SSD preferred over network storage (unverified) |

`python scripts/b2_host_inventory.py --role {generation,training} --path ROOT [--backup-path B] [--out report.json]` is read-only: it creates nothing,
imports neither torch nor CUDA, and runs at most one fixed `nvidia-smi --query-gpu` driver query. A missing GPU is BLOCKED, a measured shortfall FAIL;
PASS means only "meets the proposed figure".

## 5. This sandbox against the requirements (evidence, not a candidate)

[`b2_e8_host_inventory_sandbox_generation.json`](../results/b2_e8_host_inventory_sandbox_generation.json) and
[`..._training.json`](../results/b2_e8_host_inventory_sandbox_training.json): 4 vCPU Xeon, 15.1 GiB available RAM, 19.7 GiB free on a single device, no
NVIDIA device or `nvidia-smi`. Verdict **FAIL** for both roles: free disk is below the 25 GiB working root, the backup would sit on the same device, there
is no GPU and (training) RAM is below 16 GiB. This machine can run bounded CPU fixtures only; it is unsuitable for DR-04 and DR-05 as configured.

## 6. What the researcher must supply to turn this into a plan

A designated generation host and backup target, a designated GPU host (model, VRAM, driver, torch build), the wall / core-hour / GPU-hour / disk ceilings for
DR-04 and DR-05, and the R2/R5/R6 decisions that fix the configuration the probe measures. Until then the budget above is a screening table.
