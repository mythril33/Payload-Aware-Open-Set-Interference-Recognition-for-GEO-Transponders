# RF-ML basics with PyTorch

## Bu proje ne işe yarar?

Bu proje, PyTorch ile radyo sinyalleri üzerinde makine öğrenmesini dört aşamada öğretir. Tüm veri bilgisayarda üretilen sentetik sinyaldir; gerçek saha verisi yoktur.

1. Aşama 1 (lesson 01): tensörleri ve otomatik türevi (autograd) öğrenirsin; gradyan inişini elle yazıp kütüphane optimizasyonuyla karşılaştırırsın.
2. Aşama 2 (lesson 02): bir sinyalin modülasyon türünü (BPSK, QPSK, 8PSK, 16QAM) farklı SNR değerlerinde tanıyan bir sinir ağı eğitirsin.
3. Aşama 3 (lesson 03): her cihaz aynı QPSK sinyalini gönderir; cihazları yalnızca donanım kusurlarından (IQ dengesizliği, PA doğrusalsızlığı, faz gürültüsü, DC ofseti) ayırt etmeyi denersin.
4. Aşama 4 (lesson 04): eğitimde görülmeyen modülasyonları (64QAM, 4PAM) "bilinmeyen" olarak reddetmeye çalışırsın; eşik yalnızca bilinen sınıfların doğrulama verisiyle belirlenir.

## Quick start

Run everything from this folder (`learning/rfml-basics`).

```bash
bash setup.sh          # creates .venv/, installs requirements.txt, prints a smoke check
bash setup.sh --test   # the same, then runs pytest -q
```

`setup.sh` uses `python3` unless you set `PYTHON=/path/to/python3`. `requirements.txt` does not pin versions. The commands below call `.venv/bin/python` directly, so you do not need to activate the environment.

```bash
.venv/bin/python lessons/01_tensors_autograd.py                  # stage 1: a few seconds
.venv/bin/python lessons/02_modulation_classification.py --quick
.venv/bin/python lessons/03_rf_fingerprint.py --quick
.venv/bin/python lessons/04_open_set.py --quick
```

For the interactive UI, run `.venv/bin/streamlit run app.py` from this folder. It opens in the browser and has four stages, each with its own controls and a run button. The UI and the lessons share the stage functions in `rfml/experiments.py`. The UI screens themselves are not covered by the tests.

`--quick` is a smoke run: 2 epochs and very few devices. It checks that the code runs and nothing more. In the checks made for this README, each quick run took from a few seconds to about 15 seconds. Drop the flag for the full run. Full runs train several networks for up to 25 epochs, so expect minutes rather than seconds on a CPU. The scripts set PyTorch to 4 threads.

Results go to two places. Each lesson writes `results/<lesson>.json` (strict JSON with the numbers) and `results/<lesson>.png` (plots). Quick and full runs write the same file names, and the JSON `"mode"` field says which one it is (`"quick"` or `"default"`). Check that field before you read a result. Set `RFML_RESULTS_DIR` to write to another folder instead. The numbers are not copied into this README: rerun the lessons to regenerate them.

## Learning path

| Stage | File | Question it answers | What to look at in the output |
|---|---|---|---|
| 1. Tensors and autograd | `lessons/01_tensors_autograd.py` | How do tensors and `backward()` produce gradients, and does a hand-written gradient descent match `nn.Linear` with `SGD`? | Section 3: the hand gradient and the autograd gradient agree. Section 4: gradient descent matches least squares. Section 5: the printed differences between the two code paths are tiny (the lesson asserts less than 1e-4). The PNG shows the loss curve and the fitted line. |
| 2. Modulation classification | `lessons/02_modulation_classification.py` | Does a classifier recognise modulations from devices it has never seen, and how does accuracy change with SNR? | The per-SNR table: the `n` column, the chance level printed in the header (1/4), the row marked "below training SNRs" (-6 dB), and the MLP and CNN1D columns. The `overall` row pools all SNR rows. The second table puts train accuracy (seen devices) next to overall test accuracy (unseen devices); a large gap means the model memorised the training devices. It also gives the val-select accuracy, the best epoch and the epoch count per model. |
| 3. RF fingerprinting | `lessons/03_rf_fingerprint.py` | Can a 1D ResNet recognise an individual device when every device sends the same QPSK? | The `impaired` and `ideal` columns, each with its own `n`, because the frame-level test split puts a different number of frames in each SNR bin. An empty bin has `n` 0 and prints `null`. The ideal column (identical devices) should sit near the chance level that the script prints. The split is frame-level (see section 2). |
| 4. Open-set recognition | `lessons/04_open_set.py` | Can a score reject modulations the model was never trained on, with a threshold set on known data only? | The table: threshold, known accepted (k/n), unknown rejected (k/n), AUROC, and closed-set accuracy on accepted frames (k/n). The PNG histograms show known and unknown scores with the threshold. The `Objectosphere + MSP` row is optimistic (see section 4). |

## 1. The synthetic physics model

The signal model is in `rfml/signals.py` (`make_frame`, `apply_impairments`) and `rfml/dataset.py` (`build_frames`). It is a simplified model, and there is no field data behind it. Time is measured in samples and symbols, so there is no sample rate in Hz. Each frame is 512 complex samples, stored as a float32 array of shape (2, 512): row 0 is I and row 1 is Q (`iq_channels`).

Each step below is applied in this order.

1. **Symbols.** `constellation(name)` returns the points of a modulation, scaled to unit average power. Unit power makes one SNR value mean the same for every modulation. Symbols are drawn uniformly at random. There is no Gray coding and no bit-error metric.
2. **Pulse shaping.** Symbols are placed every `sps = 8` samples, with zeros in between, and convolved with a unit-energy root-raised-cosine pulse (`root_raised_cosine`, roll-off beta = 0.35, span 6 symbols). With t in symbol periods, the taps are

   ```
   h(t) = [ sin(pi t (1 - beta)) + 4 beta t cos(pi t (1 + beta)) ] / [ pi t (1 - (4 beta t)^2) ]
   ```

   The code fills in the removable singularities at t = 0 and |4 beta t| = 1, and scales the taps so that sum(h^2) = 1. A frame is a window from the steady-state part of the stream, rescaled to unit average power.
3. **Rapp AM/AM power amplifier** (`apply_impairments`, step 1). The amplitude is compressed and the phase is unchanged:

   ```
   y = x / (1 + (|x| / A)^(2p))^(1 / (2p))
   ```

   A is `pa_saturation`, drawn per device from [1.0, 1.6], in units of the unit-RMS input. p is `pa_smoothness`, drawn from [2.0, 3.0].
4. **IQ imbalance** (step 2):

   ```
   y = mu * x + nu * conj(x)
   mu = (1 + g e^(-j phi)) / 2        nu = (1 - g e^(+j phi)) / 2
   ```

   g is `iq_gain` (Q gain relative to I, drawn from [0.9, 1.1]) and phi is `iq_phase_deg` (drawn from [-5, 5] degrees). The conj(x) term is the image at the mirror frequency. The image-to-signal amplitude ratio is |nu| / |mu|. For g = 1 this equals tan(phi / 2), which a test checks.
5. **Phase noise** (step 3). A random walk: theta[n] is the running sum of i.i.d. increments w_k ~ N(0, s^2), so y[n] is multiplied by exp(j theta[n]). The std s is drawn log-uniformly from [2e-3, 1e-2] rad, per device.
6. **DC offset** (`apply_impairments`, step 4). y = y + d, where d = d_I + j d_Q and d_I, d_Q are drawn from U(-0.05, 0.05), per device.
7. **Random CFO and initial phase** (`make_frame`, step 4). y[n] is multiplied by exp(j (2 pi f n + phi0)), with f drawn from U(-0.01, 0.01) cycles per sample and phi0 from U(0, 2 pi). These are drawn per frame. The DC offset was added before this rotation, so the code also turns it into a tone at frequency f.
8. **AWGN at a specified SNR** (`make_frame`, step 5, via `_add_awgn`). P_s = mean(|y|^2) is measured on the impaired, CFO-shifted frame, so SNR is defined on the signal the receiver actually sees. The noise is circular complex Gaussian with expected total power P_n = P_s / 10^(SNR / 10). In `build_frames`, each frame draws its SNR uniformly from the list it is given.

Impairments belong to the device. `Transmitter.random` draws them once per device, and every frame of that device reuses them. The frame-level symbols, the CFO, the phase and the noise change from frame to frame.

What the model leaves out: multipath and fading, any channel filter beyond the pulse shaping, timing and carrier recovery at the receiver (the frame start is random, so each frame has a random symbol-timing phase, but nothing estimates it), interference, and any real amplifier, oscillator or radio measurement. The parameter ranges are the code's own choices, not measured values.

From simulator to score:

```
Transmitter.random / make_transmitters   device = modulation + fixed impairments
        |
make_frame -> apply_impairments -> CFO -> _add_awgn      one frame: (2, 512) float32
        |
build_frames -> dict(iq (N,2,512), label, tx_id, snr_db)  label -1 = not in class_names
        |
ModulationDataset -> DataLoader -> model(x) -> logits (B, C), computed as fc(embed(x))
        |
ce_loss or objectosphere_loss -> Adam -> train_model (keeps the best val-select state)
        |
predict_logits, predict_embeddings -> msp_unknown_score, distance_unknown_score
        |
calibrate_threshold (known val-calib only) -> open_set_report -> results/*.json, *.png
```

## 2. Data splits and roles

**Rule: every frame of one device goes to exactly one split.** The unit that gets split is the device, not the frame.

Why a device-level split matters: a device's impairments (IQ gain and phase, DC offset, PA curve, phase-noise level) form a fingerprint. If frames of one device appeared in both train and test, the network could learn that fingerprint and use it as a shortcut to the modulation label. Test accuracy would then measure memorised devices, not modulation recognition. With a device-level split, the test devices have impairment values the network has never seen, so only the modulation pattern can carry over.

Roles (the sizes are the lessons' default settings; `--quick` uses fewer):

| Role | Used for | Lesson 02 | Lesson 04 |
|---|---|---|---|
| train | network weights, and class centroids in lesson 04 | 40 devices per modulation | 40 known devices per class; the aux outliers (16PSK, 8PAM) only in variant (c) |
| val-select | choosing the checkpoint (best epoch) | 10 devices per class | half of the 10 known validation devices per class |
| val-calib | setting the threshold, known data only | not used | the other half of the known validation devices |
| test | reported once | 10 devices per class, reused at every SNR | known: 10 devices per class; unknown: 10 devices per unknown class |

Class groups, as named in `rfml/signals.py`:

- Known (`KNOWN_MODULATIONS`): BPSK, QPSK, 8PSK, 16QAM. These are the training classes.
- Unknown, test only (`UNKNOWN_MODULATIONS`): 64QAM and 4PAM. They are never used for training, checkpoint choice or calibration. They exist only to score the final decision.
- Auxiliary outliers, train only (`AUX_OUTLIER_MODULATIONS`): 16PSK and 8PAM. They enter training with label -1 in variant (c), so the Objectosphere loss can use them.

**Frame-level split (lesson 03 only).** `split_frames_stratified` splits the frames inside each device, 60/20/20. This is the one exception to the device-level rule, and it is deliberate. In fingerprinting the device is the label, so every device must appear in training, and a device-level split would leave nothing to classify. The test therefore measures recognition of known devices from new frames. It does not test generalisation to a new device. Read the lesson 03 numbers as "can the hardware be recognised", and do not compare them directly with lessons 02 and 04.

## 3. Open-set methods

A closed-set classifier can only name one of its C known classes. To allow "none of the above", we need a score s(x) and a threshold t, and accept x as known when s(x) <= t. In this project a larger score always means "more unknown-like".

- **MSP score (1 - max softmax).** s(x) = 1 - max_c softmax(z)_c, computed from the logits z (`msp_unknown_score`). Its range is [0, 1 - 1/C]. Softmax is trained only to be confident on known classes, so it is a weak unknown detector. Used by variants (a) and (c).
- **Distance-to-centroid score.** Take the embedding e(x) from the penultimate layer (`embed`). `class_centroids` gives the mean embedding mu_c of the known training frames of each class, and s(x) = min_c ||e(x) - mu_c||_2 (`distance_unknown_score`). Used by variant (b). Unknowns tend to land away from every centroid.
- **Objectosphere loss (Dhamija et al., 2018).** Implemented as `objectosphere_loss`, with xi = 10 and lam = 0.1 (`DEFAULT_XI` and `DEFAULT_LAM` in `rfml/experiments.py`). For a known sample (label >= 0) the term is CE(z, y) + lam * max(0, xi - ||z||)^2, so the logit norm is pushed up to xi and no further. For an outlier (label -1) the term is -(1/C) sum_c log softmax_c(z) + lam * ||z||^2: the cross entropy to a uniform target, which is minimal for a flat softmax, plus a penalty that shrinks the logits. The batch loss is the sum over the batch divided by B. The code follows the idea of the paper; check the paper before you quote its exact constants or form.
- **Threshold calibration on known validation data.** `calibrate_threshold(scores, 0.95)` returns the k-th smallest known score, with k = ceil(0.95 n). A sample is accepted when s <= t. Only known val-calib frames are used, so the threshold cannot depend on unknown data.

Positive classes and denominators (these are the definitions `open_set_report` and `auroc` use):

- **Known accept rate.** Positive class: known. Numerator: known test frames with s <= t. Denominator: n_known, the number of known test frames.
- **Unknown reject rate.** Positive class: unknown (64QAM and 4PAM pooled). Numerator: unknown test frames with s > t. Denominator: n_unknown.
- **AUROC.** Positive class: unknown. Negatives: known test frames. It is the fraction of (unknown, known) pairs where the unknown score is larger, with ties counted as one half. 0.5 is chance and 1.0 is perfect separation. Values below 0.5 are possible: they mean unknown frames score lower than known frames, and lesson 04 prints a note saying so.
- **Closed-set accuracy on accepted.** Numerator: accepted known test frames whose argmax is correct. Denominator: accepted known test frames.

Chance levels: for a score with no information, the unknown reject rate is about 0.05 (the threshold accepts about 95% of known scores, and unknown scores then look like known ones), and AUROC is about 0.5. Closed-set accuracy on accepted frames is about 1/4 (lesson 04 has four known classes).

## 4. What the results do and do not mean

- **Synthetic data only.** A result describes this simulator. It says nothing about a real radio, a real amplifier or a real device.
- **A chance-level result can be honest.** With 2 epochs, a few devices, or a weak score, chance-level numbers are what you should expect. Check the data path before you suspect a bug, but do not assume one.
- **A quick run is not evidence.** `--quick` checks that the code runs. Its numbers are not results.
- **Small test sets are noisy.** Lesson 03 gives the ideal column a chance level of 1/N_DEVICES. A row with about 50 frames can differ from that level by several points through chance alone, so compare overall rows before reading much into one SNR.
- **One seed is not a comparison.** Each variant in lesson 04 has its own seed, so the gap between (a) and (b) mixes the score and the seed. A seed-matched rerun would isolate the score.
- **The Objectosphere variant is optimistic on the 4PAM pair.** 8PAM is an auxiliary outlier in training and 4PAM is an unknown at test. Both are PAM with the same real-valued level structure, so "PAM-like is not my class", learned from 8PAM, transfers to 4PAM more easily than to an unrelated modulation. Treat the unknown reject rate of variant (c) as an optimistic bound on what outlier exposure buys in general. The lesson also notes that 64QAM is a close relative of the known 16QAM.
- **The fingerprinting split is frame-level by design** (section 2).
- **Frames of one device are correlated.** The n in each table counts frames, so it overstates the number of independent samples. Devices are the more honest unit of independence.
- **Passing tests** show that the code runs as written. They do not show that recognition works.

Self-check checklist for any number you read or report:

- [ ] Which class is positive, and what is the denominator?
- [ ] Is the count (k/n or n) printed next to the rate, and is it large enough? Count devices as well as frames.
- [ ] What is the chance level for this metric? 1/C for accuracy, about 0.05 for a reject rate at 95% acceptance, 0.5 for AUROC.
- [ ] Is it a `default` run (check `"mode"` in the JSON), and which seed produced it?
- [ ] Did any unknown-class frame influence training, the checkpoint choice (val-select) or the threshold (val-calib)?
- [ ] Are train, val and test devices disjoint, or is this the frame-level fingerprinting split?
- [ ] Is there a matching baseline: chance for lesson 02, the ideal-device ablation for lesson 03?

## 5. Exercises

Each exercise fits in about an hour. A full run takes minutes, and every run overwrites `results/`. Work in a copy of the folder (for example, `cp -r` it to a scratch directory) so the original source and `results/` stay unchanged, and copy the JSON file before each sweep run.

1. **Predict, then remove impairments (stage 3).** Before running, predict what happens to the impaired-versus-ideal gap in lesson 03 if you narrow the IQ phase range from plus or minus 5 degrees to plus or minus 0.5 degrees. Then run the full lesson and compare. Hint: `Transmitter.random` in `rfml/signals.py` draws the parameters. For g = 1 the image ratio is tan(phi / 2), so you can estimate how small the image becomes. The other impairments are still present.
2. **Move the training SNR grid (stage 2).** Change `TRAIN_SNRS` in `rfml/experiments.py` so training starts at 0 dB, and predict whether accuracy at -4 dB and -6 dB falls more than at 0 dB. The grid is shared by lessons 02 to 04, so work in a copy. Hint: `MOD_TEST_SNRS` keeps the -6 dB test point for stage 2, and lesson 02 marks the rows below the training grid.
3. **Add an unknown modulation (stage 4).** Add a 16-point ring constellation, for example "16APSK", to `constellation()` in `rfml/signals.py`. Add it to `MODULATIONS` and to `UNKNOWN_MODULATIONS`, then rerun lesson 04 and see whether AUROC moves. Predict first. Hint: `tests/test_signals.py` has an `EXPECTED_SIZES` table, and the unit-power test runs over every name in `MODULATIONS`, so both must be updated, and the test suite must pass.
4. **Sweep xi and lam (stage 4).** The defaults `DEFAULT_XI` and `DEFAULT_LAM` are in `rfml/experiments.py`. In a copy of the folder, run a 2 x 2 grid on the full lesson 04, using `RFML_RESULTS_DIR` to keep each run's JSON in its own folder. Record the AUROC and the unknown reject rate with its k/n count. Hint: one seed per cell, so treat small differences as possible noise.
5. **Temperature-scaled MSP (stage 4).** Change `msp_unknown_score` so the logits are divided by a temperature T before the softmax. Decide which known split may fit T, and justify the choice against the role rules in section 2. Never use the unknown test frames. Hint: T = 1 must reproduce the current results. Temperature does not change the argmax, so closed-set accuracy stays the same, but the ranking of unknown scores can change.
6. **Mahalanobis distance on the embeddings (stage 4).** Implement a score that uses one shared covariance Sigma, estimated from the known training embeddings, with s(x) = min_c (e - mu_c)^T Sigma^-1 (e - mu_c). Compare it with the Euclidean `distance_unknown_score`. Hint: `predict_embeddings` gives e, and `class_centroids` gives mu_c from known training data only. If Sigma is singular, use `np.linalg.pinv` or a small ridge term, and say which one you used.
7. **Change the frame length (stage 2).** Set `N_SAMPLES` to 256 in a copy of `rfml/experiments.py` and compare the per-SNR accuracy of MLP and CNN1D with the 512 run. Predict first which model is more affected. Hint: at `sps = 8`, 512 samples is 64 symbols and 256 samples is 32. The MLP's first layer size is `2 * n_samples`, so it follows the same constant.

## 6. Testing and layout

```
learning/rfml-basics/
  README.md              this file
  setup.sh               creates .venv/, installs requirements.txt, smoke check; --test also runs pytest
  requirements.txt       numpy, torch, matplotlib, pytest, streamlit (versions not pinned)
  app.py                 Streamlit UI for the four stages (run with streamlit run app.py)
  pytest.ini             testpaths = tests, pythonpath = .
  .gitignore             ignores .venv/, __pycache__/, .pytest_cache/ and results/*.png
  rfml/                  the library; lessons 02 to 04 import it
    __init__.py          empty
    signals.py           constellations, RRC pulse, impairments, AWGN, make_frame, iq_channels
    dataset.py           device draws, build_frames, ModulationDataset, frame-level split
    models.py            MLP, CNN1D, BasicBlock1D, ResNet1D (each has embed() and fc)
    train.py             TrainConfig, train_model, predict_*, ce_loss, accuracy_val_score
    openset.py           MSP score, centroids, distance score, Objectosphere loss, threshold
    metrics.py           accuracy, auroc, open_set_report, confusion_matrix
    experiments.py       stage functions and scale presets, shared by the lessons and app.py
  lessons/               run these; each prints its output and writes results/
    01_tensors_autograd.py
    02_modulation_classification.py
    03_rf_fingerprint.py
    04_open_set.py
  tests/                 pytest suite (section below)
  results/               JSON (tracked) and PNG (git-ignored), written by the lessons
```

Run the tests with `.venv/bin/python -m pytest -q`, or `bash setup.sh --test`. `pytest.ini` points pytest at `tests/`. All 165 tests passed when this README was checked. The count changes when tests are added.

What the suite covers:

- `test_signals.py`: constellation size and unit power, RRC energy and zero ISI at symbol spacing, the IQ image ratio against its closed form, Rapp compression and saturation, phase-noise variance, AWGN power and circularity, frame shape and power.
- `test_dataset.py`: device draws, `build_frames` shapes and labels, `ModulationDataset` indexing, and the frame-level split (disjoint, covering, every device in train).
- `test_models.py`: output shapes, the embed and fc split, finite gradients, rejection of (B, L, 2) input, and the ResNet block specification.
- `test_train.py`: seeding, learning on a separable toy problem, early stopping, best-state restore, eval mode during prediction, `ce_loss` ignoring outliers, and `accuracy_val_score` counting known samples only.
- `test_openset.py`: softmax stability, the MSP range, centroids that ignore outliers, distances against brute force, the Objectosphere loss against hand-computed values, threshold target and ties, AUROC against brute force, `open_set_report` and `confusion_matrix`.
- `test_experiments.py`: the stage functions in `rfml/experiments.py` on a tiny scale: strict JSON output, the presets against the lesson sizes, seed reproducibility, role independence, and figure helpers.
- `test_lesson01.py`: runs lesson 01's `main()` with its output folder redirected to a temporary directory, checks its strict JSON output, and checks that lesson 01 does not import `rfml`.
- `test_lessons_experiments.py`: runs lessons 02 to 04 with `--quick` into a temporary folder, checks that their JSON parses strictly, and checks that each lesson's numbers equal the stage functions called directly.

One limit to keep in mind: pytest checks lessons 02 to 04 only in quick mode, so a full run is not part of the test suite. Running pytest leaves `results/` unchanged.

## 7. References

- Dhamija, A. R., Günther, M., and Boult, T. E. "Reducing Network Agnostophobia." *Advances in Neural Information Processing Systems 31 (NeurIPS 2018).* The Objectosphere loss in `rfml/openset.py`.
- He, K., Zhang, X., Ren, S., and Sun, J. "Deep Residual Learning for Image Recognition." *CVPR 2016*, pp. 770-778. The 1D ResNet in `rfml/models.py` follows the ResNet-18 block layout.
- O'Shea, T. J., and West, N. "Radio Machine Learning Dataset Generation with GNU Radio." *Proceedings of the GNU Radio Conference*, 2016. Background on how RF-ML datasets are generated. This project uses its own simulator and does not reproduce that dataset.
