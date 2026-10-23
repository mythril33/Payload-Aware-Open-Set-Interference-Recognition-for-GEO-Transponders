"""Read-only independent P27 arithmetic on three existing train observations.

Run from the repository root. No fitting, calibration, generation or test
selection occurs. This exact body was executed in a Python heredoc; the
internal computation timer begins after imports, and the shell measurement
also includes interpreter startup and imports.
"""
import numpy as np, json, resource, time
from pathlib import Path
from geoml.b2_expert import extract_features, FEATURE_NAMES

start=time.perf_counter()
path=sorted(Path('data/b2-readiness-known/train').glob('part-*.npz'))[0]
with np.load(path,allow_pickle=False) as raw:
    spec=raw['spec'][:3].astype(np.float64)
    mask=raw['mask'][:3].astype(np.float64)
    residual=raw['residual'][:3].astype(np.float64)
f=(np.arange(512)-256)*0.1875
band=(f>=-18)&(f<=18)
manual=[]
for s,m,r in zip(spec,mask,residual):
    cores=[m[p,band]>-3 for p in (0,1)]
    streams=[10**(s[0][:,band]/10),10**(s[1][:,band]/10),10**(r[:,band]/10)]
    reference=np.mean(streams[0][:,cores[0]])
    row=[]
    for power,core in zip(streams,[cores[0],cores[1],cores[0]]):
        bandmean=np.sum(power)/(128*193)
        steady=np.sum(power,axis=0)/128
        snapshot=np.sum(power,axis=1)/193
        centroid=np.sum(power*f[band][None,:],axis=1)/np.sum(power,axis=1)
        row += [10*np.log10(bandmean/reference),
                10*np.log10(np.mean(power[:,core])/reference),
                10*np.log10(np.mean(power[:,~core])/reference),
                10*np.log10(np.max(steady)/bandmean),
                10*np.log10(np.max(power)/bandmean),
                np.std(snapshot,ddof=0)/np.mean(snapshot),
                np.exp(np.sum(np.log(steady))/193)/np.mean(steady),
                np.std(centroid,ddof=0)]
    row += [np.count_nonzero(core)/193 for core in cores]
    manual.append(row)
manual=np.array(manual)
actual=extract_features(spec,mask,residual)
absolute=np.abs(actual-manual)
position=np.unravel_index(np.argmax(absolute),absolute.shape)
assert np.allclose(actual,manual,atol=1e-11,rtol=1e-11)
print(json.dumps({'n_observations':len(spec),'n_features':len(FEATURE_NAMES),
    'max_abs_feature_discrepancy':float(absolute.max()),
    'largest_difference_feature':FEATURE_NAMES[position[1]],
    'computation_seconds':time.perf_counter()-start,
    'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    'method':'raw train NPZ; direct power sums/log-ratios; direct weighted centroid; independent temporal SD and geometric mean',
    'model_fitting':False,'threshold_fitting':False},indent=2))
