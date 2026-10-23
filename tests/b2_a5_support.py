"""Shared fast fixtures for the E4 A5 evaluation tests.

The on-disk artifacts are real B2-feat/1 and B2-match/1 artifacts written and verified by the production
writers; only the physics is a deterministic stand-in (random spectra and IQ seeded by the scene, a canceller
whose residual depends on the declared plan). The fakes are deterministic functions of the scene, so replay
parity, determinism and the receiver-consistent recomputation are exercised without a real simulation.
Nothing here is a recognition result. Real physics is covered by ``test_b2_a5_replay.py``.
"""
import atexit
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from geoml import b2_a5_replay as rp
from geoml.b2_experiment import B2ExperimentConfig, run_b2_experiment
from geosim import b2_dataset as ds
from geosim import b2_matched_dataset as md
from geosim import b2_scenarios as scenes
from geosim.b2_protocol import BASE_ROLES, B2Config
from geosim.cancellation import CancellationConfig
from geosim.plan import plan_mask_db

_WORKSPACE = None
CANCELLATION = CancellationConfig()


def _simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq, downlink_interferers=None):
    seed = int(cfg.co.seed)
    rng = np.random.default_rng([seed, int(round(cfg.uplink_xpd_db)), sum(event is not None for event in interferers)])
    spec = rng.normal(-80, 2, (2, 128, 512)).astype(np.float32)
    iq = None
    if keep_iq:
        gen = np.random.default_rng([seed, 99])
        iq = (gen.standard_normal((2, 128, 4096)) + 1j * gen.standard_normal((2, 128, 4096))).astype(np.complex64)
    power = [sum(c.power for c, keep in zip(plan, active) if keep) for plan, active in zip(plans, active_carriers)]
    meta = {"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
            "has_interferer": [event is not None for event in interferers],
            "has_downlink_interferer": [False, False],
            "active_carriers": [list(active) for active in active_carriers],
            "active_planned_power": power, "nominal_planned_power": [1., 1.],
            "gain_mode": "fixed_nominal_planned_power",
            "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10., "omux_output_power": 0.1,
                       "receiver_noise_psd": 1e-10, "zero_drive": False} for _ in range(2)],
            "receiver_calibration_applied": True, "receiver_calibration": calibration.to_dict()}
    return SimpleNamespace(spec_db=spec, mask_db=np.stack([plan_mask_db(plan) for plan in plans]), meta=meta, iq=iq)


def fake_cancel(iq, plan, config=None):
    """Residual depends on the co IQ and on the declared plan, so a stale residual is distinguishable."""
    plan = list(plan)
    rng = np.random.default_rng([int(abs(float(np.asarray(iq)[0, 0].real)) * 1e6) % 100000,
                                 *(int(abs(c.f0)) % 100003 for c in plan), len(plan)])
    return SimpleNamespace(residual_iq=iq, residual_db=rng.normal(-95, 1, (128, 512)).astype(np.float32),
                           carriers=[{"plan_index": i, "f0": c.f0, "symbol_rate": c.symbol_rate, "mod": c.mod,
                                      "samples_per_symbol": 60, "symbols_per_snapshot": 200, "timing_samples": [0] * 128,
                                      "gain_power_db_mean": 0.0, "decision_snr_db_median": 20.0,
                                      "basis": "observed IQ and operator plan only"} for i, c in enumerate(plan)],
                           config=config)


def install_fakes(mp):
    mp.setattr(scenes, "simulate_dual", _simulate)
    mp.setattr(ds, "cancel_planned_carriers", fake_cancel)
    mp.setattr(rp, "cancel_planned_carriers", fake_cancel)
    mp.setattr(ds, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})
    mp.setattr(md, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})


EXPERIMENT = B2ExperimentConfig(views=("co", "dual_residual"),
                                training={"epochs": 1, "batch": 8, "width": 4, "seed": 0, "center_loss_weight": 0.005,
                                          "augment": False})


def workspace() -> Path:
    """known / matched artifacts and a frozen run directory, built once per pytest process."""
    global _WORKSPACE
    if _WORKSPACE is None:
        root = Path(tempfile.mkdtemp(prefix="a5-tests-"))
        atexit.register(shutil.rmtree, root, ignore_errors=True)
        with pytest.MonkeyPatch.context() as mp:
            install_fakes(mp)
            ds.generate_b2_dataset(root / "known", roles=BASE_ROLES, limit_groups=2, groups_per_shard=1,
                                   cancellation=CANCELLATION)
            md.generate_b2_matched_dataset(root / "matched", root / "known", B2Config(), limit_groups=2,
                                           groups_per_shard=1, cancellation=CANCELLATION)
            run_b2_experiment(EXPERIMENT, root / "known", root / "runs", log=lambda *_: None)
        _WORKSPACE = root
    return _WORKSPACE


def copy_of(name: str, tmp_path: Path) -> Path:
    target = tmp_path / name
    shutil.copytree(workspace() / name, target)
    return target
