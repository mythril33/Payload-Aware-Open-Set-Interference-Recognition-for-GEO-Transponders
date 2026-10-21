---
name: physics-check
description: Run and interpret the numerical/physical sanity checks of the simulator, payload chain and cancellation residual before trusting new simulator or feature code.
---

# Physics check

Use after any change under `src/geosim/` or before scaling a generation run.

1. Regression identity: run `python -m pytest -q tests/test_chain.py tests/test_active_carriers.py
   tests/test_b2_scenarios.py tests/test_cancellation.py`. Default A1/B2 outputs must stay bit-identical.
2. Payload: `python scripts/npr_check.py` (NPR slope ≈ 1.25 dB/dB for `dvbs2_nl` at IBO 10–14 dB;
   `dvbs2_lin` shows an artificial distortion floor — known limit).
3. Cancellation residual on a B2-feat artifact:
   `python scripts/check_b2_cancellation.py --data <dir> --out <json>`. Expect: residual gap-floor
   shift ≈ 0 dB, in-band depth limited by C/N (reaches the noise floor at C/N ≤ 30 dB), lower depth for
   overdrive/cross_pol (physical), paired CuC ΔPSD larger after cancellation than before.
4. Missing-carrier twins: `python scripts/check_b2_base.py --data <dir> --out <json> --check-missing`
   (plans and nominal gain unchanged; active power falls; clean actual IBO rises).
5. Report numbers with n, protocol name and data fingerprint. Never call a pilot a benchmark result.
