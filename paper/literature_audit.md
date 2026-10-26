# Primary-source and novelty audit for manuscript V1

Checked 26 October 2026. This is a bounded source verification, not a systematic
review or a proof that no earlier study exists. Bibliography keys in
`references.bib` are stable; their embedded digits do not override the explicit
publication year. No account was used, no authentication was bypassed, no
hardware service was called, and no raw dataset or third-party PDF is included
in this package. Downloaded papers were read in temporary storage only.

## Verified primary sources and limits

For registered papers below, publisher-deposited Crossref metadata were read at
`https://api.crossref.org/works/` followed by the URL-encoded DOI. This verifies
title, authors, venue, year and pages; it is not a substitute for reading full
methods. A Crossref title-search request for Henarejos returned HTTP429 and was
not retried; the author preprint metadata and full text establish that citation.

| Citation key | Primary source read | What was verified / evidence limit |
|---|---|---|
| `daoud2023dataset` | DOI [10.1109/ICASSPW59220.2023.10193395](https://doi.org/10.1109/ICASSPW59220.2023.10193395); [official dataset page](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/) HTTP200 | Publisher title, six authors, ICASSP **Workshops**, 2023, pp.1–5. The official page confirms 12000/3000 training/validation rows, four full/reduced magnitude/complex FFT representations, and clean/five subband-location labels. The page's abbreviated paper title/ICASSP wording differs from the registered title/venue; bibliography uses the DOI record. [Author PDF](https://orbilu.uni.lu/bitstream/10993/55407/1/ICASSP_2023_Saed.pdf) returned503 in this pass. Detailed simulation-setting statements rely on the preserved earlier full-text audit in P1 section8, not a newly read PDF |
| `saifaldawla2024genai` | DOI [10.1109/TMLCN.2024.3418933](https://doi.org/10.1109/TMLCN.2024.3418933); [official dataset page](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/) HTTP200 | Five authors, TMLCN2,904–924,2024 verified. Official page confirms clean-only training/validation, mixed test,800 magnitudes and separate labels;801/802-column comparative tables append labels/INR/angle. It does not state numeric positive-label direction. [Author PDF](https://orbilu.uni.lu/bitstream/10993/61484/1/TMLCN_Final.pdf) returned503; equation-level simulation descriptions are attributed to P1's earlier primary-paper reading |
| `brieger2022multimodal` | DOI [10.33012/2022.18586](https://doi.org/10.33012/2022.18586); [publisher abstract](https://www.ion.org/publications/abstract.cfm?articleID=18586) HTTP200 | Correct source paper requested by the LC/FIOT release: eight authors, ION GNSS+2022,3210–3234. Publisher abstract already describes high-/low-resolution sensing, ResNet/transformer fusion and uncertainty on measured GNSS interference. Full publisher paper requires a download credit/sign-in; not accessed. No superiority comparison with its reported scores is made |
| `heublein2024discrepancies` | DOI [10.33012/2024.19887](https://doi.org/10.33012/2024.19887); [publisher abstract](https://www.ion.org/publications/abstract.cfm?articleID=19887); [author full text](https://arxiv.org/pdf/2503.23775), all HTTP200 | ION GNSS+**2024**,1260–1293, eight authors; the author preprint was posted2025. Full text already studies LC/snapshot data, laboratory/highway discrepancies, outlier detection (including many PyOD methods), pseudo-labeling and domain adaptation. Our simple LC anomaly scoring and domain cautions are not new problem definitions |
| `heublein2024robustness` | DOI [10.1109/ICL-GNSS65520.2025.11046126](https://doi.org/10.1109/ICL-GNSS65520.2025.11046126); [author full text](https://arxiv.org/pdf/2409.15114), HTTP200 | ICL-GNSS**2025**,1–7; first preprint2024. Describes a **different** controlled-low-frequency-antenna dataset, environmental/multipath robustness and characterization/localization. It must not be cited as the source of the LC/FIOT laboratory release |
| `fraunhoferLCdataset` | [Official Zenodo metadata](https://zenodo.org/api/records/21333335) HTTP200; [pinned author repository](https://github.com/FelixOtt94/FIOT_LC_laboratory/tree/2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26) | Official title, creators, DOI, crop semantics, native class names and LC feature order verified. Record publication date is **2026-07-13**, although description says latest update2024-10-30 and cites2022 work. Do not use the README date as the Zenodo publication year. Structured license is CC BY-SA4; description/README says CC BY-NC-SA4. The contradiction remains unresolved. Description's copied Jammertest download instructions are not the identity of these LC/FIOT samples |
| `wu2024opendpd` | DOI [10.1109/ISCAS58744.2024.10558162](https://doi.org/10.1109/ISCAS58744.2024.10558162); [author citation guide](https://github.com/lab-emi/OpenDPD/blob/970d6968a2947e77fc378b65efa2f2694b914cae/docs/community/citation.md); [dataset guide](https://github.com/lab-emi/OpenDPD/blob/970d6968a2947e77fc378b65efa2f2694b914cae/datasets/README.md), HTTP200 | Six authors, ISCAS2024,1–5, registered title and preferred citation. Author documentation establishes measured time-aligned I/Q datasets and differing bandwidth/sample-rate conventions. The current guide calls APA Auxiliary PA and DPA Doherty PA; detailed GaN/CMOS/device-frequency attribution in P17 comes from the earlier project source audit, not an independent remeasurement or a claim that the2024 paper describes every later APA release. Local MP NMSEs are this project's committed results, not OpenDPD paper numbers. Code Apache-2.0 is not a newly established separate raw-data license |
| `henarejos2019interference` | [Author metadata](https://arxiv.org/abs/1906.03012) and [full text](https://arxiv.org/pdf/1906.03012), HTTP200 | Three authors/title/year verified. SectionIV captures actual Ku-band DVB-S2 and cellular LTE/UMTS/GSM, then digitally scales/adds terrestrial captures. SectionIII uses autoencoder-based detection and LSTM classification. This defeats a claim that all previous satellite ML uses purely simulated inputs, but is not evidence of physical uplink interferers traversing the satellite amplifier |
| `pellaco2019spectrum` | [Author metadata](https://arxiv.org/abs/1912.04716) and [full text](https://arxiv.org/pdf/1912.04716), HTTP200 | Three authors/title/year verified. Predicts normal spectra using LSTM and detects deviations on actual Swedish Space Corporation spectra. Crossref search also returns a later expanded chapter, DOI10.1049/pbte095e_ch63; the bibliography deliberately cites the verified2019 preprint rather than conflating versions |
| `politis2017weak` | DOI [10.1109/ICASSP.2017.7953366](https://doi.org/10.1109/ICASSP.2017.7953366), publisher-deposited metadata HTTP200 | Five authors, ICASSP2017,6289–6293. Signal-cancellation detection predates this work. [Author PDF](https://orbilu.uni.lu/bitstream/10993/29259/1/icassp_final.pdf) returned503 here; detailed on-board/weak-interference analysis is supported by P1's preserved earlier full-text reading, not a fresh full-text claim |
| `etsi2014dvbs2` | [ETSI EN302307-1 V1.4.1 PDF](https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf), HTTP200 | AnnexH.7 transparent IMUX→amplifier→OMUX model, H.2/H.3 linearized/nonlinear TWTA figures and H.8 phase-noise masks read. Reference models support traceability, not empirical calibration of a new GEO payload; implemented simplified waveform is not complete DVB-S2 framing |
| `etsi2021dvbs2guide` | [ETSI TR102376-2 V1.2.1 PDF](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf), HTTP200 | Clause4.4.1 and AnnexE read; AnnexE explicitly points to attachment `tr_10237602v010201p0.zip` with amplitude/group-delay numerical entries for26/33/36MHz IMUX/OMUX. Digitization/FIR fitting in the repository is an engineering derivation, not a fresh satellite measurement |
| `saleh1981twta` | DOI [10.1109/TCOM.1981.1094911](https://doi.org/10.1109/TCOM.1981.1094911), publisher-deposited metadata HTTP200 | Title, author, IEEE TCOM29(11),1715–1720,1981 verified. Historical alternative model citation; full text not newly retrieved here. It must not replace the repository's default reference TWTA curves |
| `smartspaceDatasets` | [Official research terms](https://fnr-smartspace-project.uni.lu/datasets/), HTTP200; dataset pages above | Explicit research-only/noncommercial restriction. Access failure is established by the separate dated P8/public-data audit, not by confusing public description pages with raw downloads. No raw SmartSpace metrics exist |

Full-text details above are deliberately qualitative. We do not transplant other
papers' performance percentages into our result tables or imply identical
populations, representations, splits, calibration or label sets.

## Citation-safe related-work synthesis

Satellite interference detection already includes cancellation-based detection,
real received-spectrum prediction and hybrid real-capture experiments. SmartSpace
provides native on-board location and NGSO detection tasks, not a public measured
eight-type dual-polarization GEO benchmark. Measured GNSS multimodal classification,
uncertainty, outlier detection and data discrepancies are substantial existing
research; neither the use of GNSS measurements nor the observation that domain
shifts matter is novel here. OpenDPD supplies measured PA behavior and a modeling
framework, while ETSI supplies reference satellite-channel structures. These
literatures motivate careful comparison but do not make GNSS or Doherty captures
measurements of GEO field interference.

## Novelty and appropriate publication category

The current evidence does **not** support a new-recognizer research-article claim,
first satellite interference ML, first measured GNSS anomaly detection, proved
cross-domain generalization, or a statistically confirmed payload-gap advantage.
Simply assembling those established lines is insufficient novelty.

The bounded contribution is instead a **reproducibility/comparative-methods
audit** of a particular released-data snapshot: explicit crop-parent isolation,
unavailable LC coverage, frozen clean-only calibration, all fixed scorers retained
including an unfavorable RGB-level result, and a separate physical account of
why each representation cannot answer the original GEO questions. The evidence
links limitations rather than demonstrating one transferable model. The work can
be submitted honestly as a reproducibility report, comparative-methods short
paper or data/methods note if a suitable venue values these results. A current
venue-specific novelty judgment and author approval remain unresolved; this
bounded check does not establish priority or guarantee acceptance.
