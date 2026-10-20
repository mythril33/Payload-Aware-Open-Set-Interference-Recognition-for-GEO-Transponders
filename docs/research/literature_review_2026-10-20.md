> Kullanıcının 2026-10-20 tarihli literatür taraması, değiştirilmeden saklanan kopya. "(verify)" işaretli künyeler ve ticari basın rakamları doğrulanmamıştır; projedeki kullanım kuralları ve tarama↔depo düzeltmeleri: [P16](../plan/P16_literatur_duzeltme_programi.md).

# Payload-Aware Open-Set Interference Recognition for GEO Transponders: Literature Review

The claimed gap largely holds. I found no 2018–2026 paper that trains or evaluates a deep-learning interference detector or classifier for GEO/GSO satellites on data that models TWTA nonlinearity, IMUX/OMUX filtering, multicarrier intermodulation, dual polarization or carrier-plan metadata. Open-set rejection of unknown interference classes has been published only for generic anti-jamming, radar and GNSS signals, never for a GEO transponder. Work that partly narrows the gap (Eutelsat/CTTC/ESA, Fudan's Agon, Fraunhofer's GNSS work, open-set jamming papers) must be cited, and C1–C3 should be framed as transferring known pieces into a new setting, not as firsts in every respect.

## TL;DR

- **Verdict: the gap holds, with caveats.** The GEO DL interference papers I found are from SnT/Luxembourg (Daoud et al. ICASSP 2023; Saifaldawla et al. PIMRC 2023, ICC-W 2024, IEEE TMLCN 2024), Fudan (Agon, arXiv 2026), CTTC/Eutelsat (SPAWC 2019, IEEE Commun. Mag. 2021) and KTH (Pellaco et al. ICSSC 2019). All use linear signal superposition with single-polarization inputs. They are binary detectors, either reconstruction-error or closed-set. None models the transponder chain, cross-pol, carrier plans or open-set rejection. Even the DVB-S2X reference channel guidelines treat cross-polar and co-channel interference as negligible in their multicarrier scenario.
- **The pieces exist, but in separate fields.** Payload models are mature but used only for predistortion and equalization: the Saleh TWTA, the DVB-S2 IMUX/TWTA/OMUX chain (Casini, De Gaudenzi & Ginesi 2004), and multicarrier intermodulation analysis. Open-set methods are mature but untested on satellite interference: MSP, ODIN, energy, Mahalanobis, OpenMax, OSCR, and Vaze et al.'s "good closed-set classifier" result. The most rigorous real-data, domain-shift interference ML comes from GNSS (Fraunhofer IIS DARCY/DARCII datasets and papers).
- **What to do.** Frame the novelty as "first payload-realistic, plan-conditioned, dual-polarization open-set benchmark plus a quantified payload gap." Add a carrier-cancellation or cyclic baseline for carrier-under-carrier, which a PSD cannot see. Report OSCR alongside AUROC. Validate realism against OpenDPD and the SnT data rather than claiming real-world performance.

## Key Findings

1. **No GEO interference-recognition paper models the transponder.**
   - Daoud et al. (ICASSP 2023): a GSO uplink with BPSK signals, rectangular pulses and AWGN, 5 subbands, 2,500 samples per class, and 6 closed-set classes.\[1\]
   - Saifaldawla et al. (PIMRC 2023, ICC-W 2024, TMLCN 2024): a downlink NGSO→GSO ground-station link budget with linear superposition. TrID beats the energy detector by up to 31.23% in detection accuracy, and time-domain inputs beat frequency-domain ones.\[2\]
   - Agon (Fudan, arXiv 2606.14147): also a linear superposition model. It reaches AUC 0.9327 on the public NGSO-GSO set versus 0.8318 for TrID-like baselines.\[3\]
2. **Operator-motivated work names the right classes but does not model them.** Vázquez et al. (CTTC/UPC/Eutelsat/GMV/Reply; 2019 newsletter, arXiv 2007.10110) write that a mispointed antenna (cross-polarization or adjacent satellite) and misconfigured equipment (noise, intermodulation) "cover 70-80% of all interference cases". Carrier overlaps are listed separately and are not part of that 70–80%. The Commun. Mag. 2021 paper (CTTC, Eutelsat, ESA ARTES) still uses a generic autoencoder detector. That detector, as arXiv 2007.10110 describes it, "throws an alarm if the deviation trespasses a fixed threshold." The paper reports a 44% reduction in false detection probability on "real data."
3. **Open-set is the most clearly unoccupied axis for satellite interference.** Open-set jamming recognition exists in general wireless and radar work: convolutional prototype learning (Appl. Sci. 2022), OpenMax radar jamming (Remote Sens. 2022), compound-jamming EVT (IET RSN 2024), ArcCider (IET Commun. 2026).\[4\]\[5\]\[6\]\[7\] Open-set AMC and RF fingerprinting are also active. None of it covers satellite transponders. A 2021 interference-suppression survey (arXiv 2112.08988) says OSR/OOD has received too little attention in DL interference work.\[8\]
4. **Industry statistics support the open-set motivation.** These are industry and trade-press figures, not peer-reviewed statistics.
   - **Unknown sources.** SUIRG's early database (3,650 incidents) attributed 62% of cases to human error, cross-polarization and equipment problems. SUIRG president Robert Ames told Via Satellite (1 Aug 2005) that "another 34 percent of interference incidents are caused by unknown sources, usually because the problems appear and disappear before the operators have a chance to document it."
   - **Cross-pol and unauthorized carriers.** In Microwave Journal (14 Aug 2012), sIRG's Martin Coleman reported that "according to Intelsat, as much as 33 percent of interference is due to cross polarization leakage." The same article says Intelsat attributes 47% to unauthorized carriers.
   - **VSATs.** IRG Executive Director Martin Coleman (Dec 2014) said VSAT systems "cause approximately 40% of all interference, and are responsible for 50% of downtime." The often-cited "50–70%" figure comes from Kratos marketing copy.
   - **Frequency.** A Satellite Interference Reduction Group survey found that 93% of operators suffer interference at least once a year, more than half at least monthly, and 17% continuously.
5. **Carrier-under-carrier is a hard identifiability case.** The DVB-CID metacarrier sits at −27.5 dB relative to the host's spectral density.\[9\] Commercial carrier-under-carrier detectors (R&S GSACSM, Integrasys VectorSat, Kratos Monics, Calian Decimator) work by cancelling the host carrier, not by inspecting the PSD.\[10\] A spectrogram-only model therefore cannot be expected to identify carrier-under-carrier at realistic C/I. The cyclic branch, or a cancellation residual, is needed in practice, and the identifiability analysis (C2) should say so explicitly.
6. **GNSS is the methodological template for evaluation, not for the physics.** Fraunhofer IIS work evaluates under real-world data discrepancies, novel-class few-shot learning, MC-dropout uncertainty and controlled-versus-highway shift, with CC-BY/CC-BY-SA datasets. But GNSS interference sits far above a below-noise signal, whereas a GEO operator sees structured multicarrier spectra.

## Details: Thematic Review

### 1. Interference detection/classification for satellite communications

**Classical on-board detection (SnT, 2016–2018).** Politis, Maleki, Tsinos, Chatzinotas and Ottersten proposed on-board spectrum monitoring units that decode and cancel the desired signal, then apply an energy detector to the residual. They analyzed imperfect cancellation (SPAWC 2016) and weak interference (ICASSP 2017), and used DVB-S2X pilot fields.\[11\]\[12\] Pérez-Neira et al. (arXiv 1802.03958) placed this within HTS signal processing and noted that on-board detection avoids the downlink noise and *transponder distortion* that degrade on-ground detection.\[13\] This is an early acknowledgement that the payload chain corrupts ground-based observations, which supports C3.

**Early DL (2019).** Two papers started the DL line:
- Henarejos, Vázquez and Pérez-Neira (SPAWC 2019) used a sparse autoencoder on real Ku-band DVB-S2 captures for detection, and an LSTM to classify terrestrial interferers (LTE/UMTS/GSM) added digitally.\[14\]
- Pellaco, Singh and Jaldén (ICSSC 2019, KTH with SSC) used an LSTM to predict spectra and flagged deviations, trained on real received spectra.\[15\]\[16\]

**Operations (2019–2021).** Vázquez et al. (CTTC, Eutelsat, Data Reply, Rheatech, GMV; ESA ARTES) brought ML into operator workflows: interference detection, flexible payload configuration and congestion prediction.\[17\]

**SnT SmartSpace line (2023–2026).** The FNR SmartSpace project (Lagunas, Ortiz, Chatzinotas) produced the on-board CNN study (Daoud et al.), the NGSO→GSO autoencoder/CAE/VAE/TrID line (Saifaldawla et al.) and public datasets.\[18\]\[19\]\[20\] All are binary or subband-localization tasks with a single carrier per scenario, and none models the payload.

**Recent Chinese and other work.** Agon (Fudan, 2026) adds MAE pre-training of a dual-attention transformer, HOS-augmented attention, wavelet regularization and a multi-task head, and runs cross-dataset/OOD robustness tests.\[3\] This is covariate shift, not unknown-class rejection. Several closed-set satellite interference classifiers cover single-tone, narrowband, broadband noise, pulse, sweep and multi-tone interference in AWGN (ACM 2018; IEEE conference 2024; ICECAI 2025).\[21\]\[22\]\[23\] A Kernel-FastICA anti-jamming paper explicitly says existing methods "lack effective modeling of the physical distortion mechanisms caused by transponder nonlinearities," which is direct support for the gap claim, although that paper does suppression rather than recognition.\[24\]

**On-board vs. ground.** On-board approaches (Politis, Daoud, the AI-accelerator review in *Aerospace* 2023) observe the uplink before the TWTA. The project's ground-downlink view is the one in which payload IM and external interference become confounded.

### 2. GNSS interference/jamming classification with DL

Fraunhofer IIS (the DARCY and DARCII projects) is the most prolific group:
- Brieger et al. (ION GNSS+ 2022) fuse spectrum and time-domain data and use MC-dropout entropy as a reliability measure.\[25\]
- Ott et al. (ICL-GNSS 2024) apply few-shot quadruplet learning.
- Heublein et al. (ION GNSS+ 2024, arXiv 2503.23775) evaluate supervised and unsupervised methods under real-world data discrepancies.\[26\]\[27\]
- Further work covers VAE disentanglement (arXiv 2504.10556), LLM-based characterization (arXiv 2501.05079), attention fusion with AoA (arXiv 2507.14167), and the Sionna-simulated S-ICDF dataset (arXiv 2607.03411).

Datasets include the Highway 1 dataset (IEEE DataPort, doi:10.21227/xpm9-tt28, CC BY 4.0), Highway 2, LC-laboratory and Jammertest 2025 (Zenodo, CC BY-SA 4.0).\[28\]\[29\]\[30\]\[31\] Other groups contribute too: Mehr and Dovis (IEEE TAES) on ResNet-based classification from terrestrial and LEO stations, and an MDPI *Electronics* 2025 bit-depth study.\[32\]\[33\]

**What transfers to GEO:** condition-based splits (location, sensor, day), explicit "novel class" protocols, uncertainty-based rejection, and spectrogram-plus-feature fusion. **What does not:** the GNSS interference catalogue (chirp jammers, DME pulses), which matches the held-out unknowns rather than the GEO known classes, and the below-noise desired-signal regime.

### 3. Generic RF/spectrum DL

- TorchSig's Sig53 (5M samples, 53 classes) and WidebandSig53 (550k samples, ~2M signals; Boegner et al., arXiv 2211.10335) move to wideband detection and recognition on complex spectrograms with CNN and transformer detectors. They are good pre-training and augmentation sources, but contain no satellite payload effects or polarization.\[34\]\[35\]
- Tekbıyık et al. (arXiv 2003.08359) showed that CNNs on spectral-correlation-function inputs beat raw-signal networks on real cellular captures.\[36\] This is direct support for the cyclic branch.
- Cyclo-AMC (FPT 2025) reports that cyclostationary features improve DNN generalization.\[37\]
- "Keep It Simple" (arXiv 2303.03326) found that small CNNs suffice for interference classification. This supports including a small-model baseline and reporting FLOPs and latency.

### 4. Open-set recognition and OOD detection

**Foundations:** OpenMax (Bendale & Boult, CVPR 2016); MSP baseline (Hendrycks & Gimpel, ICLR 2017); ODIN (Liang et al., ICLR 2018); Mahalanobis (Lee et al., NeurIPS 2018); energy score (Liu et al., NeurIPS 2020); OSCR and "agnostophobia" (Dhamija et al., NeurIPS 2018); ARPL (Chen et al., TPAMI 2021); and "Open-Set Recognition: a Good Closed-Set Classifier is All You Need" (Vaze et al., ICLR 2022), which shows that MSP/MLS baselines with strong closed-set training match or beat specialized OSR methods. Surveys: Geng et al. (TPAMI 2020) and Yang et al. (generalized OOD survey).

**RF applications:**
- open-set AMC: DC-LSTM with center loss and Weibull (arXiv 2002.12037); CIR reconstruction (arXiv 2312.13023); FSOS-AMC (arXiv 2410.10265); adversarial attacks on AMOSR (arXiv 2405.05022)\[38\]\[39\]\[40\]\[41\]
- open-set RF fingerprinting (arXiv 2306.13895)\[42\]
- expert-feature-augmented open-set classification (arXiv 2302.03749)\[43\]
- the open-set jamming papers listed above

**Pitfalls for the evaluation design:**
- Results depend on which classes are held out ("semantic" vs. "nuisance" novelty). The three unknowns (pulsed, wideband noise, intermittent bursts) differ in how close they are to the known classes. Wideband noise resembles overdrive-IM spectral regrowth, so report per-unknown AUROC.
- Vaze et al. imply that closed-set accuracy drives OSR. Report closed-set accuracy jointly, through OSCR.
- AUROC hides operating-point behaviour. Add FPR@95TPR.
- Tuning thresholds or ODIN temperatures on the test unknowns is leakage. Use a separate validation unknown, or none at all.

### 5. Satellite payload modeling

- **Amplifier models.** The Saleh (1981) TWTA model remains the standard AM/AM–AM/PM form. Rapp (SSPA) and the memory polynomial are the usual alternatives.
- **DVB-S2 reference channel.** The DVB-S2 standard (ETSI EN 302 307) and Casini, De Gaudenzi & Ginesi (IJSCN 2004) define the IMUX–TWTA–OMUX transponder, with conventional and linearized TWTA curves, a phase-noise mask, and static and dynamic predistortion.\[44\]\[45\] The DVB-S2X implementation guidelines (TR 102 376-2) include a multicarrier scenario with six carriers through one TWTA and an adjacent-beam model. They explicitly assume cross-polar and co-channel contributions are negligible.\[46\] C1's dual-pol extension therefore goes beyond the reference channel and must be justified with XPD measurement literature.
- **Multicarrier distortion.** Beidas (IEEE TCOM) analyzes intermodulation in multicarrier transponders.\[47\] Allegue-Martínez et al. (*Electronics Letters* 2014) show that IMUX/OMUX group delay "masks" the TWTA characteristics in multicarrier DVB-S2.\[48\] This matters for identifiability: payload IM appears through a filtered, memory-ful channel. NPR testing of TWTAs (ResearchGate 2021) gives a realism check for loading sweeps.\[49\]
- **Measured PA data.** OpenDPD (TU Delft; ISCAS 2024; v2 arXiv 2507.06849) supplies measured PA data (DPA_200MHz) and PyTorch PA models.\[50\]\[51\] It is not a TWTA, so use it to test amplifier-model mismatch, not as GEO ground truth.

### 6. Interference mechanisms and operational practice

- **Cross-polarization.** Causes include feed misalignment, rain depolarization and insufficient XPD (see the dual-polarised HTS and JPL IPN references).\[52\]\[53\]\[54\]
- **Carrier ID.** ITU-R S.2062 (2014) and the DVB-CID metacarrier support source identification.\[9\]\[55\] The FCC required CID for occasional-use video uplinks from June 2016.\[56\]
- **PCMA/carrier-under-carrier.** Blind PCMA detection uses SIC/ICA, and its detection limits have been analyzed information-theoretically.\[57\]\[58\]
- **Commercial monitoring.** Kratos Monics/SatGuard, Integrasys VectorSat ("up to 200 carriers per second"), R&S GSACSM and Calian Decimator all advertise carrier-under-carrier detection.\[9\]\[10\]\[59\]\[60\] These are vendor claims and have not been independently benchmarked.
- **Intentional jamming.** In March 2026 Kratos reported sustained Iran-origin jamming affecting at least six commercial GEO satellites, including on/off cycling.\[61\] This is exactly the "intermittent burst" unknown class.

### 7. Sim-to-real and domain shift

RF-specific evidence is thin. RadioML's over-the-air study, Heublein et al.'s real-world discrepancy evaluation, embedding-based domain generalization for RF (arXiv 2510.23186) and synthetic-to-real RF VLM tests (arXiv 2605.04676) all find degradation without calibration or adaptation.\[62\]\[63\] That finding supports C3's condition-based splits. No GEO interference study reports results under domain shift except Agon, which uses cross-constellation and cross-dataset tests.

**Leakage risks to avoid:** the same carrier-plan instance in train and test; the same random seed for the payload transfer function; spectrogram normalization fitted on all data.

### 8. Classical baselines

- **Energy detection** is the universal baseline in the SnT papers (Politis; Saifaldawla TMLCN).\[2\]
- **CA-CFAR** (Finn & Johnson 1968) is standard for spectral peak detection.
- **Cyclostationary detection** (Gardner 1991) is more robust at low SNR but expensive.
- **Feature-plus-gradient-boosting** (XGBoost, Chen & Guestrin 2016) is a fair "expert" baseline.

**Additional baselines to add:** signal-cancellation energy detection (EDSC, per Politis), which approximates operator carrier-under-carrier tools; a reconstruction autoencoder (Saifaldawla-style); and the WBSig53 detector as a pre-trained baseline.

### 9. Identifiability

No paper offers a formal identifiability analysis for satellite interference classes, which makes C2's analysis a real contribution. The physics-based cues are:
1. **Payload IM vs. external carrier.** IM products sit at predictable frequencies (2f₁−f₂ etc.) given the carrier plan, and scale with input back-off at roughly a 3:1 dB slope for third-order products. External carriers do neither. *Needs: plan mask plus a back-off sweep.*
2. **Cross-pol leakage vs. co-pol unplanned carrier.** Leakage reproduces a carrier present on the opposite polarization at reduced level (XPD). *Needs: the cross-pol channel.*
3. **Carrier-under-carrier.** Invisible in the PSD at low C/I. It needs cyclic features at the under-carrier symbol rate, or a cancellation residual.
4. **ASI vs. unauthorized carrier.** These are spectrally similar. Separating them needs plan metadata, geolocation or CID, which are beyond the observables. Report this pair as confusable by design.

Information-theoretic analysis of blind PCMA detection is the closest existing formal treatment.

### 10. Candidate venues

| Venue | Fit | Comparable papers |
|---|---|---|
| IEEE TAES | Strong for a full journal paper with payload modeling and evaluation rigor | Mehr & Dovis GNSS DNN classification |
| IEEE TMLCN | Strong: ML-for-comms, open-access | Saifaldawla et al. 2024 (GenAI NGSO detection) |
| IEEE TCCN | Good for open-set signal recognition | Open-set wireless identification in ISM band |
| IEEE OJ-COMS | Good, fast, open access | — |
| IJSCN (Wiley) | Domain-native; reviewers know DVB-S2 channels | Casini et al. 2004; Bhattacharyya et al. 2023 ML survey |
| ICASSP / SPAWC | Short version or dataset-generator paper | Daoud 2023; Henarejos 2019; Politis 2016/17 |
| ICC/GLOBECOM satellite workshops | Workshop version | Saifaldawla ICC-W 2024 |
| ASMS/SPSC, ICSSC (AIAA/IET) | Operator audience | Pellaco 2019 |
| IEEE Aerospace Conf., MILCOM | Applied/defense audience; jamming angle | — |

## Gap Matrix

Legend: ✔ modeled; ✖ not modeled; ◐ partial or incidental.

| Paper | TWTA NL / IBO | IMUX/OMUX | Multicarrier IM | Dual-pol / XPD | Carrier plan | Open-set | Data | Metrics |
|---|---|---|---|---|---|---|---|---|
| Politis et al. SPAWC'16/ICASSP'17 | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Analytical/sim | Pd vs ISNR |
| Henarejos et al. SPAWC'19 | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Real Ku DVB-S2 + digital interferers | Accuracy |
| Pellaco et al. ICSSC'19 | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Real spectra (operator) | Detection rates |
| Vázquez et al. Commun. Mag.'21 | ✖ | ✖ | ✖ | ✖ (motivation only) | ✖ | ✖ | "Real data" (Eutelsat context) | False-detection reduction 44% |
| Daoud et al. ICASSP'23 | ✖ | ✖ | ✖ | ✖ | ◐ (subband grid) | ✖ | Sim BPSK, 6 classes | Accuracy |
| Saifaldawla et al. PIMRC'23 | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Sim NGSO→GSO | Accuracy/AUC |
| Saifaldawla et al. ICC-W'24 | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Sim NGSO→GSO | Pd (+11% vs ED) |
| Saifaldawla et al. TMLCN'24 | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Public NGSO-GSO set | Accuracy, AUC |
| Agon (Yang et al.) arXiv'26 | ◐ (testbed only) | ✖ | ✖ | ✖ | ✖ | ✖ (covariate OOD only) | NGSO-GSO + NGSO-NGSO + testbed | AUC, F1 |
| Sat. interference CNN (ACM'18; IEEE'24; ICECAI'25) | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | Sim AWGN | Accuracy |
| Open-set jamming (Appl. Sci.'22; IET'26) | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | Sim generic jamming | Acc., AUROC |
| Fraunhofer GNSS (Heublein'24 etc.) | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ (novel class, few-shot) | Real + controlled | F1, acc. |
| DVB-S2X TR 102 376-2 (reference channel) | ✔ | ✔ | ✔ | ✖ (assumed negligible) | ◐ | n/a | Reference model | BER/MODCOD |
| **This project (planned)** | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | Sim + realism checks | Pd@Pfa, macro-F1, AUROC, OSCR |

## Annotated Bibliography

Tags: C1 = dataset generator; C2 = plan-conditioned open-set recognizer and identifiability; C3 = payload gap / generalization; components: [SIM] simulator, [MOD] model, [OSR] open-set, [BASE] baselines, [EVAL] evaluation. DOIs marked "(verify)" are recalled, not confirmed during this search.

### A. Satellite interference detection/classification

1. **Daoud, S., Eappen, G., Ortiz, F., Lagunas, E., Martins, W., Chatzinotas, S.** "CNN-Based On-Board Interference Detection in Satellite Systems: An Analysis of Dataset Impact on Performance." ICASSP 2023. Landing: https://ieeexplore.ieee.org/document/10193395/ · OA PDF: https://orbilu.uni.lu/bitstream/10993/55407/1/ICASSP_2023_Saed.pdf. A CNN on board a GSO satellite classifies which of 5 subbands contains NGSO interference, using BPSK signals with rectangular pulses, fs = 5 GHz around 29.55 GHz, and 2,500 samples per class.\[1\] Reduced-size magnitude FFT gave the best accuracy.\[1\] There is no payload model, and the classification is closed-set. Data are public on SmartSpace. Tags: C1 (contrast), C3; [BASE][EVAL].
2. **Saifaldawla, A., Ortiz, F., Lagunas, E., Daoud, S., Chatzinotas, S.** "NGSO-To-GSO Satellite Interference Detection Based on Autoencoder." IEEE PIMRC 2023. Landing: https://www.semanticscholar.org/paper/2e58ac0017ce6245ed8328d3e892e0fe7c7360a4 · OA PDF: paywalled (ResearchGate copy only). An autoencoder flags LEO downlink interference at a GSO terminal from reconstruction error in the time and frequency domains. It uses a single MODCOD and a single NGSO satellite.\[64\]\[65\] Tags: C2 (anomaly-detection contrast); [BASE].
3. **Saifaldawla, A., Ortiz, F., Lagunas, E., Chatzinotas, S.** "Convolutional Autoencoders for Non-Geostationary Satellite Interference Detection." IEEE ICC Workshops 2024, pp. 1334–1339. OA PDF: https://orbilu.uni.lu/bitstream/10993/60597/1/Moatssim__ICC__Final.pdf. Two CAE models are trained only on interference-free GSO signals and improve detection probability by up to 11% over conventional methods.\[64\] Tags: [BASE].
4. **Saifaldawla, A., Ortiz, F., Lagunas, E., Adam, A. B. M., Chatzinotas, S.** "GenAI-based Models for NGSO Satellites Interference Detection." IEEE TMLCN, vol. 2, pp. 904–924, 2024. DOI: 10.1109/TMLCN.2024.3418933. OA PDF: https://orbilu.uni.lu/bitstream/10993/61484/1/TMLCN_Final.pdf (CC BY 4.0). VAE and transformer (TrID) reconstruction detectors, using real satellite positions and link budgets, are tested across QPSK, 8PSK and 16APSK, bandwidth overlap and off-axis angles.\[20\]\[65\] TrID beats ED by up to 31.23%, and time-domain inputs beat spectra.\[2\] This is the closest modern GEO-ground baseline. Tags: C3; [BASE][EVAL].
5. **Yang, B., Yang, C., Chen, Z., Qiu, K., Gao, Y.** "Agon: A Semi-Supervised Framework for Robust Satellite Interference Detection." arXiv:2606.14147, 2026. Landing: https://arxiv.org/abs/2606.14147 · OA PDF: https://arxiv.org/pdf/2606.14147. Combines MAE pre-training of a dual-attention transformer, HOS attention, wavelet loss and a multi-task head. Reports AUC 0.9327 and F1 0.8351 on the public NGSO-GSO set, and 0.9085/0.9055 on its NGSO-NGSO set, with OOD robustness tests.\[3\] Uses a linear superposition model, and the task is binary. This is the strongest recent competitor. Tags: C2, C3; [MOD][EVAL].
6. **Pellaco, L., Singh, N., Jaldén, J.** "Spectrum Prediction and Interference Detection for Satellite Communications." ICSSC 2019 (IET). OA PDF: https://arxiv.org/pdf/1912.04716. An LSTM predicts interference-free spectra and flags deviations, trained on real received spectra (KTH with SSC).\[16\] Tags: [BASE], realism.
7. **Henarejos, P., Vázquez, M. Á., Pérez-Neira, A. I.** "Deep Learning for Experimental Hybrid Terrestrial and Satellite Interference Management." IEEE SPAWC 2019. DOI: 10.1109/SPAWC.2019.8815532. OA PDF: https://arxiv.org/pdf/1906.03012. Uses a sparse autoencoder on real Ku-band DVB-S2 IQ and an LSTM classifier of LTE, UMTS and GSM interferers.\[14\] Tags: [BASE].
8. **Vázquez, M. Á., Henarejos, P., Pappalardo, I., Grechi, E., Fort, J., Gil, J. C., Lancellotti, R. M.** "Machine Learning for Satellite Communications Operations." IEEE Commun. Mag. 59(2):22–27, 2021. DOI: 10.1109/MCOM.001.2000367. OA: https://zenodo.org/records/4705117. An ESA/Eutelsat operations study covering interference detection, flexible payload and congestion prediction, with a 44% reduction in false detection.\[66\] Tags: motivation; [EVAL].
9. **Vázquez, M. Á., et al.** "On the Use of AI for Satellite Communications." IEEE ComSoc SSC Newsletter, 2019. OA PDF: https://arxiv.org/pdf/2007.10110. States that mispointed antennas (cross-polarization or adjacent satellite) and misconfigured equipment (noise, intermodulation) "cover 70-80% of all interference cases." It describes the autoencoder detector as one that "throws an alarm if the deviation trespasses a fixed threshold." Tags: class taxonomy (C2).
10. **Politis, C., Maleki, S., Tsinos, C., Chatzinotas, S., Ottersten, B.** "On-board the Satellite Interference Detection with Imperfect Signal Cancellation." IEEE SPAWC 2016. Paywalled. Energy detection after decoding and cancelling the desired signal, with analytical Pd under imperfect cancellation.\[12\] Tags: [BASE] (EDSC).
11. **Politis, C., Maleki, S., Tsinos, C., Chatzinotas, S., Ottersten, B.** "Weak Interference Detection with Signal Cancellation in Satellite Communications." ICASSP 2017. OA PDF: https://orbilu.uni.lu/bitstream/10993/29259/1/icassp_final.pdf. Extends EDSC to weak interference.\[11\] Tags: [BASE].
12. **Pérez-Neira, A. I., Vázquez, M. Á., Maleki, S., Shankar, M. R. B., Chatzinotas, S.** "Signal Processing for High Throughput Satellite Systems: Challenges in New Interference-Limited Scenarios." OA PDF: https://arxiv.org/pdf/1802.03958. Notes that on-ground detection is degraded by transponder distortion, and compares on-board CED, EDSCP and EDSCD.\[13\] Tags: C3 motivation.
13. **Ortiz, F., Lagunas, E., Saifaldawla, A., Jalali, M., Emiliani, L., Chatzinotas, S.** "Emerging NGSO Constellations: Spectral Coexistence with GSO Satellite Communication Systems." *Frontiers*, 2026. Landing: https://www.researchgate.net/publication/400945409. A review of NGSO-GSO coexistence and detection. Tags: context.
14. **Ortiz, F., et al. (SnT).** "Artificial Intelligence for Satellite Communication: A Survey." OA PDF: https://orbilu.uni.lu/bitstream/10993/65397/1/Artificial_Intelligence_for_Satellite_Communication_A_Survey.pdf. Lists ESA projects (SATAI, Φ-Sat-1, ATRIA) and hardware (Jetson) used for interference-detection autoencoders and CNNs.\[67\] Tags: venues, context.
15. **Fourati, F., Alouini, M.-S.** "Artificial Intelligence for Satellite Communication: A Review." OA PDF: https://arxiv.org/pdf/2101.10899. Tags: context.
16. **Ortiz, F., et al.** "Onboard Processing in Satellite Communications Using AI Accelerators." *Aerospace* 10(2):101, 2023. OA: https://www.mdpi.com/2226-4310/10/2/101. Covers an autoencoder interference-detection use case on AI chips.\[68\] Tags: [EVAL] (latency).
17. **Bhattacharyya, et al.** "Machine Learning and Deep Learning Powered Satellite Communications." IJSCN 41(6), 2023. DOI: 10.1002/sat.1482. Paywalled. A survey. Tags: venues.
18. **"Artificial Intelligence-based Interference Signal Recognition for Satellite Communications."** IEEE conference, 2024. Landing: https://ieeexplore.ieee.org/document/10823708/. Paywalled. FPGA preprocessing plus DL. Reports 97.5% closed-set accuracy, 5.7 points above SVM.\[23\] Tags: contrast.
19. **CNN+MDS+SVM satellite interference recognition.** ACM conference, 2018. DOI: 10.1145/3231884.3231901. Paywalled. Covers five interference types in AWGN, including coexisting interference.\[21\] Tags: contrast.
20. **Xiong, H.** "Research on Interference Detection and Identification Algorithms for Satellite Communication Systems." ICECAI 2025. Landing: https://www.semanticscholar.org/paper/08c7cf481ab890ff1f6f8c45353fa4c4bc9406bc. Closed-set classification of five classes.\[22\] Tags: contrast.
21. **Kernel-FastICA nonlinear BSS for anti-jamming satellite communications.** OA: https://pmc.ncbi.nlm.nih.gov/articles/PMC12197282/. States that existing methods lack modeling of transponder-nonlinearity distortion.\[24\] This is a suppression paper, not recognition. Tags: C3 gap evidence.
22. **"Cognitive Interference Cancellation with Digital Channelizer for Satellite Communication."** *Sensors* 20(2):355, 2020. OA: https://www.mdpi.com/1424-8220/20/2/355. Detects and nulls tone interference in channelizer subchannels.\[69\] Tags: [BASE] (CW).

### B. GNSS interference ML

23. **Heublein, L., Raichur, N. L., Feigl, T., Brieger, T., Heuer, F., Asbach, L., Rügamer, A., Ott, F.** "Evaluation of (Un-)Supervised Machine Learning Methods for GNSS Interference Classification with Real-World Data Discrepancies." ION GNSS+ 2024. OA PDF: https://arxiv.org/pdf/2503.23775. Evaluates supervised, unsupervised, pseudo-label and domain-adaptation methods on released real-world and controlled datasets.\[27\] Tags: C3; [EVAL][OSR].
24. **Brieger, T., Raichur, N. L., Jdidi, D., Ott, F., Feigl, T., van der Merwe, J. R., Rügamer, A., Felber, W.** "Multimodal Learning for Reliable Interference Classification in GNSS Signals." ION GNSS+ 2022, pp. 3210–3234. Landing: https://www.researchgate.net/publication/364056875. \[70\]\[71\] Fuses spectrum and time data with MC-dropout entropy for reliability.\[25\] Tags: C2 (multimodal fusion, uncertainty).
25. **van der Merwe, J. R., et al.** "Low-Cost COTS GNSS Interference Monitoring, Detection, and Classification System." *Sensors* 23(7):3452, 2023. DOI: 10.3390/s23073452 (verify). OA via MDPI. Tags: [BASE].
26. **Ott, F., Heublein, L., Raichur, N. L., Feigl, T., Hansen, J., Rügamer, A., Mutschler, C.** "Few-Shot Learning with Uncertainty-based Quadruplet Selection for Interference Classification in GNSS Data." ICL-GNSS 2024. Paywalled or arXiv (verify). Tags: C2 (novel classes).
27. **Heublein, L., et al.** "VAE-based Feature Disentanglement for Data Augmentation and Compression in Generalized GNSS Interference Classification." OA: https://arxiv.org/abs/2504.10556. Tags: C3.
28. **"The S-ICDF Dataset: Sionna-Simulated Dynamic Interference Characterization and Direction Finding."** OA PDF: https://arxiv.org/pdf/2607.03411. A simulated, open GNSS interference dataset and a model for the C1 dataset-paper style. Tags: C1.
29. **"Real-time Pre-Correlation GNSS Interference Classification with Lightweight Learned Algorithms."** OA PDF: https://arxiv.org/pdf/2607.28404. Tags: [EVAL] (latency).
30. **Mehr, I. E., Dovis, F.** "A Deep Neural Network Approach for Classification of GNSS Interference and Jamming." IEEE TAES, 2024 (verify DOI). Landing: https://www.researchgate.net/publication/384100236. Covers terrestrial and LEO monitoring.\[33\] Tags: venue comparable.
31. **"A Machine Learning Evaluation of the Impact of Bit-Depth for the Detection and Classification of Wireless Interferences in GNSS."** *Electronics* 14(6):1147, 2025. DOI: 10.3390/electronics14061147. OA. Tags: [EVAL] (quantization).

### C. Generic RF DL

32. **O'Shea, T. J., Roy, T., Clancy, T. C.** "Over-the-Air Deep Learning Based Radio Signal Classification." IEEE JSTSP 12(1), 2018. DOI: 10.1109/JSTSP.2018.2797022. OA: https://arxiv.org/abs/1712.04578. RadioML 2018 with a ResNet; addresses sim-to-OTA. Tags: [MOD][EVAL].
33. **Boegner, L., Gulati, M., Vanhoy, G., et al.** "Large Scale Radio Frequency Signal Classification" (Sig53/TorchSig). OA PDF: https://arxiv.org/pdf/2207.09918. Tags: [SIM] tooling.
34. **Boegner, L., Vanhoy, G., Vallance, P., Gulati, M., Feitzinger, D., Comar, B., Miller, R. D.** "Large Scale Radio Frequency Wideband Signal Detection & Recognition." OA PDF: https://arxiv.org/pdf/2211.10335. WBSig53 (550k samples, 53 classes) with segmentation and detection networks, including transformers, on spectrograms.\[34\] Tags: [MOD][BASE].
35. **Kulin, M., Kazaz, T., Moerman, I., De Poorter, E.** "End-to-End Learning from Spectrum Data." IEEE Access 2018. OA PDF: https://arxiv.org/pdf/1712.03987. Tags: [MOD].
36. **Tekbıyık, K., et al.** "Spectrum Sensing and Signal Identification with Deep Learning based on Spectral Correlation Function." OA: https://arxiv.org/abs/2003.08359. A CNN on SCF beats raw-IQ networks on real OTA data.\[72\] Tags: C2 cyclic branch.
37. **"Cyclo-AMC: Automatic Modulation Classification on Versal."** FPT 2025. OA PDF: http://phwl.org/assets/papers/cycloamc_fpt25.pdf. Cyclostationary features improve DNN generalization. Tags: C2, C3.
38. **"Keep It Simple: CNN Model Complexity Studies for Interference Classification Tasks."** OA PDF: https://arxiv.org/pdf/2303.03326. Tags: [EVAL] (params/FLOPs).
39. **"Time-Frequency Analysis based Deep Interference Classification for Frequency Hopping System."** OA PDF: https://arxiv.org/pdf/2108.10056. Tags: [MOD].
40. **"Interference Suppression Using Deep Learning: Current Approaches and Open Challenges."** OA: https://arxiv.org/abs/2112.08988. Flags OSR/OOD as under-studied.\[8\] Tags: gap evidence.
41. **"Deep Learning Based Transmitter Identification using Power Amplifier Nonlinearity."** OA PDF: https://arxiv.org/pdf/1811.04521. Builds a PA nonlinearity generator for DL.\[73\] Tags: C1 (randomizing PA models).
42. **Gong, Y., Chung, Y.-A., Glass, J.** "AST: Audio Spectrogram Transformer." Interspeech 2021. OA: https://arxiv.org/abs/2104.01778. Tags: [MOD] (spectrogram transformer).
43. **He, K., Zhang, X., Ren, S., Sun, J.** "Deep Residual Learning for Image Recognition." CVPR 2016. OA: https://arxiv.org/abs/1512.03385. Tags: [MOD].
44. **Perez, E., Strub, F., de Vries, H., Dumoulin, V., Courville, A.** "FiLM: Visual Reasoning with a General Conditioning Layer." AAAI 2018. OA: https://arxiv.org/abs/1709.07871. A natural mechanism for plan conditioning, as an alternative to the mask channel. Tags: C2 [MOD].

### D. Open-set / OOD

45. **Bendale, A., Boult, T.** "Towards Open Set Deep Networks" (OpenMax). CVPR 2016. OA: https://arxiv.org/abs/1511.06233. Tags: [OSR].
46. **Hendrycks, D., Gimpel, K.** "A Baseline for Detecting Misclassified and Out-of-Distribution Examples." ICLR 2017. OA: https://arxiv.org/abs/1610.02136. Tags: [OSR] (MSP).
47. **Liang, S., Li, Y., Srikant, R.** "Enhancing the Reliability of OOD Image Detection in Neural Networks" (ODIN). ICLR 2018. OA: https://arxiv.org/abs/1706.02690. Tags: [OSR].
48. **Lee, K., Lee, K., Lee, H., Shin, J.** "A Simple Unified Framework for Detecting OOD Samples and Adversarial Attacks" (Mahalanobis). NeurIPS 2018. OA: https://arxiv.org/abs/1807.03888. Tags: [OSR].
49. **Liu, W., Wang, X., Owens, J., Li, Y.** "Energy-based Out-of-distribution Detection." NeurIPS 2020. OA: https://arxiv.org/abs/2010.03496. Tags: [OSR].
50. **Dhamija, A. R., Günther, M., Boult, T.** "Reducing Network Agnostophobia" (OSCR). NeurIPS 2018. OA: https://arxiv.org/abs/1811.04110. Tags: [OSR][EVAL].
51. **Vaze, S., Han, K., Vedaldi, A., Zisserman, A.** "Open-Set Recognition: a Good Closed-Set Classifier is All You Need." ICLR 2022. OA: https://arxiv.org/abs/2110.06207. Tags: [OSR][EVAL].
52. **Chen, G., Peng, P., Wang, X., Tian, Y.** "Adversarial Reciprocal Points Learning for Open Set Recognition." TPAMI 2021. OA: https://arxiv.org/abs/2103.00953. Tags: [OSR] (extra baseline).
53. **Geng, C., Huang, S.-J., Chen, S.** "Recent Advances in Open Set Recognition: A Survey." TPAMI 2020. OA: https://arxiv.org/abs/1811.08581. Tags: [OSR].
54. **Yang, J., Zhou, K., Li, Y., Liu, Z.** "Generalized Out-of-Distribution Detection: A Survey." OA: https://arxiv.org/abs/2110.11334. Tags: [OSR][EVAL].
55. **"Efficient Open-Set Recognition for Interference Signals Based on Convolutional Prototype Learning."** *Appl. Sci.* 12(9):4380, 2022. DOI: 10.3390/app12094380. OA: https://www.mdpi.com/2076-3417/12/9/4380. Nine jamming types, with multitone and pulse jamming held out as unknowns.\[7\] This is the closest OSR-interference precedent. Tags: C2 [OSR].
56. **"An Open-Set Jamming Signal Recognition Method Based on Domain-Specific Network."** IET Commun., 2026. DOI: 10.1049/cmu2.70198. Landing: https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/cmu2.70198. Tags: [OSR].
57. **"Intelligent Radar Jamming Recognition in Open Set Environment Based on Deep Learning Networks."** *Remote Sens.* 14(24):6220, 2022. DOI: 10.3390/rs14246220. OA (MDPI). Tags: [OSR].
58. **Xiao, et al.** "Open-set Recognition of Compound Jamming Signal Based on Multi-task Multi-label Learning." IET RSN, 2024. DOI: 10.1049/rsn2.12561. Tags: [OSR] (compound events).
59. **"MDPAR: Open-Set Recognition Method for Active Radar Jamming Signals."** Preprints.org, 2025. OA: https://www.preprints.org/manuscript/202503.2079. Not peer-reviewed. Tags: [OSR].
60. **"Open Set Modulation Recognition Based on Dual-Channel LSTM Model."** OA PDF: https://arxiv.org/pdf/2002.12037. Tags: [OSR].
61. **"Class Information Guided Reconstruction for Automatic Modulation Open-Set Recognition."** OA: https://arxiv.org/abs/2312.13023. Tags: [OSR].
62. **Zhang, H., Zhou, F., Wu, Q., Yuen, C.** "FSOS-AMC: Few-Shot Open-Set Learning for AMC." OA: https://arxiv.org/abs/2410.10265. Tags: [OSR].
63. **"Adversarial Threats to Automatic Modulation Open Set Recognition in Wireless Networks."** OA: https://arxiv.org/abs/2405.05022. Tags: [EVAL] (robustness).
64. **"Open-Set RF Fingerprinting via Improved Prototype Learning."** OA PDF: https://arxiv.org/pdf/2306.13895. Tags: [OSR].
65. **"Open Set Wireless Signal Classification: Augmenting Deep Learning with Expert Feature Classifiers."** OA: https://arxiv.org/abs/2302.03749. A hybrid of DL and an expert classifier, directly relevant to the GBM baseline.\[74\] Tags: [BASE][OSR].

### E. Payload modeling

66. **Saleh, A. A. M.** "Frequency-Independent and Frequency-Dependent Nonlinear Models of TWT Amplifiers." IEEE Trans. Commun. 29(11), 1981. DOI: 10.1109/TCOM.1981.1094911 (verify). Paywalled. Tags: C1 [SIM].
67. **Casini, E., De Gaudenzi, R., Ginesi, A.** "DVB-S2 Modem Algorithms Design and Performance over Typical Satellite Channels." IJSCN 22(3), 2004. DOI: 10.1002/sat.791. Landing: https://onlinelibrary.wiley.com/doi/abs/10.1002/sat.791. Paywalled. Covers the IMUX–TWTA–OMUX chain, predistortion and phase noise.\[45\] Tags: C1 [SIM].
68. **Morello, A., Mignone, V.** "DVB-S2: The Second Generation Standard for Satellite Broad-band Services." Proc. IEEE 94(1), 2006. DOI: 10.1109/JPROC.2005.861013 (verify). OA copy: https://scispace.com/pdf/dvb-s2-the-second-generation-standard-for-satellite-broad-1hexqkf3ux.pdf. Tags: C1.
69. **ETSI/DVB.** "DVB-S2X Implementation Guidelines" (TR 102 376-2; DVB BlueBook A171-2). OA PDF: https://dvb.org/wp-content/uploads/2020/02/A171-2_DVB-S2X_Implementation-Guidelines_Draft-TR-102-376-2_v121_Apr-2020.pdf. Gives conventional and linearized TWTA curves and the multicarrier scenario (6 carriers per TWTA). Cross-polar and co-channel contributions are assumed negligible. Tags: C1 traceability.
70. **Allegue-Martínez, M., et al.** "Digital Linear Pre-compensation Technique to Enhance Predistortion Performance in Multicarrier DVB-S2 Satellite Communication Systems." *Electron. Lett.*, 2014. DOI: 10.1049/el.2014.1172. Uses a 36 MHz transponder whose IMUX/OMUX group delay masks the TWTA.\[48\] Tags: C1, C2.
71. **Beidas, B. F.** "Intermodulation Distortion in Multicarrier Satellite Systems: Analysis and Turbo Volterra Equalization." IEEE TCOM, 2011. Landing: https://www.researchgate.net/publication/224232286. Paywalled. Tags: C1, C2 (IM identifiability).
72. **"NPR and Intermodulation Distortion Modelling of Travelling-Wave Tube Amplifier of Telecommunication Spacecraft."** Landing: https://www.researchgate.net/publication/349494998. Tags: C1 validation (NPR).
73. **"Widely Linear Augmented Extreme Learning Machine Based Impairments Compensation for Satellite Communications."** OA PDF: https://arxiv.org/pdf/2506.14557. Models TWTA, IMUX/OMUX and multicarrier IM for compensation.\[75\] This shows the models are standard in satellite ML, but not in interference recognition. Tags: C1, gap.
74. **Wu, Y., Singh, G. D., Beikmirza, M., de Vreede, L. C. N., Alavi, M., Gao, C.** "OpenDPD: An Open-Source End-to-End Learning & Benchmarking Framework for Wideband PA Modeling and DPD." ISCAS 2024. OA PDF: https://arxiv.org/pdf/2401.08318. Measured DPA_200MHz data. Reports ACPR −44.69/−44.47 dBc and EVM −35.22 dB.\[50\] Tags: C1 realism, C3.
75. **Wu, Y., et al.** "OpenDPDv2." OA: https://arxiv.org/abs/2507.06849. Tags: C1.
76. **Patent: "Apparatus and Method for Optimizing the Power Utilization of a Satellite Spot Beam Transponder for a Multicarrier Transmission."** US 10103804. OA: https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10103804. Describes power robbing, weak-signal suppression and IM versus IBO.\[76\] Tags: C2 identifiability.

### F. Operational practice, statistics, regulation

77. **ITU-R S.2062-0 (09/2014).** "Carrier Identification System for FSS Occasional Use Earth Station Transmissions." OA PDF: https://www.itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.2062-0-201409-I!!PDF-E.pdf. Tags: C2 (unauthorized carrier).
78. **Via Satellite (2014).** "Preventing Adjacent Satellite Interference." https://www.satellitetoday.com/technology/2014/03/26/preventing-adjacent-satellite-interference/. Gives CID metacarrier parameters (−27.5 dB relative to host spectral density).\[9\] Tags: C2.
79. **Bates, J., Via Satellite (1 Aug 2005).** "Satellite Operators Target Interference Problem." https://www.satellitetoday.com/connectivity/2005/08/01/satellite-operators-target-interference-problem/. SUIRG database of 3,650 incidents: 62% human error, cross-pol and equipment. SUIRG president Robert Ames is quoted: "another 34 percent of interference incidents are caused by unknown sources, usually because the problems appear and disappear before the operators have a chance to document it." Tags: OSR motivation.
80. **Coleman, M. (sIRG), Microwave Journal (14 Aug 2012).** "Tackling Satellite Interference." https://www.microwavejournal.com/articles/18088-tackling-satellite-interference. Contains the quote "according to Intelsat, as much as 33 percent of interference is due to cross polarization leakage." Intelsat also attributes 47% to unauthorized carriers. Includes Monics case studies. Tags: motivation.
81. **Kratos.** "Complete VSAT Interference Mitigation" (fact sheet). https://www.kratosspace.com/-/media/communications/pdf/fact-sheet---complete-vsat-interference-mitigation.pdf. Vendor material. It echoes IRG's figure that VSATs "cause approximately 40% of all interference, and are responsible for 50% of downtime" (Martin Coleman, IRG, Dec 2014). The "50–70%" variant comes from Kratos marketing copy. Tags: motivation.
82. **Kratos (2026).** "Kratos KnownSpace Detects Sustained Iran Origin RF Interference Targeting GEO Communications." https://www.kratosspace.com/sdatracker/kratos-knownspace-detects-sustained-iran-origin-rf-interference-targeting-geo-communications. Tags: unknown-class motivation.
83. **Rohde & Schwarz.** R&S GSACSM product page. https://www.rohde-schwarz.com/us/products/aerospace-defense-security/secure-communications-options/rs-gsacsm-communications-system-monitoring_63493-636288.html. Covers PCMA and under-carrier detection by carrier cancellation.\[10\] Tags: [BASE].
84. **Integrasys.** VectorSat. https://www.integrasys-space.com/interference-detection. Tags: [BASE].
85. **Calian.** Decimator carrier-under-carrier detection. https://www.calian.com/advanced-technologies/space-satcom/decimator-carrier-under-carrier-detection/. Tags: [BASE].
86. **"A Novel and Blind Detection Scheme for Asymmetric PCMA System."** IEEE, 2014. https://ieeexplore.ieee.org/document/6967240/. Paywalled. Tags: C2.
87. **"Information Theory Analysis of Blind Detection for PCMA Satellite Communication Systems."** OA PDF (author upload, ResearchGate). Tags: C2 identifiability.
88. **"Cross-polarisation Discrimination-Induced Interference in Dual-Polarised High-Capacity Satellite Communication Systems."** Landing: https://www.researchgate.net/publication/303477998. Tags: C1 (XPD statistics).
89. **"Impact of Cross-Polarization Interference on Dual Polarization..."** JPL IPN Progress Report 42-213. OA PDF: https://ipnpr.jpl.nasa.gov/progress_report/42-213/42-213A.pdf. Tags: C1.

### G. Classical baselines and domain shift

90. **Gardner, W. A.** "Exploitation of Spectral Redundancy in Cyclostationary Signals." IEEE SP Magazine 8(2), 1991. DOI: 10.1109/79.81007 (verify). Paywalled. Tags: [BASE], C2.
91. **Chen, T., Guestrin, C.** "XGBoost." KDD 2016. OA: https://arxiv.org/abs/1603.02754. Tags: [BASE].
92. **"Approaching Domain Generalization with Embeddings for Robust Discrimination and Recognition of RF Communication Signals."** OA PDF: https://arxiv.org/pdf/2510.23186. Tags: C3.
93. **"RF-Analyzer: Can Vision-Language Models Learn RF Understanding from Synthetic Data?"** OA: https://arxiv.org/html/2605.04676v1. Tags: C3 (sim-to-real).

## Dataset and Tool Inventory

| Name | URL | License | Contents | Usability |
|---|---|---|---|---|
| SnT Satellite On-board Interference | https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/ | Free, **research-only, non-commercial** | 4 FFT representations; 12,000 train / 3,000 val; 6 subband classes\[19\]\[77\] | Baseline reproduction of Daoud et al.; no payload effects |
| SnT NGSO to GSO's Users Interference | https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/ | Research-only | Time and spectrum magnitude (800 points); 11,500 interference-free training; 4,470 mixed test; QPSK/8PSK/16APSK test sets\[78\] | Detection baseline (vs. TrID/Agon); not class-labelled by interference type |
| Fraunhofer GNSS Highway 1 | https://ieee-dataport.org/documents/gnss-interference-spectrum-highway-dataset-1 (doi:10.21227/xpm9-tt28) | CC BY 4.0 | Real highway snapshots, E1/E6 | Real-interferer realism and OSR protocol template |
| Highway 2; LC Laboratory; Jammertest 2025 | https://zenodo.org/records/21336653 · https://zenodo.org/records/21333335 · https://zenodo.org/records/21332689 | CC BY-SA 4.0 | Real and controlled GNSS interference; domain-shift splits | Unknown-class realism (pulsed, chirp, bursts) |
| TorchSig / Sig53 / WBSig53 | https://torchsig.com (paper arXiv 2211.10335) | Open source (check repo license) | 53-class narrowband; 550k wideband spectrogram samples\[35\]\[79\] | Pre-training, wideband detector baseline, waveform generation |
| OpenDPD (v1/v2) | https://github.com/lab-emi/OpenDPD | Open source (check repo) | Measured PA I/O (DPA_200MHz), PyTorch PA models\[80\]\[81\] | Amplifier-mismatch robustness; not a TWTA |
| DVB-S2X guidelines (TR 102 376-2) | dvb.org PDF above | Free | TWTA AM/AM–AM/PM curves, IMUX/OMUX, phase-noise mask\[46\] | Simulator traceability |
| Chalmers RF WebLab | (not verified in this search) | — | Remote PA measurement | Possible TWTA-like measurements; verify access |

## Recommendations

**Risks**
1. **The "simulation-only" reviewer objection.** Every comparable GEO paper is simulation-based, but TAES or TMLCN reviewers will ask about real data. Mitigate by calibrating TWTA curves to the DVB-S2X tables, validating IM levels via NPR literature, testing amplifier-model mismatch (train Saleh, test Rapp, memory polynomial or an OpenDPD-learned model), and, if possible, obtaining a handful of operator spectrum-analyzer traces for qualitative checks.
2. **Shortcut learning on the plan mask.** The mask can trivially reveal "unauthorized carrier" (energy outside the mask). Include a plan-perturbation test with stale or erroneous plans, and an ablation with the mask present but carriers moved.
3. **Carrier-under-carrier is not observable in the spectrogram.** Unless the cyclic branch is present, expect near-chance performance at low C/I. Treat this as an identifiability *result*, not a failure.
4. **Choice of unknowns.** Wideband noise versus overdrive-IM regrowth, and pulsed versus intermittent bursts, are near-duplicates. Report per-unknown AUROC and separate "near" from "far" OOD.
5. **Overclaiming "first."** Agon, the Vázquez/Eutelsat work and the open-set jamming papers partially overlap. Use precise wording such as "first to jointly model…".

**Refinements to contributions**
- C1: add randomized payload parameters (TWTA family, IMUX/OMUX order, XPD distribution) as domain randomization, and publish the generator with a fixed benchmark split and dataset card, following the S-ICDF and Fraunhofer releases.
- C2: write the identifiability analysis as a table of class × observable (co-pol PSD, cross-pol PSD, plan, IBO response, cyclic features). Back it with the ablations, and add FiLM conditioning as an alternative to the mask channel.
- C3: report the payload gap as a function of IBO distance from training, not as a single number.

**Additional baselines and metrics**
- Baselines: EDSC (signal-cancellation ED); a TrID/CAE reconstruction detector; the WBSig53 pre-trained detector; ARPL and OpenMax; a hybrid DL-plus-expert classifier (arXiv 2302.03749).
- Metrics: OSCR, FPR@95TPR, per-unknown AUROC, expected calibration error, Pd at fixed Pfa versus C/I and versus IBO, and inference latency per spectrum sweep (operators scan up to "200 carriers per second," per the Integrasys vendor claim).

**Top-15 prioritized reading list**
1. Saifaldawla et al., TMLCN 2024 (GenAI NGSO detection)
2. Yang et al., Agon, arXiv 2026
3. Daoud et al., ICASSP 2023
4. Casini, De Gaudenzi & Ginesi, IJSCN 2004
5. DVB-S2X Implementation Guidelines (TR 102 376-2)
6. Vaze et al., ICLR 2022
7. Liu et al., energy OOD, NeurIPS 2020
8. Lee et al., Mahalanobis, NeurIPS 2018
9. Dhamija et al., OSCR, NeurIPS 2018
10. Heublein et al., ION GNSS+ 2024 (real-world discrepancies)
11. Vázquez et al., Commun. Mag. 2021, plus the 2019 newsletter
12. Boegner et al., WBSig53, 2022
13. Efficient OSR for interference signals (Appl. Sci. 2022)
14. Beidas, multicarrier IM analysis (IEEE TCOM)
15. Tekbıyık et al., SCF-CNN (arXiv 2003.08359)

## Caveats

- **Search coverage.** The search budget was limited. CNKI-indexed Chinese literature and full IEEE Xplore texts were only partly checked, so a closer GEO paper could exist.
- **Unconfirmed details.** Not verified from full text: whether the Commun. Mag. 2021 interference data are Eutelsat transponder spectra (check the Zenodo PDF); the Mehr & Dovis DOI; the Chalmers RF WebLab license. DOIs marked "(verify)" were recalled from memory. CA-CFAR's origin (Finn & Johnson, RCA Review 29, 1968) is print-only.
- **Unrefereed sources.** Agon (2026) and several 2026 arXiv items are preprints and may change.

## Kaynaklar

1. [CNN-BASED ON-BOARD INTERFERENCE DETECTION IN SATELLITE SYSTEMS: AN](https://orbilu.uni.lu/bitstream/10993/55407/1/ICASSP_2023_Saed.pdf)
2. <https://orbilu.uni.lu/bitstream/10993/61484/1/TMLCN_Final.pdf>
3. <https://arxiv.org/pdf/2606.14147>
4. [An Open‐Set Jamming Signal Recognition Method Based on Domain‐Specific Network - Meidan - 2026 - IET Communications - Wiley Online Library](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/cmu2.70198?af=R)
5. [Intelligent Radar Jamming Recognition in Open Set Environment Based on Deep Learning Networks](https://doi.org/10.3390/rs14246220)
6. [Open‐set recognition of compound jamming signal based on multi‐task multi‐label learning - Xiao - 2024 - IET Radar, Sonar & Navigation - Wiley Online Library](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/rsn2.12561)
7. [Efficient Open-Set Recognition for Interference Signals Based on Convolutional Prototype Learning](https://www.mdpi.com/2076-3417/12/9/4380)
8. [Interference Suppression Using Deep Learning: Current Approaches and Open Challenges](https://arxiv.org/pdf/2112.08988)
9. [Preventing Adjacent Satellite Interference - Via Satellite](https://www.satellitetoday.com/technology/2014/03/26/preventing-adjacent-satellite-interference/)
10. [R&S®GSACSM communications system monitoring](https://www.rohde-schwarz.com/us/products/aerospace-defense-security/secure-communications-options/rs-gsacsm-communications-system-monitoring_63493-636288.html)
11. [WEAK INTERFERENCE DETECTION WITH SIGNAL CANCELLATION IN SATELLITE](https://orbilu.uni.lu/bitstream/10993/29259/1/icassp_final.pdf)
12. [Onboard Processing in Satellite Communications Using AI Accelerators](https://www.mdpi.com/2226-4310/10/2/101)
13. [Signal Processing for High Throughput Satellite Systems: Challenges in New Interference-Limited Scenarios](https://arxiv.org/pdf/1802.03958)
14. <https://arxiv.org/pdf/1906.03012>
15. [1 SPECTRUM PREDICTION AND INTERFERENCE DETECTION FOR SATELLITE COMMUNICATIONS](https://arxiv.org/pdf/1912.04716)
16. [Artificial Intelligence for Satellite Communication: A Review](https://arxiv.org/pdf/2101.10899)
17. [Machine Learning for Satellite Communications Operations](https://dl.acm.org/doi/10.1109/MCOM.001.2000367)
18. [Publications](https://fnr-smartspace-project.uni.lu/publications/)
19. [Datasets](https://fnr-smartspace-project.uni.lu/datasets/)
20. [Research](https://fnr-smartspace-project.uni.lu/research/)
21. [. . Latest updates: hps://dl.acm.org/doi/10.1145/3231884.3231901 . .](https://dl.acm.org/doi/pdf/10.1145/3231884.3231901)
22. [Research on Interference Detection and Identification Algorithms for Satellite Communication Systems](https://www.semanticscholar.org/paper/Research-on-Interference-Detection-and-Algorithms-Xiong/08c7cf481ab890ff1f6f8c45353fa4c4bc9406bc)
23. [Artificial Intelligence-based Interference Signal Recognition for Satellite Communications](https://ieeexplore.ieee.org/document/10823708/)
24. [Kernel-FastICA-Based Nonlinear Blind Source Separation for Anti-Jamming Satellite Communications](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12197282/)
25. [(PDF) Multimodal Learning for Reliable Interference Classification in GNSS Signals](https://www.researchgate.net/publication/364056875_Multimodal_Learning_for_Reliable_Interference_Classification_in_GNSS_Signals)
26. [Evaluation of (Un-)Supervised Machine Learning Methods for GNSS Interference Classification with Real-World Data Discrepancies](https://arxiv.org/pdf/2503.23775)
27. [Evaluation of (Un-)Supervised Machine Learning Methods for GNSS Interference Classification with Real-World Data Discrepancies](https://arxiv.org/html/2503.23775)
28. [Spectrum Highway Dataset 2 for Interference Classification in GNSS Data](https://zenodo.org/records/21336653)
29. [Spectrum & Low-Cost (LC) Laboratory Dataset for Interference Classification in GNSS Data](https://zenodo.org/records/21333335)
30. [Jammertest 2025 GNSS Interference Dataset](https://zenodo.org/records/21332689)
31. [GNSS Interference Spectrum Highway Dataset 1](https://ieee-dataport.org/documents/gnss-interference-spectrum-highway-dataset-1)
32. [A Machine Learning Evaluation of the Impact of Bit-Depth for the Detection and Classification of Wireless Interferences in Global Navigation Satellite Systems](https://doi.org/10.3390/electronics14061147)
33. [(PDF) A Deep Neural Network Approach for Classification of GNSS Interference and Jamming](https://www.researchgate.net/publication/384100236_A_Deep_Neural_Network_Approach_for_Classification_of_GNSS_Interference_and_Jamming)
34. [Large Scale Radio Frequency Wideband Signal Detection & Recognition](https://arxiv.org/pdf/2211.10335)
35. [\[PDF\] Large Scale Radio Frequency Signal Classification](https://www.semanticscholar.org/paper/Large-Scale-Radio-Frequency-Signal-Classification-Boegner-Gulati/773d2126b634bc008d9a6bb91c42a445096031a5)
36. [\[2003.08359\] Spectrum Sensing and Signal Identification with Deep Learning based on Spectral Correlation Function](https://arxiv.org/abs/2003.08359)
37. [Cyclo-AMC: Automatic Modulation Classification on Versal ...](http://phwl.org/assets/papers/cycloamc_fpt25.pdf)
38. [Adversarial Threats to Automatic Modulation Open Set Recognition in Wireless Networks](https://arxiv.org/pdf/2405.05022)
39. [\[2410.10265\] FSOS-AMC: Few-Shot Open-Set Learning for Automatic Modulation Classification Over Multipath Fading Channels](https://arxiv.org/abs/2410.10265)
40. [1 Open Set Modulation Recognition Based on Dual-Channel LSTM Model](https://arxiv.org/pdf/2002.12037)
41. [Class Information Guided Reconstruction for Automatic Modulation Open-Set Recognition](https://arxiv.org/html/2312.13023v1)
42. [Open-Set RF Fingerprinting via Improved Prototype Learning](https://arxiv.org/pdf/2306.13895)
43. [Open Set Wireless Signal Classification: Augmenting Deep Learning with Expert Feature Classifiers](https://arxiv.org/pdf/2302.03749)
44. [DVB-S2: The Second Generation Standard for Satellite Broad-band Services](https://scispace.com/pdf/dvb-s2-the-second-generation-standard-for-satellite-broad-1hexqkf3ux.pdf)
45. [DVB‐S2 modem algorithms design and performance over typical satellite channels - Casini - 2004 - International Journal of Satellite Communications and Networking - Wiley Online Library](https://onlinelibrary.wiley.com/doi/abs/10.1002/sat.791)
46. [S2 Extensions (DVB-S2X)](https://dvb.org/wp-content/uploads/2020/02/A171-2_DVB-S2X_Implementation-Guidelines_Draft-TR-102-376-2_v121_Apr-2020.pdf)
47. [Intermodulation Distortion in Multicarrier Satellite Systems: Analysis and Turbo Volterra Equalization](https://www.researchgate.net/publication/224232286_Intermodulation_Distortion_in_Multicarrier_Satellite_Systems_Analysis_and_Turbo_Volterra_Equalization)
48. [Digital linear pre‐compensation technique to enhance predistortion performance in multicarrier DVB‐S2 satellite communication systems - Allegue‐Martínez - 2014 - Electronics Letters - Wiley Online Library](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/el.2014.1172)
49. [(PDF) NPR AND INTERMODULATION DISTORTION MODELLING OF TRAVELLING-WAVE TUBE AMPLIFIER OF TELECOMMUNICATION SPACECRAFT](https://www.researchgate.net/publication/349494998_NPR_AND_INTERMODULATION_DISTORTION_MODELLING_OF_TRAVELLING-WAVE_TUBE_AMPLIFIER_OF_TELECOMMUNICATION_SPACECRAFT)
50. [OpenDPD: An Open-Source End-to-End Learning & Benchmarking Framework for Wideband Power Amplifier Modeling and Digital Pre-Distortion](https://arxiv.org/pdf/2401.08318)
51. [\[2507.06849\] OpenDPDv2: A Unified Learning and Optimization Framework for Neural Network Digital Predistortion](https://arxiv.org/abs/2507.06849)
52. [(PDF) Cross-polarisation discrimination-induced interference in dual-polarised high-capacity satellite communication systems](https://www.researchgate.net/publication/303477998_Cross-polarisation_discrimination-induced_interference_in_dual-polarised_high-capacity_satellite_communication_systems)
53. [Impact of Cross-Polarization Interference on Dual Polarization ...](https://ipnpr.jpl.nasa.gov/progress_report/42-213/42-213A.pdf)
54. [Satellite Interference Explained: Causes, Types, and Mitigation in SATCOM Systems](https://www.satcomindex.com/blog/satellite-interference-explained)
55. [Recommendation ITU-R S.2062-0 (09/2014) Carrier identification system for](https://www.itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.2062-0-201409-I!!PDF-E.pdf)
56. [Mitigating Satellite Interference through Carrier Identification - Via Satellite](https://www.satellitetoday.com/uncategorized/2014/08/26/mitigating-satellite-interference-through-carrier-identification/)
57. [A novel and blind detection scheme for asymmetric PCMA system](https://ieeexplore.ieee.org/document/6967240/)
58. [Information-Theory-Analysis-of-Blind-Detection-for-PCMA- ...](https://www.researchgate.net/profile/Xiang-Chen-68/publication/261383218_Information_Theory_Analysis_of_Blind_Detection_for_PCMA_Satellite_Communication_Systems/links/5428140b0cf2e4ce940c48a3/Information-Theory-Analysis-of-Blind-Detection-for-PCMA-Satellite-Communication-Systems.pdf)
59. [Decimator carrier under carrier detection - Advanced Technologies](https://www.calian.com/advanced-technologies/space-satcom/decimator-carrier-under-carrier-detection/)
60. [Vectorsat - Satellite Carrier Under Carrier Interference Detection](https://www.integrasys-space.com/interference-detection)
61. [Iran RF Interference Targeting GEO Satellites](https://www.kratosspace.com/sdatracker/kratos-knownspace-detects-sustained-iran-origin-rf-interference-targeting-geo-communications)
62. [RF-Analyzer: Can Vision-Language Models Learn RF Understanding from Synthetic Data?](https://arxiv.org/html/2605.04676v1)
63. [Approaching Domain Generalization with Embeddings for Robust Discrimination and Recognition of RF Communication Signals](https://arxiv.org/pdf/2510.23186)
64. [Convolutional Autoencoders for Non-Geostationary Satellite ...](https://orbilu.uni.lu/bitstream/10993/60597/1/Moatssim__ICC__Final.pdf)
65. [(PDF) GenAI-based Models for NGSO Satellites Interference Detection](https://www.researchgate.net/publication/381715013_GenAI-based_Models_for_NGSO_Satellites_Interference_Detection)
66. [Machine Learning for Satellite Communications Operations](https://zenodo.org/records/4705117)
67. [1 Artificial Intelligence for Satellite Communication: A Survey](https://orbilu.uni.lu/bitstream/10993/65397/1/Artificial_Intelligence_for_Satellite_Communication_A_Survey.pdf)
68. [(PDF) Onboard Processing in Satellite Communications Using AI Accelerators](https://www.researchgate.net/publication/367254401_Onboard_Processing_in_Satellite_Communications_Using_AI_Accelerators)
69. [Cognitive Interference Cancellation with Digital Channelizer for Satellite Communication](https://www.mdpi.com/1424-8220/20/2/355)
70. [GenAI for Energy-Efficient and Interference-Aware Compressed Sensing of GNSS Signals on a Google Edge TPU This work has been carried out within the DARCII project, funding code 50NA2401, sponsored by the German Federal Ministry for Economic Affairs and Climate Action (BMWK) and supported by the German Aerospace Center (DLR), the Bundesnetzagentur (BNetzA), and the Federal Agency for Cartography and Geodesy (BKG).](https://arxiv.org/html/2605.14839v1)
71. [Attention-Based Fusion of IQ and FFT Spectrograms with AoA Features for GNSS Jammer Localization](https://arxiv.org/html/2507.14167v1)
72. [(PDF) Real-World Considerations for Deep Learning in Wireless Signal Identification Based on Spectral Correlation Function](https://www.researchgate.net/publication/340021824_Real-World_Considerations_for_Deep_Learning_in_Wireless_Signal_Identification_Based_on_Spectral_Correlation_Function)
73. [Deep Learning Based Transmitter Identiﬁcation using Power Ampliﬁer Nonlinearity](https://arxiv.org/pdf/1811.04521)
74. [Revolution of Wireless Signal Recognition for 6G: Recent Advances, Challenges and Future Directions](https://arxiv.org/pdf/2503.08091)
75. [Widely Linear Augmented Extreme Learning Machine Based Impairments Compensation for Satellite Communications](https://arxiv.org/pdf/2506.14557)
76. [Apparatus and method for optimizing the power utilization of a satellite spot beam transponder for a multicarrier transmission](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10103804)
77. [Satellite On-Board Interference Detection](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/)
78. [NGSO to GSO’s Users Interference](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/)
79. [Large Scale Radio Frequency Signal Classiﬁcation](https://arxiv.org/pdf/2207.09918v1)
80. [\[Literature Review\] OpenDPD: An Open-Source End-to-End Learning & Benchmarking Framework for Wideband Power Amplifier Modeling and Digital Pre-Distortion](https://www.themoonlight.io/en/review/opendpd-an-open-source-end-to-end-learning-benchmarking-framework-for-wideband-power-amplifier-modeling-and-digital-pre-distortion)
81. [OpenDPD/README.md at main · lab-emi/OpenDPD · GitHub](https://github.com/lab-emi/OpenDPD/blob/main/README.md)
