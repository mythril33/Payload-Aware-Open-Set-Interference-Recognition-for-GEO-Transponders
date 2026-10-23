"""Stand-in child for the supervisor tests: fast fake physics, then the REAL generator CLI.

    python tests/b2_supervisor_standin.py <known|test|matched> <generator args...>

It patches only the physical chain (``simulate_dual``) and the canceller with the deterministic fakes the artifact tests
use, so the real request/shard/descriptor/manifest code of ``geosim.b2_dataset``, ``b2_test_dataset`` and
``b2_matched_dataset`` runs unchanged and produces genuinely valid (non-physical) shards. Failure injection is driven by
environment variables so a test can exercise crashes, orphans, signals, slowness and resource use of a real child:

    STANDIN_ONLY_STAGE      apply every knob only to this stage
    STANDIN_ONCE_MARKER     path; the crash/orphan/signal knobs fire only while the file does not exist (then create it)
    STANDIN_START_DELAY_S   sleep before generating            STANDIN_OBS_DELAY_S   sleep per simulated observation
    STANDIN_EXIT_AFTER_OBS  os._exit(STANDIN_EXIT_CODE) after N observations (a mid-shard crash)
    STANDIN_ORPHAN_AT       os._exit(9) right before shard K's descriptor is written (data files exist, descriptor does not)
    STANDIN_SELF_SIGNAL     send this signal number to itself after STANDIN_SELF_SIGNAL_AFTER observations
    STANDIN_ALLOC_MB        touch this many MiB at start              STANDIN_BURN_CPU_S   busy-loop this many seconds
    STANDIN_PID_FILE        write the pid here at start
"""
import importlib
import os
import signal
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

MODULES = {"known": "geosim.b2_dataset", "test": "geosim.b2_test_dataset", "matched": "geosim.b2_matched_dataset"}


def _env_float(name, default=0.0):
    return float(os.environ.get(name, default))


def _knobs_active(stage):
    only = os.environ.get("STANDIN_ONLY_STAGE")
    if only and only != stage:
        return False
    marker = os.environ.get("STANDIN_ONCE_MARKER")
    if marker:
        return not Path(marker).exists()
    return True


def _consume_once():
    marker = os.environ.get("STANDIN_ONCE_MARKER")
    if marker:
        Path(marker).write_text("fired\n")


def fake_meta(cfg, plans, interferers, active_carriers, calibration, downlink):
    power = [sum(c.power for c, keep in zip(plan, active) if keep) for plan, active in zip(plans, active_carriers)]
    return {"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
            "has_interferer": [event is not None for event in interferers],
            "has_downlink_interferer": [event is not None for event in downlink],
            "downlink_interference_reference_power": [0.1, 0.1],
            "active_carriers": [list(active) for active in active_carriers],
            "active_planned_power": power, "nominal_planned_power": [1., 1.], "gain_mode": "fixed_nominal_planned_power",
            "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10., "omux_output_power": 0.1,
                       "receiver_noise_psd": 1e-10, "zero_drive": False} for _ in range(2)],
            "receiver_calibration_applied": True, "receiver_calibration": calibration.to_dict()}


def main(argv):
    stage, args = argv[1], argv[2:]
    from geosim import b2_dataset, b2_scenarios
    from geosim.plan import plan_mask_db
    active = _knobs_active(stage)
    state = {"observations": 0, "fired": False}

    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq, downlink_interferers=(None, None)):
        if active:
            state["observations"] += 1
            delay = _env_float("STANDIN_OBS_DELAY_S")
            if delay:
                time.sleep(delay)
            crash_after = os.environ.get("STANDIN_EXIT_AFTER_OBS")
            if crash_after and state["observations"] >= int(crash_after):
                _consume_once()
                os._exit(int(os.environ.get("STANDIN_EXIT_CODE", "7")))
            signal_after = os.environ.get("STANDIN_SELF_SIGNAL")
            if signal_after and state["observations"] >= int(os.environ.get("STANDIN_SELF_SIGNAL_AFTER", "1")):
                _consume_once()
                os.kill(os.getpid(), int(signal_after))
                time.sleep(5)
        t0 = np.arange(cfg.co.n_snap) * cfg.co.snap_interval
        for event in (*interferers, *downlink_interferers):
            if event is not None:
                event(np.random.default_rng(0), t0, 512, 288e6)
        iq = None
        if keep_iq:
            rng = np.random.default_rng([int(cfg.co.seed), 7])
            iq = (rng.standard_normal((2, 128, 4096)) + 1j * rng.standard_normal((2, 128, 4096))).astype(np.complex64)
        return SimpleNamespace(spec_db=np.full((2, 128, 512), -80, np.float32),
                               mask_db=np.stack([plan_mask_db(plan) for plan in plans]),
                               meta=fake_meta(cfg, plans, interferers, active_carriers, calibration, downlink_interferers), iq=iq)

    def cancel(iq, plan, config=None):
        return SimpleNamespace(residual_iq=iq, residual_db=np.full((128, 512), -95, np.float32),
                               carriers=[{"plan_index": i, "f0": c.f0, "symbol_rate": c.symbol_rate, "mod": c.mod,
                                          "samples_per_symbol": 60, "symbols_per_snapshot": 200, "timing_samples": [0] * 128,
                                          "gain_power_db_mean": 0.0, "decision_snr_db_median": 20.0,
                                          "basis": "observed IQ and operator plan only"} for i, c in enumerate(plan)],
                               config=config)

    b2_scenarios.simulate_dual = simulate
    b2_dataset.cancel_planned_carriers = cancel
    module = importlib.import_module(MODULES[stage])
    if active and os.environ.get("STANDIN_ORPHAN_AT") is not None:
        wanted = f"shard-{int(os.environ['STANDIN_ORPHAN_AT']):05d}.json"
        real = module._atomic_json

        def guarded(path, value):
            if Path(path).name == wanted and Path(path).parent.name != "":
                _consume_once()
                os._exit(9)                                  # data files are renamed into place, the descriptor never lands
            return real(path, value)

        module._atomic_json = guarded
    if os.environ.get("STANDIN_PID_FILE"):
        Path(os.environ["STANDIN_PID_FILE"]).write_text(str(os.getpid()))
    print(f"standin env CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')!r} "
          f"OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')!r}", flush=True)
    if active:
        start_delay = _env_float("STANDIN_START_DELAY_S")
        if os.environ.get("STANDIN_ALLOC_MB"):
            block = bytearray(int(float(os.environ["STANDIN_ALLOC_MB"]) * 2 ** 20))
            block[::4096] = b"x" * len(block[::4096])
            state["block"] = block
        burn = _env_float("STANDIN_BURN_CPU_S")
        if burn:
            end = time.process_time() + burn
            while time.process_time() < end:
                pass
        if start_delay:
            time.sleep(start_delay)
    module.main(args)


if __name__ == "__main__":
    main(sys.argv)
