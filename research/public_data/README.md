# Public interference data pilot

This research directory is independent of frozen B2/1. It imports no B2 data,
generates no RF, trains no neural model and uses no GPU. Only generic NumPy metric
arithmetic is reused from `geoml`. Read the current [P8 audit](../../docs/plan/P8_dis_veri.md).

`protocol.json` is fixed **before the first test metrics**. Three scores are
reported without choosing a winner or changing direction from test performance:
stored native level, clean-train standardized diagonal distance and supervised
binary centroid margin. Thresholds use only clean records in the deterministic
25% calibration partition of publisher training IDs. The nominal false-alarm
target is 5%; the empirical count is reported separately. Tiny populations do
not establish 5% precision. No hyperparameter search is performed.

## Available sources and representations

- SmartSpace on-board: full/reduced FFT magnitude/complex; native five-bit labels
  indicate clean or one of five **subband locations**. Download folders currently
  require Microsoft authentication. `smartspace.py` is a fixture-tested MAT import
  contract with explicit variable keys/axes; the official raw container has not
  been inspected. It rejects HTML and never guesses a label variable.
- SmartSpace NGSO: clean-only train/validation, mixed test, 800 magnitude values;
  not IQ. The test-positive numeric value must be explicitly source-verified.
  Appended label/INR/off-axis columns are not inputs. No actual SmartSpace metric
  is available while raw downloads remain blocked.
- Fraunhofer LC: observed receiver features. Only ss/SDR/kurtosis columns enter
  the six summaries; GPS coordinates, PRNs, azimuth/elevation, record ID, power
  and jammer metadata do not. Empty arrays are explicit abstentions.
- Fraunhofer FIOT: rendered RGB spectrogram crops, **not calibrated PSD or IQ**.
  Color means/deviations and pixel gradients describe the released image. Never
  interpret squared pixel values as watts. Three channels are colors, not
  polarizations. Crop suffixes 0..5 share their five-digit parent ID.

The Fraunhofer API license field says CC BY-SA 4.0, while the author README says
CC BY-NC-SA 4.0. Retain this disagreement; local noncommercial research follows
the stricter statement. Do not redistribute raw files here. SmartSpace is
research-only. Exact source links/hashes are recorded in P8/results.

## Reproduce the bounded Fraunhofer runs

Use Python 3.12+, NumPy, SciPy and Matplotlib (`pip install -e '.[dev]'`). Optional
archive extraction used `py7zr==0.22.0`; it is not a runtime loader dependency.
Keep all third-party files outside Git. The author source is pinned to
`FelixOtt94/FIOT_LC_laboratory@2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26`.
Obtain `GNSS_dataset/train_LC.txt`, `test_LC.txt`, `train_FIOT.txt`, `test_FIOT.txt`
from that commit. Real binary archives (the small Zenodo ZIP contains pointers):

- LC: `https://media.githubusercontent.com/media/FelixOtt94/FIOT_LC_laboratory/2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26/GNSS_dataset/data_LC/data.7z`
  SHA-256 `466a4788ce9780d9374451eb548694869656b043f760ffaa2218254dd2bada54` (2,216,728 B).
- FIOT: same commit/path with `data_FIOT/data.7z`, SHA-256
  `f1a062ccfffdd4e0da31ed92af2f8c1c4386090170c3fa6644fee5caa3ffa2d8` (364,187,305 B).

Extract LC into a separate directory (the archive uses `data_lc/`). For FIOT,
the full expanded archive is **10.04 GB**: do not expand it all. Read publisher
split metadata, choose crop 0 for all 1121 parent IDs, and extract only these
targets (1,673,787,520 B, below the 2-GiB/300-s/two-core cap).
The experiment repeats this exact metadata-only selection and refuses missing
selected files. It never changes the subset because of a result or an empty file.
The initial 256-parent access probe was expanded before any detector metrics:
it supplied only seven clean calibration records and sixteen clean test records.
The final protocol removes that arbitrary subsample and retains all publisher
parent IDs, without changing the scoring directions or hash calibration rule.

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0
python -m research.public_data.baseline --kind lc --data /path/to/data_lc \
  --train /path/to/train_LC.txt --test /path/to/test_LC.txt --out /path/to/lc.json
python -m research.public_data.baseline --kind fiot --data /path/to/selected_crop0/data \
  --train /path/to/train_FIOT.txt --test /path/to/test_FIOT.txt --out /path/to/fiot.json
python -m pytest -q -rs research/public_data/tests
```

One NPY is loaded at a time and reduced to a small feature row. Publisher test
never fits centers/scales, positive centroids or thresholds. All retained crops
of a parent stay together; the selected experiment uses one crop per parent.
Repeated nonempty train/test bytes are rejected. Parent-ID bootstrap intervals
condition on published recordings; acquisition-day/session independence is unknown.
Rates on nonempty LC records are conditional; coverage and a sensitivity lower
bound counting empty positive records as undetected are also reported.

These results concern measured **GNSS** interference in supplied recording
partitions. They neither validate GEO ground truth nor supply operator plans,
dual-polarization observations, payload/cancellation residuals or B2 labels.
