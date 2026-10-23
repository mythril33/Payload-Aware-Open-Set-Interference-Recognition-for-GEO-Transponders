"""Read-only arithmetic audit; run from the repository root.

The recorded execution used this body in a Python heredoc with:
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    /workspace/.venvs/geosim/bin/python - <<'PY'

Timing starts after imports and includes reading saved JSON, raw artifact
arrays, independent arithmetic and assertions. The recorded wall_seconds
ends before the assertions/JSON print below (same boundary as the original
heredoc). Recorded subprocess wall includes interpreter startup/imports.
No geosim/geoml helper or scorer is imported.
"""
import json
import resource
import time
from pathlib import Path
import numpy as np

started = time.perf_counter()
run = Path('runs/b2-e3a-edsc-smoke')
saved = json.loads((run/'scores.json').read_text())
calibration = json.loads((run/'calibration.json').read_text())['methods']['edsc']
frequencies = (np.arange(512, dtype=np.float64)-256) * (96_000_000.0/512)
in_band = np.abs(frequencies) <= 18_000_000.0
assert in_band.sum() == 193


def independently_read(root, role, target):
    values, labels, groups = [], [], []
    for shard in sorted((Path(root)/role).glob('part-*.npz')):
        with np.load(shard, allow_pickle=False) as arrays:
            for i in range(len(arrays['seed'])):
                spectrum = arrays['spec'][i,0].astype(np.float64)
                residual = arrays['residual'][i].astype(np.float64)
                core = (arrays['mask'][i,0] > -3.0) & in_band
                observed_density = (10.0 ** (spectrum[:,core]/10.0)).mean()
                residual_density = (10.0 ** (residual[:,in_band]/10.0)).mean()
                values.append(10.0*np.log10(residual_density/observed_density))
                labels.append(int(arrays[target][i]))
                groups.append(int(arrays['seed'][i]))
    return np.array(values), np.array(labels), np.array(groups)


cv, cy, cg = independently_read('data/b2-readiness-known', 'val-calib', 'label')
clean_cv = cv[cy == 0]
threshold = float(np.sort(clean_cv)[int(np.ceil((len(clean_cv)-1)*0.95))])
checks = {}
for key, root, role, target in (
    ('known','data/b2-readiness-known','test','label'),
    ('unknown','data/b2-readiness-test','test','family'),
    ('matched','data/b2-readiness-matched','test-matched','label'),
):
    values, labels, groups = independently_read(root, role, target)
    ids = np.column_stack((groups,labels)).tolist()
    assert ids == saved['sample_ids'][key]
    reference = np.array(saved['methods']['edsc'][key])
    difference = float(np.max(np.abs(values-reference)))
    checks[key] = {'n':len(values), 'max_abs_score_discrepancy_db':difference}
    if key == 'known':
        alarm = values > threshold
        checks[key].update(clean_alarms=int(alarm[labels == 0].sum()),n_clean=int((labels == 0).sum()),event_alarms=int(alarm[labels != 0].sum()),n_event=int((labels != 0).sum()))
result = {
    'independent_method':'raw np.load; float64 direct linear PSD means; log10 of ratio; manual frequency grid; sorted higher quantile',
    'calibration_clean_scores_db':clean_cv.tolist(),
    'threshold_db':threshold,
    'stored_threshold_db':calibration['threshold'],
    'threshold_abs_discrepancy_db':abs(threshold-calibration['threshold']),
    'calibration_false_alarms':int((clean_cv > threshold).sum()),
    'n_calibration_clean':len(clean_cv),
    'checks':checks,
    'wall_seconds':time.perf_counter()-started,
    'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
}
assert result['calibration_false_alarms'] == 0
assert checks['known']['clean_alarms'] == 1 and checks['known']['n_clean'] == 2
assert checks['known']['event_alarms'] == 13 and checks['known']['n_event'] == 14
assert all(v['max_abs_score_discrepancy_db'] < 1e-12 for v in checks.values())
assert result['threshold_abs_discrepancy_db'] < 1e-12
print(json.dumps(result,indent=2,allow_nan=False))
