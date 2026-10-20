"""Uplink adjacent-satellite interference: geometry-driven C/I and spectral visibility (input to P18 / K17).

    python scripts/asi_visibility.py --out docs/results/asi_visibility.json

Each scenario seed draws one uplink ASI event from geosim.asi with the default
(sourced) ranges. The same carriers and noise pass through the single-polarization
A1 chain (DVB-S2 H.3 TWTA) with and without the event. Delta = time-averaged PSD
with the event / without it, separately over the interferer's bins that lie
inside the operator plan and those outside it. This paired difference is an upper
bound on visibility: an operator has no event-free twin. Sigma = 1-sigma
estimation noise of the band mean from the snapshots of the event-free spectrum.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from geosim.asi import DEFAULT_RANGES, adjacent_satellite_uplink
from geosim.plan import monitor_freqs
from geosim.scenario import ScenarioConfig, default_plan, simulate

SEEDS = tuple(range(610_000, 610_120))              # outside every dataset protocol's seed range
IBO_DB, CN_DB = 11.0, 25.0                          # mid A1 nominal values [assumption]
CI_BINS_DB = ((-np.inf, 10.0), (10.0, 15.0), (15.0, 20.0), (20.0, 25.0), (25.0, np.inf))


def band_mean(spec_db: np.ndarray, sel: np.ndarray) -> tuple[float, float]:
    """Time-averaged linear power in the selected bins and its 1-sigma relative estimation noise."""
    rows = np.mean(10 ** (spec_db[:, sel].astype(float) / 10), axis=1)
    return float(rows.mean()), float(rows.std(ddof=1) / np.sqrt(len(rows)) / rows.mean())


def _delta(clean, event, sel):
    if not sel.any():
        return None, None
    p0, rel_sigma = band_mean(clean.spec_db, sel)
    p1, _ = band_mean(event.spec_db, sel)
    return float(10 * np.log10(p1 / p0)), float(10 * np.log10(1 + rel_sigma))


def measure(seeds=SEEDS) -> dict:
    freqs = monitor_freqs()
    rows = []
    for seed in seeds:
        cfg = ScenarioConfig(bandwidth=36e6, ibo_db=IBO_DB, cn_up_db=CN_DB, cn_dn_db=CN_DB, seed=seed)
        plan = default_plan(seed, 36e6)
        gen, info = adjacent_satellite_uplink(np.random.default_rng([seed, 8100]), plan, 36e6)
        band = (freqs >= info["f_lo"]) & (freqs <= info["f_hi"])
        if not band.any():
            raise ValueError(f"seed {seed}: interferer band resolves to no monitor bin")
        planned = np.zeros_like(band)
        for c in plan:
            planned |= (freqs >= c.f0 - c.occupied_bw / 2) & (freqs <= c.f0 + c.occupied_bw / 2)
        clean, event = simulate(cfg, plan=plan), simulate(cfg, plan=plan, interferer=gen)
        row = {"seed": seed, "c_over_i_psd_db": info["c_over_i_psd_db"], "c_over_i_db": info["c_over_i_db"],
               "overlap_fraction": info["overlap_fraction"], "symbol_rate": info["carrier"]["symbol_rate"],
               "geometry": info["geometry"]}
        for name, sel in (("in_plan", band & planned), ("out_of_plan", band & ~planned)):
            delta, sigma = _delta(clean, event, sel)
            row[name] = {"n_bins": int(sel.sum()), "delta_db": delta, "sigma_db": sigma,
                         "visible_3sigma": None if delta is None else bool(delta > 3 * sigma)}
        rows.append(row)
    return {"ibo_db": IBO_DB, "cn_up_db": CN_DB, "cn_dn_db": CN_DB, "amplifier": "dvbs2_nl", "bandwidth": 36e6,
            "ranges": asdict(DEFAULT_RANGES),
            "seeds": list(seeds), "geometry_summary": geometry_summary(rows), "summary": summary(rows), "rows": rows}


def _stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0, "median": None, "p10": None, "p90": None}
    return {"n": len(values), "median": float(np.median(values)),
            "p10": float(np.percentile(values, 10)), "p90": float(np.percentile(values, 90))}


def geometry_summary(rows) -> dict:
    ci = [r["c_over_i_psd_db"] for r in rows]
    by_diameter = {str(d): _stats([r["c_over_i_psd_db"] for r in rows if r["geometry"]["diameter_m"] == d])
                   for d in DEFAULT_RANGES.diameters_m}
    regions = sorted({r["geometry"]["pattern_region"] for r in rows})
    return {"c_over_i_psd_db": _stats(ci), "c_over_i_psd_min_db": float(min(ci)), "c_over_i_psd_max_db": float(max(ci)),
            "by_diameter_m": by_diameter,
            "pattern_region_counts": {k: sum(r["geometry"]["pattern_region"] == k for r in rows) for k in regions}}


def summary(rows) -> list:
    out = []
    for lo, hi in CI_BINS_DB:
        r = [x for x in rows if lo <= x["c_over_i_psd_db"] < hi]
        entry = {"c_over_i_psd_db": [None if np.isinf(lo) else lo, None if np.isinf(hi) else hi], "n": len(r)}
        for name in ("in_plan", "out_of_plan"):
            d = [x[name] for x in r if x[name]["delta_db"] is not None]
            entry[name] = {"n_with_bins": len(d), **{k: v for k, v in _stats([x["delta_db"] for x in d]).items() if k != "n"},
                           "fraction_visible_3sigma": float(np.mean([x["visible_3sigma"] for x in d])) if d else None,
                           "fraction_above_0p5_db": float(np.mean([x["delta_db"] > 0.5 for x in d])) if d else None,
                           "fraction_above_1_db": float(np.mean([x["delta_db"] > 1.0 for x in d])) if d else None}
        out.append(entry)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    result = measure()
    a.out.write_text(json.dumps(result, indent=1, allow_nan=False) + "\n")
    g = result["geometry_summary"]["c_over_i_psd_db"]
    print(f"C/I_psd median {g['median']:.1f} dB (p10 {g['p10']:.1f}, p90 {g['p90']:.1f}), n={g['n']}")
    for s in result["summary"]:
        cells = []
        for name in ("in_plan", "out_of_plan"):
            v = s[name]
            cells.append(f"{name} n={v['n_with_bins']} median " + ("-" if v["median"] is None else f"{v['median']:.2f} dB")
                         + ("" if v["fraction_above_1_db"] is None else f", >1 dB {100 * v['fraction_above_1_db']:.0f} %"))
        print(f"C/I_psd {s['c_over_i_psd_db']}: n={s['n']}; " + "; ".join(cells))
