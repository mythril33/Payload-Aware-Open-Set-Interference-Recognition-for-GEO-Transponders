import copy
import numpy as np
import pytest

from research.public_data import baseline as B


def test_lc_quality_features_do_not_read_position_id_or_truth_metadata():
    x = np.zeros((10, 308))
    x[:, 57:98] = 30
    x[:, 180:244] = 2
    x[:, 244:] = 3
    expected = [30, 0, 1, 0, 2, 3]
    assert np.allclose(B.lc_features(x), expected)
    x[:, :57] = 1e6
    x[:, 98:180] = -1e6
    assert np.allclose(B.lc_features(x), expected)


def test_rgb_levels_are_not_squared_as_power_and_feature_order_is_fixed():
    image = np.ones((512, 243, 3), dtype=np.int32) * [30, 60, 120]
    assert np.allclose(B.fiot_features(image), [30, 60, 120, 0, 0, 0, 0, 0])
    model = B.fit_scores([[30,60,120],[31,61,121],[80,80,80]], [0,0,1], level_columns=(0,1,2))
    assert B.score([[30,60,120]], model)["native_level"][0] == 70


def test_smartspace_magnitude_power_is_relative_and_complex_phase_does_not_change_statistic():
    a = np.full((2,100), 2+0j)
    assert np.allclose(B.smartspace_features(a)[:,0], 4)
    assert np.allclose(B.smartspace_features(a), B.smartspace_features(a*1j))
    with pytest.raises(ValueError):
        B.smartspace_features(np.ones((2,802)))


def test_clean_distance_and_supervised_margin_have_explicit_directions():
    model = B.fit_scores([[0,0],[2,2],[4,4]], [0,0,1])
    scored = B.score([[1,1],[3,3],[4,4]], model)
    assert np.allclose(scored["clean_diagonal_distance"], [0,4,9])
    assert np.allclose(scored["binary_centroid_margin"], [-9,3,9])
    assert model["n_fit_clean"] == 2 and model["n_fit_positive"] == 1


def test_tied_rank_and_strict_alarm_are_different_conventions():
    report = B.evaluate(np.array([0,1]), [2,2], ["a","b"], 2, bootstrap=30)
    assert report["auroc"] == .5 and report["average_precision"] == .5
    assert report["detection"]["count"] == report["false_alarm"]["count"] == 0
    assert report["fpr_at_95_tpr"] == 1
    assert report["oscr"] is None


def test_repeated_crops_are_bootstrapped_together_and_absent_classes_are_null():
    report = B.evaluate(np.array([0,0,1,1]), [0,0,1,1], ["a","a","b","b"], .5,
                        class_map={0:"clean",1:"native subtype",7:"CW"}, bootstrap=100)
    assert report["bootstrap"]["groups"] == 2
    assert 0 < report["bootstrap"]["valid_draws"]["auroc"] < 100
    assert report["per_native_class"]["7"]["rate"] is None
    assert report["per_native_class"]["7"]["denominator"] == 0
    assert report["per_native_class"]["1"]["name"] == "native subtype"


def test_empty_record_abstentions_reduce_reported_coverage_and_lower_bound():
    report = B.evaluate(np.array([0,1]), [0,3], ["a","b"], 1, bootstrap=20, published_counts={0:2,1:3})
    assert report["coverage"]["fraction"] == 2/5
    assert report["coverage"]["abstentions"] == 3
    assert report["coverage"]["detected_positive_over_all_published_positive"]["rate"] == 1/3


def fixture():
    ids = np.array(["parent-"+str(i) for i in range(120)])
    y = np.arange(120) % 2
    x = np.c_[np.arange(120)%7+y*2, np.arange(120)%11]
    return {"train":{"x":x,"y":y,"groups":ids},
            "test":{"x":np.array([[0.,1.],[6.,3.],[4.,2.],[8.,7.]]),"y":np.array([0,1,0,1]),"groups":np.array(["a","b","c","d"],dtype=object)}}


def test_test_values_and_labels_cannot_change_fitted_statistics_or_calibration():
    data = fixture()
    first = B.experiment(data, bootstrap=20)
    changed = copy.deepcopy(data)
    changed["test"]["x"] += 100
    changed["test"]["y"] = 1-changed["test"]["y"]
    second = B.experiment(changed, bootstrap=20)
    assert first["model"] == second["model"]
    assert {k:v["threshold"] for k,v in first["results"].items()} == {k:v["threshold"] for k,v in second["results"].items()}
    assert first == B.experiment(data, bootstrap=20)


def test_publisher_recording_cannot_cross_train_test_even_with_different_crops():
    data = fixture()
    data["test"]["groups"][0] = data["train"]["groups"][0]
    with pytest.raises(ValueError, match="overlap"):
        B.experiment(data, bootstrap=10)


def test_clean_calibration_population_is_required():
    data = fixture()
    data["train"]["y"][:] = 1
    with pytest.raises(ValueError, match="calibration"):
        B.experiment(data, bootstrap=10)


@pytest.mark.parametrize("bad", [np.nan,np.inf,-np.inf])
def test_nonfinite_observations_are_not_imputed_from_test(bad):
    with pytest.raises(ValueError):
        B.fit_scores([[0,1],[bad,2]], [0,0])


def test_clean_only_training_still_supports_anomaly_scoring_without_a_positive_centroid():
    model = B.fit_scores([[0,1],[1,2],[2,1]], [0,0,0])
    assert set(B.score([[5,5]],model)) == {"native_level","clean_diagonal_distance"}


def test_changed_protocol_cannot_misdescribe_executed_fixed_features(tmp_path, monkeypatch):
    altered = tmp_path/"protocol.json"
    altered.write_text(B.PROTOCOL_PATH.read_text().replace('"pfa_target": 0.05','"pfa_target": 0.5'))
    monkeypatch.setattr(B,"PROTOCOL_PATH",altered)
    with pytest.raises(ValueError,match="protocol differs"):
        B.experiment(fixture(),bootstrap=10)
