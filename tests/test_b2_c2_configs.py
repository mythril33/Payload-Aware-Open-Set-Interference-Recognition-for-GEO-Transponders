"""B2-C2-ablation/1: committed configurations and the pre-declared matrix must equal their generators and stay inside the bounded caps."""
import json
from pathlib import Path

import pytest

from geoml import b2_c2, b2_execution as execution
from geoml.b2_experiment import B2ExperimentConfig

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = {"canonical": ["co", "dual", "dual_residual"], "dual_matched": ["dual_planmask", "dual_noplan"],
           "co_matched": ["co_planmask", "co_noplan"]}


def test_the_committed_smoke_configurations_are_exactly_the_generated_ones_and_nothing_else():
    files = sorted(p.name for p in (ROOT / "configs" / "c2").iterdir())
    assert files == sorted(f"smoke_{name}_seed{seed}.json" for name in BUNDLES for seed in b2_c2.SEEDS)
    for name, arms in BUNDLES.items():
        for seed in b2_c2.SEEDS:
            raw = json.loads((ROOT / "configs" / "c2" / f"smoke_{name}_seed{seed}.json").read_text())
            assert raw == b2_c2.bundle_config(arms, seed, "smoke")
            config = B2ExperimentConfig.from_file(ROOT / "configs" / "c2" / f"smoke_{name}_seed{seed}.json")
            assert config.views == tuple(arms) and all(config.train_config(v).seed == seed for v in config.views)
            execution._caps(config)                                  # within the bounded CPU smoke caps


def test_smoke_configurations_carry_the_declared_recipes():
    for seed in b2_c2.SEEDS:
        canonical = B2ExperimentConfig.from_file(ROOT / "configs" / "c2" / f"smoke_canonical_seed{seed}.json")
        assert canonical.plan_consistency is True and all(canonical.train_config(v).level == "carrier" and
                                                          canonical.train_config(v).plan_shift_fraction == 0.15 for v in canonical.views)
        for name in ("dual_matched", "co_matched"):
            matched = B2ExperimentConfig.from_file(ROOT / "configs" / "c2" / f"smoke_{name}_seed{seed}.json")
            assert matched.plan_consistency is False
            for view in matched.views:
                cfg = matched.train_config(view)
                assert (cfg.level, cfg.plan_consistency, cfg.plan_shift_fraction, cfg.center_loss_weight) == ("absolute", False, 0.0, 0.005)


def test_the_matrix_file_is_the_generated_plan_and_is_neither_approved_nor_loadable():
    path = ROOT / "docs" / "plan" / "b2_c2_experiment_matrix.json"
    text = path.read_text()
    assert text == json.dumps(b2_c2.matrix(), indent=1, sort_keys=True, allow_nan=False) + "\n"
    matrix = json.loads(text, parse_constant=lambda value: pytest.fail(f"nonfinite constant {value}"))
    assert matrix["status"] == "UNAPPROVED_NOT_EXECUTABLE" and matrix["production_authorized"] is False and matrix["benchmark_complete"] is False
    assert len(matrix["fits"]) == 21 and matrix["roster"]["declared_fits"]["total_fits"] == 21 and matrix["roster"]["primary_scorer"] is None
    assert matrix["sample_passes"]["per_fit"] == 360000 and matrix["sample_passes"]["all_21_fits"] == 21 * 360000
    assert {(f["arm"], f["seed"]) for f in matrix["fits"]} == {(a, s) for a in b2_c2.ARMS for s in b2_c2.SEEDS}
    with pytest.raises(ValueError):
        B2ExperimentConfig.from_file(path)                           # a plan, not a runner configuration


def test_every_production_scale_entry_is_refused_by_the_bounded_executor_and_every_smoke_entry_is_not():
    matrix = json.loads((ROOT / "docs" / "plan" / "b2_c2_experiment_matrix.json").read_text())
    for arm, scales in matrix["arms"].items():
        for raw in scales["production"]:
            assert (raw["training"]["width"], raw["training"]["epochs"]) == (16, 30)
            with pytest.raises(ValueError, match="bounded CPU smoke caps"):
                execution._caps(B2ExperimentConfig(**raw))
        for raw in scales["smoke"]:
            execution._caps(B2ExperimentConfig(**raw))
