"""Carrier-under-carrier visibility in the monitored spectrum versus C/I (input to P18 / K17).

    python scripts/cuc_visibility.py --out docs/results/cuc_visibility.json

For each scenario seed one under-carrier placement (E1 generator) is kept and
only its power changes with C/I. The same carriers and noise pass through the
single-polarization A1 chain (DVB-S2 H.3 TWTA) with and without the event.
Delta = time-averaged PSD in the under-carrier band with the event / without it.
This paired difference is an upper bound on visibility: an operator has no
event-free twin. Sigma = 1-sigma estimation noise of the band mean from the
128 snapshots of the event-free spectrum. "Visible" means delta > 3 sigma.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from geosim.events import carrier_under_carrier
from geosim.plan import monitor_freqs
from geosim.scenario import ScenarioConfig, default_plan, simulate

C_OVER_I_DB = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)   # against total planned uplink power
SEEDS = tuple(range(600_000, 600_024))              # outside every dataset protocol's seed range
IBO_DB, CN_DB = 11.0, 25.0                          # mid A1 nominal values [assumption]


def band_mean(spec_db: np.ndarray, sel: np.ndarray) -> tuple[float, float]:
    """Time-averaged linear power in the selected bins and its 1-sigma relative estimation noise."""
    rows = np.mean(10 ** (spec_db[:, sel].astype(float) / 10), axis=1)
    return float(rows.mean()), float(rows.std(ddof=1) / np.sqrt(len(rows)) / rows.mean())


def measure(seeds=SEEDS, levels=C_OVER_I_DB) -> dict:
    freqs = monitor_freqs()
    rows = []
    for seed in seeds:
        cfg = ScenarioConfig(bandwidth=36e6, ibo_db=IBO_DB, cn_up_db=CN_DB, cn_dn_db=CN_DB, seed=seed)
        plan = default_plan(seed, 36e6)
        clean = simulate(cfg, plan=plan)
        for ci in levels:
            gen, info = carrier_under_carrier(np.random.default_rng([seed, 8000]), plan, 36e6, ci)
            sel = (freqs >= info["f_lo"]) & (freqs <= info["f_hi"])
            if not sel.any():
                raise ValueError(f"seed {seed}: under-carrier band resolves to no monitor bin")
            p0, rel_sigma = band_mean(clean.spec_db, sel)
            p1, _ = band_mean(simulate(cfg, plan=plan, interferer=gen).spec_db, sel)
            delta = 10 * np.log10(p1 / p0)
            sigma_db = 10 * np.log10(1 + rel_sigma)
            rows.append({"seed": seed, "c_over_i_db": ci, "victim_c_over_i_db": info["victim_c_over_i_db"],
                         "n_bins": int(sel.sum()), "delta_db": float(delta), "sigma_db": float(sigma_db),
                         "visible_3sigma": bool(delta > 3 * sigma_db)})
    summary = []
    for ci in levels:
        r = [x for x in rows if x["c_over_i_db"] == ci]
        summary.append({"c_over_i_db": ci, "n": len(r),
                        "median_victim_c_over_i_db": float(np.median([x["victim_c_over_i_db"] for x in r])),
                        "median_delta_db": float(np.median([x["delta_db"] for x in r])),
                        "median_3sigma_db": float(np.median([3 * x["sigma_db"] for x in r])),
                        "fraction_visible_3sigma": float(np.mean([x["visible_3sigma"] for x in r]))})
    return {"ibo_db": IBO_DB, "cn_up_db": CN_DB, "cn_dn_db": CN_DB, "amplifier": "dvbs2_nl",
            "seeds": list(seeds), "summary": summary, "rows": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    result = measure()
    a.out.write_text(json.dumps(result, indent=1, allow_nan=False) + "\n")
    for s in result["summary"]:
        print(f"C/I {s['c_over_i_db']:4.0f} dB (victim {s['median_victim_c_over_i_db']:5.1f}): "
              f"delta {s['median_delta_db']:6.3f} dB, 3 sigma {s['median_3sigma_db']:.3f} dB, "
              f"visible {100 * s['fraction_visible_3sigma']:.0f} %")
