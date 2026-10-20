"""Frozen class/role contracts, incomplete-stage scope and config identity."""
import json

import numpy as np
import pytest

from geosim.b2_protocol import (BASE_PROTOCOL, BASE_ROLES, BENIGN_TEST_FAMILIES, B2Config,
                               LABELS, NEAR_UNKNOWN, PROTOCOL, ROLE_COUNTS, ROLE_STARTS,
                               protocol_contract, require_base_group, role_for_group, scenario_ids)
from geosim.dataset import PROTOCOLS
from geosim.dual_dataset import ROLE_STARTS as D1_STARTS
from geosim.event_dataset import ROLE_STARTS as E1_STARTS


def test_frozen_labels_roles_and_test_families_remain_distinct():
    assert PROTOCOL == "B2/1" and BASE_PROTOCOL == "B2-base/1"
    assert LABELS == ("clean", "cw", "swept_cw", "unauthorized", "overdrive", "cross_pol",
                      "adjacent_satellite", "carrier_under_carrier")
    assert [ROLE_COUNTS[role] for role in BASE_ROLES] == [1500, 150, 150, 500]
    assert "adjacent_satellite_downlink" in NEAR_UNKNOWN
    assert BENIGN_TEST_FAMILIES == ("cid_overlay",)
    assert not set(LABELS) & set(NEAR_UNKNOWN)
    assert not set(LABELS) & set(BENIGN_TEST_FAMILIES)
    assert protocol_contract()["benchmark_complete"] is False


def test_group_ranges_and_pilot_prefixes_do_not_cross_roles_or_prior_protocols():
    seen = set()
    for role, start in ROLE_STARTS.items():
        groups = scenario_ids(role)
        assert groups == list(range(start, start + ROLE_COUNTS[role]))
        assert not seen & set(groups)
        seen.update(groups)
        assert scenario_ids(role, 2) == groups[:2]
        assert role_for_group(start) == role_for_group(groups[-1]) == role
    for splits in PROTOCOLS.values():
        for split in splits.values():
            assert seen.isdisjoint(split.seeds)
    # U1 reserves 900000..999999; D1/E1 each reserve up to 100000 groups per role.
    for start in (900_000, *D1_STARTS.values(), *E1_STARTS.values()):
        assert not any(start <= group < start + 100_000 for group in seen)
    assert require_base_group(ROLE_STARTS["val-calib"]) == "val-calib"
    with pytest.raises(ValueError, match="test-matched"):
        require_base_group(ROLE_STARTS["test-matched"])


@pytest.mark.parametrize("group", [True, -1, 3_099_999, 3_001_500, 3_300_150, 1e6, "3000000", None])
def test_invalid_or_unreserved_groups_fail(group):
    with pytest.raises(ValueError):
        role_for_group(group)


@pytest.mark.parametrize("role,limit", [("unknown", 1), ([], 1), ("train", 0), ("train", True),
                                        ("val-select", 151), ("test", 1.5)])
def test_invalid_role_or_pilot_limit_fails(role, limit):
    with pytest.raises(ValueError):
        scenario_ids(role, limit)


def test_json_config_roundtrip_and_contract_cannot_mutate_global_definitions(tmp_path):
    config = B2Config()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.to_dict(), allow_nan=False))
    assert B2Config.from_file(path) == config
    contract = protocol_contract()
    contract["labels"].clear()
    contract["role_starts"]["train"] = 0
    assert len(LABELS) == 8 and ROLE_STARTS["train"] == 3_000_000
    assert B2Config(n_snap=np.int64(128)).to_dict()["n_snap"] == 128


@pytest.mark.parametrize("change", [{"bandwidth": 72e6}, {"n_snap": 16}, {"n_snap": True},
                                    {"snap_interval": 0.02}, {"satellite_linewidth_hz": 0},
                                    {"nominal_xpd_db": 20}, {"drop_probability": 0.2},
                                    {"drop_probability": np.nan}, {"receiver_phase_rad": [0, 0]},
                                    {"calibration_samples": 1}, {"calibration_seed": True}])
def test_changed_frozen_physics_and_invalid_instrument_settings_fail(change):
    with pytest.raises(ValueError):
        B2Config(**change)


@pytest.mark.parametrize("raw", ['[]', '{"surprise": 1}', '{"drop_probability": NaN}',
                                '{"drop_probability": 1e999}'])
def test_invalid_config_json_fails(tmp_path, raw):
    path = tmp_path / "config.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        B2Config.from_file(path)
