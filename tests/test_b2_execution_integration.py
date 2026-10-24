"""Native E1 artifact/phase composition on deterministic stand-in physics only."""
import hashlib
import json

from geosim import b2_dataset as ds
from geosim.cancellation import CancellationConfig
from geoml import b2_execution as execution
from geoml.b2_experiment import B2ExperimentConfig
from test_b2_artifacts import feature_generator, generator  # noqa: F401
from test_b2_role_loader import _refuse_unrequested_reads


def _hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_native_artifact_train_calibrate_freeze_evaluate(tmp_path, monkeypatch, feature_generator):
    """Real writer, validator, source identity, trainer and frozen-state readers compose.

    RF physics/cancellation are stand-ins. This checks execution, never detection quality.
    """
    data = tmp_path / "data"
    ds.generate_b2_dataset(data, limit_groups=2, groups_per_shard=1,
                           cancellation=CancellationConfig())
    feature_generator["cancel"].clear()  # release the fixture's recorded transient IQ
    data_before = _hashes(data)
    allowed = {"train", "val-select"}
    seen = _refuse_unrequested_reads(monkeypatch, data, allowed)
    cfg = B2ExperimentConfig(views=("dual_residual",), training={
        "epochs": 1, "batch": 8, "width": 1, "time_pool": 8, "seed": 0,
        "center_loss_weight": 0.005, "plan_loss_weight": 1.,
        "plan_shift_fraction": 0., "augment": False})
    runs = tmp_path / "runs"
    trained = execution.fit_b2_models(cfg, data, runs, log=lambda *_: None)
    assert set(seen) == allowed
    assert trained["source"]["files_sha256"] == execution._source_identity()["files_sha256"]
    assert len(trained["source"]["files_sha256"]) > 20
    allowed.clear(); allowed.add("val-calib"); seen.clear()
    calibrated = execution.calibrate_b2_models(data, runs, log=lambda *_: None)
    assert set(seen) == {"val-calib"} and calibrated["n_calibration"] == 16
    assert calibrated["views"]["dual_residual"]["alarm"]["n_clean_calibration"] == 2
    inventory = tmp_path / "inventory.json"
    execution.freeze_inventory([runs], inventory, seeds=(0,), profile="fixture")
    frozen_before = _hashes(runs)
    inventory_before = inventory.read_bytes()
    allowed.clear(); allowed.add("test"); seen.clear()
    result = execution.evaluate_b2_inventory(data, inventory, tmp_path / "evaluation",
                                            profile="fixture", log=lambda *_: None)
    assert set(seen) == {"test"}
    assert result["inventory_cells"] == 1 and result["full_protocol_admission"] is False
    assert result["benchmark_complete"] is False and result["production_authorized"] is False
    assert result["models"][0]["metrics"]["accuracy"]["n_samples"] == 16
    assert _hashes(runs) == frozen_before and inventory.read_bytes() == inventory_before
    # Disable the access spy only after every phase has proved its actual content reads.
    monkeypatch.undo()
    assert _hashes(data) == data_before
    for path in (tmp_path / "evaluation").glob("*.json"):
        json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
