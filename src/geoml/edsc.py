"""EDSC/1: residual-energy anomaly scoring on the canonical P20 monitor grid.

Only observation-derived residual PSD provides anomaly evidence. The observed
co-pol spectrum supplies the per-observation planned-carrier power reference;
the operator mask defines its core bins. No fitting or simulator metadata is
used. Larger scores mean more residual energy relative to this reference.
"""
from __future__ import annotations

import numpy as np

from geosim.b2_protocol import LABELS, role_for_group

FREQUENCIES_HZ = np.fft.fftshift(np.fft.fftfreq(512, 1 / 96e6))
TRANSPONDER = np.abs(FREQUENCIES_HZ) <= 18e6
CORE_DB = -3.0
NOMINAL_PFA = 0.05


def _array(values, name, shape):
    array = np.asarray(values)
    if array.dtype.kind not in "iuf" or array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite numeric array with shape {shape}")
    return array


def _linear(db):
    """Reject unsupported powers rather than clipping, flooring or hiding overflow."""
    values = np.power(10.0, np.asarray(db, dtype=np.float64) / 10.0)
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("EDSC power normalization requires finite strictly positive linear PSD")
    return values


def residual_energy(spec_db, mask_db, residual_db):
    """Return four length-N dB vectors from canonical ``[N,2,128,512]`` observations.

    ``score_db = 10 log10(mean(residual power in |f| <= 18 MHz) / reference)``.
    Every one of the 128 snapshots has equal weight. The reference is the mean
    observed co-pol linear PSD over time and in-band operator core bins
    (mask > -3 dB). Equal bin width cancels in the ratio; equivalently it is
    integrated residual power divided by reference PSD times analyzed bandwidth.

    ``planned_db`` uses the core bins; ``unplanned_db`` uses their in-band
    complement, which includes carrier roll-off bins and is not an activity mask.
    These two diagnostics never select the detection score. Original spectra
    supply normalization only; cross-pol values are unused after validation.
    One observation's float64 power arrays are resident at a time.
    """
    raw = np.asarray(spec_db)
    if raw.ndim != 4 or not len(raw):
        raise ValueError("EDSC requires nonempty canonical [N,2,128,512] spectra")
    n = len(raw)
    spec = _array(raw, "spec_db", (n, 2, 128, 512))
    mask = _array(mask_db, "mask_db", (n, 2, 512))
    residual = _array(residual_db, "residual_db", (n, 128, 512))
    result = {key: np.empty(n, dtype=np.float64)
              for key in ("score_db", "planned_db", "unplanned_db", "reference_db")}
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            for row in range(n):
                core = (mask[row, 0] > CORE_DB) & TRANSPONDER
                noncore = ~core & TRANSPONDER
                if not core.any() or not noncore.any():
                    raise ValueError("EDSC normalization needs in-band carrier core and non-core bins")
                reference = float(_linear(spec[row, 0][:, core]).mean())
                power = _linear(residual[row])
                if not np.isfinite(reference) or reference <= 0:
                    raise ValueError("EDSC normalization reference must be finite and positive")
                reference_db = 10 * np.log10(reference)
                result["reference_db"][row] = reference_db
                for key, region in (("score_db", TRANSPONDER), ("planned_db", core),
                                    ("unplanned_db", noncore)):
                    # Subtract logarithms to avoid overflow/underflow in the ratio itself.
                    result[key][row] = 10 * np.log10(power[:, region].mean()) - reference_db
    except FloatingPointError as error:
        raise ValueError("EDSC observations exceed the supported finite power normalization range") from error
    if any(not np.isfinite(values).all() for values in result.values()):
        raise ValueError("EDSC normalized scores must be finite")
    return result


def calibrate_clean(scores, labels, groups, *, role, provenance):
    """Calibrate only clean known ``val-calib`` rows at nominal Pfa = 5%.

    The threshold is NumPy's deterministic higher empirical 95th percentile;
    alarm when score > threshold (ties are not alarms). This does not guarantee
    a 5% population false-alarm probability. At least two independent clean
    scenario groups are required for an engineering smoke; below 20, even one
    observed alarm exceeds the target. All inputs must belong to the known
    calibration role; non-clean known rows never contribute to the quantile.
    """
    values, targets, ids = np.asarray(scores), np.asarray(labels), np.asarray(groups)
    if (values.dtype.kind not in "iuf" or values.ndim != 1 or not len(values)
            or not np.isfinite(values).all()):
        raise ValueError("calibration scores must be a nonempty finite numeric vector")
    if (targets.dtype.kind not in "iu" or targets.shape != values.shape
            or np.any(targets < 0) or np.any(targets >= len(LABELS))):
        raise ValueError("calibration labels must be known B2 class indices")
    if ids.dtype.kind not in "iu" or ids.shape != values.shape:
        raise ValueError("calibration groups must be integer scenario ids matching scores")
    if role != "val-calib" or {role_for_group(int(group)) for group in ids} != {"val-calib"}:
        raise ValueError("EDSC threshold calibration is restricted to frozen known val-calib groups")
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError("EDSC calibration requires nonempty bound provenance")
    if len(set(zip(ids.tolist(), targets.tolist()))) != len(ids):
        raise ValueError("duplicate calibration scenario-group/label pairs")
    clean = values[targets == 0].astype(np.float64)
    clean_groups = ids[targets == 0]
    if len(clean) < 2 or len(np.unique(clean_groups)) != len(clean):
        raise ValueError("EDSC needs at least two distinct clean calibration scenario groups")
    threshold = float(np.quantile(clean, 1 - NOMINAL_PFA, method="higher"))
    count = int(np.sum(clean > threshold))
    return {"method": "edsc", "threshold": threshold, "comparison": ">",
            "nominal_pfa": NOMINAL_PFA, "quantile": "higher empirical 0.95 quantile",
            "n_calibration": len(clean), "n_calibration_groups": len(clean_groups),
            "false_alarm_count": count, "false_alarm_rate": count / len(clean),
            "empirical_resolution": 1 / len(clean), "small_population": len(clean) < 20,
            "population_claim": "empirical calibration only; nominal Pfa is not a population guarantee",
            "role": "val-calib", "population": "clean only", "provenance": provenance}
