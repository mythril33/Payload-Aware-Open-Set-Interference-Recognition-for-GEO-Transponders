"""Width-explicit production resource arithmetic for the B2/1 plan (E8, P32). Arithmetic only: no data, no model, no GPU.

    python scripts/b2_e8_budget.py                       # strict JSON on stdout
    python scripts/b2_e8_budget.py --out docs/results/b2_e8_resource_budget.json

Every figure carries a basis label: ``analytic`` (closed form from repository constants), ``measured_cpu_noisy`` (the
E7a footprint run on a loaded 4-vCPU sandbox, read from the proposal JSON), ``plan_assumption`` (E5/E7 planning figures)
or ``extrapolation`` (an assumption scaled by an analytic ratio). Nothing here is a measurement on a GPU or on the
designated host and nothing is a reservation: the width-8 "6 GPU-h" figure is deliberately NOT carried to width 16; the
GPU columns are screening bands that the authorized, bounded probe (P32 section 5) must replace.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import b2_production_preflight as pre  # noqa: E402

SCHEMA = "B2-E8-resource-budget/1"
PROPOSAL = REPO / "docs/plan/b2_e7_training_proposal.json"
# Forward MACs per sample, dual_residual (docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md section 5 / the proposal's model_width record).
MACS_G = {8: 0.097, 16: 0.321, 32: 1.154}
GPU_BAND_W8 = (200.0, 1000.0)             # samples/s, the E5 assumption, stated for the ~80 k-parameter width-8 network
LOADER_S_PER_EPOCH = 93.0                 # synchronous loader incl. val-select and K17b terms, 12,000 train observations (E7a)
TRAIN_OBS, VAL_SELECT_OBS, LOKO_TRAIN_OBS, LOKO_VAL_OBS = 12000, 1200, 10500, 1050
EPOCHS, SEEDS, VIEWS, HOLDOUTS = 30, 3, 3, 7


def cpu_warm_rate(proposal, width, batch=32, view="dual_residual"):
    rows = proposal["evidence"]["footprint_run"]["rows"]
    return next(r["cpu_warm_samples_per_s"] for r in rows if (r["view"], r["width"], r["batch"]) == (view, width, batch))


def gpu_band(width):
    """Width-8 band scaled by the analytic MAC ratio: a screening extrapolation, not a throughput claim."""
    ratio = MACS_G[width] / MACS_G[8]
    return GPU_BAND_W8[0] / ratio, GPU_BAND_W8[1] / ratio, ratio


def campaign(name, fits, train_obs, val_obs, width, proposal):
    passes = fits * EPOCHS * train_obs
    low_rate, high_rate, ratio = gpu_band(width)
    gpu_h = (passes / high_rate / 3600, passes / low_rate / 3600)
    loader_h = fits * EPOCHS * LOADER_S_PER_EPOCH * (train_obs + val_obs) / (TRAIN_OBS + VAL_SELECT_OBS) / 3600
    cpu_rate = cpu_warm_rate(proposal, width)
    cpu_h = passes / cpu_rate / 3600
    return {"name": name, "fits": fits, "epochs": EPOCHS, "train_observations_per_fit": train_obs,
            "train_sample_passes": passes, "val_select_forward_passes": fits * EPOCHS * val_obs,
            "gpu_pure_compute_hours_screening": [round(gpu_h[0], 2), round(gpu_h[1], 2)],
            "gpu_pure_compute_basis": f"extrapolation: width-8 band {GPU_BAND_W8} samples/s / MAC ratio {ratio:.2f}",
            "synchronous_loader_hours": round(loader_h, 2),
            "loader_basis": f"plan_assumption: {LOADER_S_PER_EPOCH} s/epoch at 12,000 train + 1,200 val-select observations, scaled linearly",
            "gpu_compute_plus_loader_hours_screening": [round(gpu_h[0] + loader_h, 2), round(gpu_h[1] + loader_h, 2)],
            "cpu_only_compute_hours": round(cpu_h, 1),
            "cpu_only_basis": f"measured_cpu_noisy: {cpu_rate} samples/s warm (dual_residual, batch 32, loaded sandbox) x passes; excludes loader"}


def build(proposal_path=PROPOSAL):
    proposal = json.loads(Path(proposal_path).read_text())
    plan_hours = {k: round(v, 2) for k, v in pre.BUDGET["documented_wall_hours"].items()}
    obs = pre.PLAN_TOTAL
    per_width = {}
    for width in (8, 16):
        per_width[str(width)] = {
            "model_macs_gmac_per_sample": MACS_G[width], "mac_ratio_vs_width8": round(MACS_G[width] / MACS_G[8], 2),
            "center_term_ratio_p20_over_p21b": 8 * width,       # D/2 with D = 16 x width
            "campaigns": [campaign("main: 3 views x 3 seeds", VIEWS * SEEDS, TRAIN_OBS, VAL_SELECT_OBS, width, proposal),
                          campaign("LOKO, primary view: 7 holdouts x 3 seeds", HOLDOUTS * SEEDS, LOKO_TRAIN_OBS, LOKO_VAL_OBS, width, proposal),
                          campaign("LOKO, all views: 7 x 3 x 3 views", HOLDOUTS * SEEDS * VIEWS, LOKO_TRAIN_OBS, LOKO_VAL_OBS, width, proposal)]}
    storage_gb = obs * pre.BUDGET["float16_bytes_per_observation"] / 1e9
    return {
        "schema": SCHEMA, "benchmark_complete": False, "production_authorized": False, "status": "ARITHMETIC_NOT_A_RESERVATION",
        "withdrawn_figure": "The E5 '6 GPU-h' reservation was written for width 8 and is not carried to width 16 or any other width; "
                            "no replacement reservation is proposed before the authorized probe.",
        "generation": {"observations": obs, "wall_hours_single_process": plan_hours, "reserved_wall_hours": pre.BUDGET["reserved_wall_hours"],
                       "reserved_core_hours": pre.BUDGET["reserved_core_hours"], "basis": "extrapolation from a 60-observation matched profile (E5); "
                       "nothing was timed beyond 64 observations; the supervisor's first-shard gate is the start-up validity test"},
        "storage": {"float16_array_gb": round(storage_gb, 2), "artifact_estimate_gb": pre.BUDGET["documented_storage_gb"],
                    "working_disk_gib_proposed": pre.PROPOSED_CEILINGS["working_disk_gib"],
                    "backup_gb_proposed": pre.PROPOSED_CEILINGS["backup_disk_gb"],
                    "training_host_copy_gb_minimum": pre.BUDGET["documented_storage_gb"],
                    "note": "the training host needs its own verified copy of the artifacts plus run outputs; checkpoints are ~1.2 MiB per width-16 fit"},
        "widths": per_width,
        "caveats": ["No GPU throughput, VRAM peak, loader rate on the target host or generation rate at production size has been measured.",
                    "GPU bands scale a width-8 assumption by the MAC ratio; real utilization does not scale with MACs alone.",
                    "The synchronous loader is added without overlap because no prefetching exists in the trainer.",
                    "CPU-only hours are measured on a loaded sandbox and are shown only to bound a fallback, not to plan a run."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    text = json.dumps(build(), indent=1, allow_nan=False) + "\n"
    if args.out:
        try:
            with open(args.out, "x") as stream:
                stream.write(text)
        except FileExistsError:
            print(f"{args.out} already exists; refusing to overwrite", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
