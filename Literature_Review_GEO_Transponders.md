# Literature Review — Payload-Aware Open-Set Interference Recognition for GEO Transponders

Original draft: 20 October 2026 · Technical revision: 23 October 2026

> Review status: critical technical and methodological corrections applied. This is a narrative review and proposed research design, not an experimental results report. The original 95 references are retained; this revision checks selected central sources rather than certifying the full bibliography. Appendix A records the changes and remaining verification tasks.

## Notation

Symbols are defined where first used; this list collects them. Signals are complex baseband.

| Symbol | Meaning | Unit |
| --- | --- | --- |
| x(t), y(t) | Composite uplink signal; downlink observation | Saleh-normalized amplitude |
| s_k(t), P_k, f_k, θ_k(t), K | k-th planned carrier: waveform, power, centre frequency, uplink phase noise; number of carriers | –, W, Hz, rad, – |
| i_m(t), M | Uplink interferer; number of uplink interferers | – |
| i_{d,l}(t) | Interferer entering on the downlink | – |
| n_u(t), n_d(t), N_0 | Uplink and downlink noise; noise power spectral density | –, –, W/Hz |
| h_IMUX, h_OMUX | Input and output multiplexer impulse responses | – |
| u(t), r, r_sat | TWTA input; its envelope; envelope at saturation | Saleh-normalized |
| 𝒢{·}, A(r), Φ(r) | TWTA operator; AM/AM and AM/PM characteristics | –, Saleh-normalized, rad |
| α_a, β_a, α_φ, β_φ | Saleh model parameters | – |
| IBO, P_in, P_in,sat | Input back-off; total mean input power; single-carrier input power at saturation | dB, W, W |
| f_IM3, C/IM₃, c | Third-order intermodulation frequency; carrier-to-IM3 ratio; constant of the IM3 power law | Hz, dB, dB |
| x_co, x_x, x'_co | Uplink signals per polarization; co-polar transponder input after uplink leakage | – |
| z_co, z_x, y_co, y_x, n_co, n_x | Transponder outputs, observations and noise per polarization | – |
| κ_u, κ_d, XPD | Uplink and downlink polarization coupling (complex); cross-polar discrimination | –, –, dB |
| s_h, s_u, T_h, T_u | Host and under-carrier waveforms; their symbol periods | –, s |
| ρ, (C/I)lin, (C/I)dB | Under-carrier power ratio, ρ = 1/(C/I)lin = 10^(−(C/I)dB/10); linear and logarithmic carrier-to-interference ratios | –, –, dB |
| S_y(f), S_y^α(f), α, T_s, β | Power spectral density; spectral correlation function; cycle frequency; symbol period; roll-off | W/Hz, W/Hz, Hz, s, – |
| Λ, ŝ[n], γ, γ_i, ℋ₀, ℋ₁ | Detection statistic; reconstructed desired signal; thresholds; hypotheses | W (Λ, γ) |
| η, N_r, ℛ_i, P_j | CA-CFAR scale factor; number of reference cells; reference cells of bin i; cell power | –, –, –, W |
| P_FA, P_D | False-alarm and detection probabilities | – |
| C, g_k(x), v, μ_k, Σ, τ | Number of known classes; logits; embedding; class means; shared covariance; rejection threshold | – |
| S(x), S_MSP, S_E, S_M, T_E | Open-set score and its three forms; temperature of the energy score | – |
| 𝒟_K, 𝒟_U | Known-class and unknown-class test data | – |
| CCR, FPR, OSCR, Prec_k, Rec_k | Correct classification rate; false-positive rate; open-set classification rate; per-class precision and recall | – |
| Δ_payload(ω), G(ω), 𝓜, 𝒟_ω, ω | Payload gap; generalization curve; metric; test data at condition ω; test condition | – |

## 1. Introduction

Interference is a routine, recurring cost of operating geostationary (GEO) satellites, not a rare fault. Early data (2005) from a database of 3,650 incidents compiled by the Satellite Users Interference Reduction Group (SUIRG) attributed 62% of cases to human error, cross-polarization and equipment problems [1]. Operator figures tell a similar story: Intelsat has attributed up to 33% of its interference to cross-polarization leakage and 47% to unauthorized carriers [2], and the Interference Reduction Group (IRG) has estimated that VSAT terminals cause about 40% of all interference and half of the resulting downtime [3].

These statistics come from industry and trade sources rather than peer-reviewed measurement, but they agree on the main point. A small set of mechanisms dominates the problem: mispointed antennas, misconfigured equipment, cross-polar leakage and carriers transmitted where they should not be. Mispointing and misconfiguration alone are estimated to cover 70–80% of cases [4]. Intentional jamming adds to this picture; in 2026, sustained interference with on/off cycling was reported against at least six commercial GEO satellites [5].

Operators find most of these events through downlink spectrum monitoring. Carriers are measured against expected power levels and spectral masks, threshold alarms fire on deviations, and analysts inspect spectrum-analyzer traces to work out what happened [2], [6]. The operator-oriented anomaly detectors discussed here use a threshold on a deviation score [4]. Detection and mechanism recognition are distinct tasks; their relative difficulty depends on interference power and the available observations. The costly half is recognition: deciding which mechanism is at work, because each points to a different response — repointing a terminal, correcting a polarization setting, locating an unauthorized uplink, or reducing the payload drive.

Two properties of the operator's observation make recognition harder than it first appears, and they shape this project. First, the monitoring station sees the downlink, after the uplink signal has passed through the bent-pipe transponder's input multiplexer (IMUX), traveling-wave tube amplifier (TWTA) and output multiplexer (OMUX). Detection on the ground is degraded by exactly this chain of transponder distortion and downlink noise [7], and the nonlinear amplifier creates intermodulation products that can resemble external interference. Second, the catalogue of interference types is not closed. New jamming patterns keep appearing [5], and the same early SUIRG data left a further 34% of incidents attributed to unknown sources, mostly because they appeared and disappeared before they could be documented [1]. Some of those were probably ordinary carriers, but the figure shows how often operators meet events they cannot name. A recognizer forced to assign every event to a known class will mislabel whatever falls outside its catalogue.

This review is organized around those two properties. Section 2 covers classical monitoring and detection practice, and Section 3 the learning-based detectors and classifiers proposed for satellite, GNSS and general RF interference. Section 4 examines how the transponder has been modeled, and Section 5 asks which observables can separate the interference mechanisms of interest. Section 6 reviews open-set recognition, Section 7 evaluation under distribution shift, and Section 8 positions this project and its contributions against the literature.

## 2. Monitoring practice and classical detection

Classical interference detection treats the problem as hypothesis testing on received energy. One well-developed line of work places a monitoring unit on board the satellite: the desired signal is decoded and subtracted, and an energy detector is applied to the residual [8]. Analyses of imperfect cancellation [8] and of weak interference [9] showed that cancellation substantially improves the detection of low-power interference under noise and signal-power uncertainty. Pérez-Neira et al. framed the advantage of on-board detection as avoiding the downlink noise and transponder distortion that degrade detection on the ground [7]. For a ground operator this is the key observation: the monitored spectrum is not a clean view of the uplink.

With y[n] the received samples and ŝ[n] the reconstructed desired signal, the detector compares the residual energy with a threshold γ set for a target false-alarm probability:

$$
\Lambda = \frac{1}{N}\sum_{n=0}^{N-1} \left| y[n] - \hat{s}[n] \right|^{2} \;\underset{\mathcal{H}_0}{\overset{\mathcal{H}_1}{\gtrless}}\; \gamma
$$

Imperfect cancellation leaves part of the desired signal in Λ, which is the effect analyzed in [8].

Ground monitoring relies on the standard tools of spectral detection. Cell-averaging constant false-alarm rate (CA-CFAR) detection [10] sets adaptive thresholds against the local noise floor and is the natural baseline for spotting unexpected spectral peaks. Cyclostationary detection [11] exploits the periodic statistics of modulated signals; it is more robust at low SNR and can separate signals that overlap in frequency, at higher computational cost. Simpler schemes, such as tone detection within the subchannels of an on-board digital channelizer [12], target a single interference type. Energy tests principally detect deviations from the expected signal or noise model. Cyclostationary methods can additionally expose symbol rates and other waveform structure, but these features alone need not identify an operational cause such as antenna misalignment or an unauthorized transmitter.

For a spectral bin i with N_r reference cells R_i around it, CA-CFAR scales the mean reference power by a factor η chosen for the design false-alarm probability. For square-law detection in exponentially distributed noise,

$$
\gamma_i = \eta \cdot \frac{1}{N_r}\sum_{j \in \mathcal{R}_i} P_j, \qquad \eta = N_r\left(P_{\mathrm{FA}}^{-1/N_r} - 1\right)
$$

This form holds for single-look periodogram bins in homogeneous noise. Welch-averaged cells follow a Gamma law and need the L-look expression, and in a loaded transponder the reference cells should be selected from a declared plan-masked residual rather than across carriers. Masking does not restore the ideal noise law by itself: spectral leakage, window correlation and nonuniform residuals require empirical false-alarm calibration. Distinguish per-bin false alarms from the probability of at least one alarm over a frame or monitoring interval. The cyclostationary counterpart is introduced in Section 5, where it matters most.

Identification has instead been pursued through cooperation and regulation. ITU-R Recommendation S.2062 defines a carrier identification (CID) system for occasional-use earth stations [13], and the DVB-CID metacarrier embeds a transmitter identity 27.5 dB below the host carrier's spectral density [14]. CID resolves the source of a carrier when the offending terminal transmits one, which is precisely what unauthorized or misconfigured equipment cannot be relied upon to do.

The hardest operational case, carrier-under-carrier interference, shows the limit of energy-based detection. When an unwanted carrier sits underneath an authorized one, the composite spectrum looks almost normal. Commercial monitoring systems — Rohde & Schwarz GSACSM [15], Integrasys VectorSat [16], Calian Decimator [17] and Kratos Monics [3] — advertise carrier-under-carrier detection. Where the method is documented, it works by cancelling the known host carrier and inspecting the residual [15], or by PCMA carrier cancellation [3], rather than by reading the power spectrum. Their performance claims are vendor statements without independent benchmarks. This practice already suggests that a learned recognizer cannot rely on the power spectrum alone for every class; Section 5 returns to this point.

## 3. Learning-based interference recognition

Deep learning entered satellite interference work as a way to replace hand-set thresholds with learned models of normal behavior. An early study trained a sparse autoencoder on real Ku-band DVB-S2 captures to flag interference by reconstruction error, and added an LSTM to classify digitally inserted terrestrial interferers such as LTE, UMTS and GSM [18]. A parallel approach trained an LSTM to predict the interference-free spectrum from real operator recordings and flagged deviations from that prediction [19]. In ESA-funded work co-authored with Eutelsat, an interference detector reduced the false-detection probability by 44% compared with other approaches [6]. These systems learn what clean spectra look like, not what different interferers look like, so they detect but do not recognize.

The most active recent line, from SnT's SmartSpace project, learns from simulated interference. An on-board CNN localized NGSO interference to one of five subbands of a GSO uplink, with reduced-size FFT magnitudes giving the best accuracy [20]. On the ground side, a sequence of reconstruction-based detectors for NGSO-to-GSO downlink interference [21]–[23] culminated in a transformer detector (TrID) that improved interference-detection accuracy by up to 31.23% over the compared autoencoder models and an energy detector, with time-domain inputs outperforming spectral ones [23]. The 2026 Agon framework adds masked-autoencoder pre-training, higher-order-statistics attention and a multi-task head, reaching an AUC of 0.9327 on the public NGSO–GSO dataset against 0.8318 for TrID-like baselines [24]. Closed-set classifiers recognize five to fifteen interference types — tones, narrowband, sweep, pulse, noise and spread-spectrum interference, and pairwise combinations — mostly in simulated AWGN channels [25]–[27], and on-board studies show such models can run on candidate on-board AI accelerators [28]. Surveys of AI for satellite communications count interference management among the most developed applications [29]–[31].

Several of the simulation-based detection studies reviewed above use additive desired-signal and interference models. That abstraction does not by itself establish performance for a ground monitor observing a loaded nonlinear transponder. The relevant comparison is whether a study explicitly models and independently varies multicarrier loading, amplifier behavior, multiplexer filtering, polarization coupling and carrier-plan information. Real captures in [6], [18] and [19] can contain these effects without providing controlled labels, while Agon includes a hardware testbed [24]. Accordingly, absence of a documented controlled payload sweep is the gap supported here; universal absence of payload effects across all cited work is not asserted. Anomaly detection also differs from the joint task of naming known mechanisms and rejecting unseen classes.

The closest methodological precedent is in GNSS. Fraunhofer IIS has built a sustained program of interference classification on real recordings: multimodal fusion of spectral and time-domain inputs with Monte Carlo dropout as a reliability measure [32], low-cost monitoring stations [33], few-shot learning for novel interference classes [34], and evaluation under real-world discrepancies between controlled and field data [35]. Related work disentangles interference factors with variational autoencoders [36], releases fully simulated datasets with documented generators [37], and classifies jamming observed from terrestrial and LEO stations [38]. GNSS interference differs physically from the GEO case — the desired signal lies below the noise floor, and the interferer catalogue is dominated by chirp and pulsed sources — but the GNSS literature sets the evaluation standard we adopt: condition-based splits, explicit novel-class protocols and uncertainty-aware rejection.

General RF deep learning supplies the model building blocks. Over-the-air experiments with RadioML established that residual networks classify radio signals well, and that simulation-trained models degrade on real captures [39]. TorchSig's Sig53 [40] and WidebandSig53 [41] moved recognition from narrowband snippets to wideband spectrograms containing many simultaneous signals, the representation closest to a transponder monitoring view. Beyond end-to-end learning from spectrum data [42], two results bear directly on our design: CNNs trained on spectral-correlation-function inputs outperform raw-signal networks on real captures [43], and cyclostationary features can be paired with a compact deep classifier at low energy cost on an FPGA [44]. Both motivate the cyclic-feature branch. On model size, small CNNs have been shown to suffice for interference classification [45], and time–frequency representations work well for interference in frequency-hopping systems [46]. A survey of deep-learning interference suppression also identifies open-set and out-of-distribution recognition as under-studied [47]. Residual networks [48], spectrogram transformers [49] and feature-wise conditioning [50] provide the standard mechanisms for a plan-conditioned recognizer.

## 4. The transponder as part of the observation

In a bent-pipe GEO transponder, every carrier the operator monitors has passed through the same nonlinear chain. The IMUX selects the transponder band, the TWTA amplifies the composite signal near saturation, and the OMUX filters the result before downlink. The Saleh model [51] remains the standard description of TWTA amplitude-to-amplitude (AM/AM) and amplitude-to-phase (AM/PM) conversion, with the operating point set by the input back-off (IBO). The DVB-S2 system design [52] and its accompanying modem studies [53] established the IMUX–TWTA–OMUX chain, phase-noise masks and predistortion as the reference satellite channel. The DVB-S2X implementation guidelines [54] extend this with tabulated curves for conventional and linearized TWTAs and with multi-spot scenarios in which two carriers share one amplifier. This is the reference to which our simulator is made traceable.

**Observation-chain schematic.** For each polarization, uplink carriers, uplink interferers and uplink noise enter the IMUX–TWTA–OMUX chain. Downlink interferers and downlink noise are added after that chain. Uplink and downlink polarization coupling are represented separately (Section 5). The proposed recognizer receives co-polar and cross-polar spectrograms, carrier-plan metadata and cyclic features. The supplied Markdown contained a figure placeholder; no original figure asset is available here.

In compact form, the composite uplink with K planned carriers and M interferers is

$$
x(t) = \sum_{k=1}^{K} \sqrt{P_k}\, s_k(t)\, e^{\,j\left(2\pi f_k t + \theta_k(t)\right)} + \sum_{m=1}^{M} i_m(t) + n_u(t)
$$

where s_k(t) has unit mean power and represents the selected pulse-shaped modulation, θ_k(t) is the phase noise of the k-th uplink and n_u(t) is uplink noise; the satellite local-oscillator phase noise, common to all carriers in the transponder, is applied at the IMUX input. The downlink observation is

$$
y(t) = \left(h_{\mathrm{OMUX}} * \mathcal{G}\left\{h_{\mathrm{IMUX}} * x\right\}\right)(t) + \sum_{l} i_{d,l}(t) + n_d(t)
$$

where i_{d,l}(t) are interferers that enter on the downlink and never pass through the TWTA — adjacent-satellite signals received by the monitoring antenna, or terrestrial C-band emitters [2] — so the generator labels which path each interferer takes. All amplitudes and powers in the nonlinear model use a declared normalized reference; P_k is a relative power weight unless an explicit watt-to-normalized-power mapping is supplied. Noise PSD and filter normalization must use the same reference. Using a DVB-S2 modulation and pulse shape alone does not establish a complete DVB-S2 frame, coding and pilot implementation. The common satellite-oscillator phase term must also be included explicitly in the implemented chain; it is omitted from the compact equations above. The memoryless TWTA operator acts on the envelope of its input u(t):

$$
\mathcal{G}\{u\}(t) = A\big(|u(t)|\big)\, e^{\,j\left(\arg u(t) + \Phi(|u(t)|)\right)}, \qquad A(r) = \frac{\alpha_a r}{1+\beta_a r^2}, \qquad \Phi(r) = \frac{\alpha_\phi r^2}{1+\beta_\phi r^2}
$$

The output amplitude peaks at r_sat = 1/√β_a, and the operating point is set by the input back-off, where for multicarrier operation P_in is the total mean input power referred to single-carrier saturation

$$
\mathrm{IBO} = 10\log_{10}\frac{P_{\mathrm{in,sat}}}{P_{\mathrm{in}}}\ \mathrm{dB}
$$

For the illustrative coefficients αa = 2.1587, βa = 1.1517, αφ = 4.0033 and βφ = 9.1040, the AM/AM and AM/PM expressions can be evaluated analytically. The original Figure 2 is not embedded in this file. Its numerical caption is therefore omitted pending a reproducible plot with explicit amplitude and power normalization. A single-carrier continuous-wave calculation must not be interpreted as the mean response to a fluctuating multicarrier envelope.

What matters for recognition is that the transponder creates spectral structure of its own. When several carriers share a TWTA, third-order intermodulation products fall at predictable frequencies such as 2f₁ − f₂, and their level rises faster than the carriers as drive increases [55]. The multiplexer filters add group delay that interacts with the amplifier: in a 36 MHz multicarrier DVB-S2 transponder, IMUX/OMUX group delay masks the TWTA characteristic seen at the output [56]. Simulated noise-power-ratio tests of a Saleh-modelled space TWTA show how much intermodulation fills the band under loading [57], and multicarrier operation also causes power robbing and suppression of weak carriers [58]. Seen from the monitoring station, payload intermodulation is therefore a structured, plan-dependent spectral signature that sits alongside, and can be confused with, external interference.

For carriers at f_1, …, f_K, the third-order products fall at

$$
f_{\mathrm{IM3}} \in \{2f_i-f_j: i\ne j\} \cup \{f_i+f_j-f_k: i,j,k\ \mathrm{pairwise\ distinct}\}
$$

Far below saturation, third-order power grows by 3 dB for each decibel of drive while the carriers grow by 1 dB, so asymptotically the carrier-to-intermodulation ratio improves by 2 dB per dB of back-off [55], [58]:

$$
P_{\mathrm{IM3,dB}} \approx 3P_{\mathrm{in,dB}} + c \quad\Rightarrow\quad \frac{\partial\,(C/\mathrm{IM}_3)}{\partial\,\mathrm{IBO}} \approx 2\ \mathrm{dB/dB}
$$

The approximate 2 dB/dB law is a weakly nonlinear, fixed-loading result, not a guaranteed slope near saturation. With modulated carriers, third-order mixing produces occupied bands and cross-modulation as well as discrete-tone products. The original Figure 3 placeholder and the associated model-specific slope and suppression figures are not retained as verified results because the generation code, random seeds, normalization, PSD settings and outputs were not supplied. Reproducible experiments are needed before quoting those values. Plan-consistent product locations and response to drive are diagnostic evidence, but external uplink interferers can coincide with those locations and also interact with the nonlinear payload.

The satellite literature treats this chain as an impairment to compensate, not as context for recognition. Volterra equalization of multicarrier intermodulation [55], learned impairment compensation over TWTA and phase-noise models [59] and predistortion [53] all model the transponder carefully, but toward a different goal. Interference-recognition studies leave it out (Section 3). The omission has been noted in passing: a recent anti-jamming study observes that existing methods lack modeling of the distortion caused by transponder nonlinearity [60], though its own focus is suppression rather than recognition.

Measured amplifier data is harder to obtain than models. OpenDPD [61], [62] provides measured input–output data from a wideband power amplifier together with a PyTorch framework for behavioral modeling. It is a solid-state device, not a TWTA, so it cannot serve as ground truth for a GEO payload. It is useful instead as a source of model mismatch: a recognizer trained on Saleh-model data can be tested against a different, measured nonlinearity. Work on transmitter identification has shown that randomized amplifier nonlinearity models can be generated at scale for deep learning [63], which supports randomizing payload parameters during data generation rather than fixing a single transponder.

## 5. Interference mechanisms and identifiability

The interference classes in this project are not equally easy to tell apart, and the literature suggests that some cannot be separated from a single-polarization power spectrum at all. The main confusable groups are considered in turn, since they determine which observables the recognizer needs.

Cross-polarization leakage is among the largest single causes of interference in operator statistics [2]. It arises when an earth-station feed is misaligned [2], when rain or ice depolarization reduces the cross-polar discrimination (XPD) [64], or when antenna XPD is insufficient for a dual-polarized system [65]. In a co-polar spectrum, leaked energy looks like any other unexpected carrier. Observing the opposite polarization supplies a useful reference for testing whether unexpected energy is consistent with leakage. This does not guarantee unique attribution, and other evidence, such as terminal measurements or polarization adjustments, can also support diagnosis. The DVB-S2X guidelines model cross-polar interference only as an aggregate C/I — about 24 dB at Ku-band and 17 dB at Ka-band in deep fade — built from antenna cross-polar isolation and depolarization [54]. They do not model leakage of identifiable carriers from the opposite polarization, which is what recognition needs, so the dual-polarization observation extends the reference model and draws on XPD studies [64], [65].

Cross-polar leakage enters at two points. Uplink leakage from a misaligned earth-station antenna adds a copy of the opposite-polarization signal before the IMUX, so it passes through the co-polar transponder. Downlink depolarization and the monitoring antenna's XPD couple the transponder outputs. With complex coupling coefficients κ_u and κ_d that generally differ,

$$
x'_{\mathrm{co}}(t) = x_{\mathrm{co}}(t) + \kappa_u\, x_{\mathrm{x}}(t), \qquad y_{\mathrm{co}}(t) = z_{\mathrm{co}}(t) + \kappa_d\, z_{\mathrm{x}}(t) + n_{\mathrm{co}}(t), \qquad \mathrm{XPD} = -20\log_{10}|\kappa|\ \mathrm{dB}
$$

with an analogous equation for the cross-polar channel, using separately specified reverse-direction coefficients rather than assuming symmetric coupling, where z_co and z_x are the transponder outputs of Section 4 and x'_co is the co-polar transponder's input. Downlink leakage is a scaled copy of z_x and can be tested by correlating y_co with y_x. Uplink leakage appears in y_co as a nonlinearly distorted, possibly differently filtered copy of a carrier that is also visible in y_x, so the same test is only approximate. These cross-channel tests require synchronized, frequency-aligned observations and adequate reference-channel SNR. The scalar coupling model approximates matched polarization paths over the band; per-carrier uplink alignment and frequency-dependent coupling require a richer model. Even with both observations, simultaneous uplink and downlink leakage need not be uniquely separable.

Unplanned carriers form a second group. An unauthorized carrier, a carrier at the wrong frequency and adjacent-satellite interference all add energy outside the expected occupancy, and their spectra can be nearly identical. What separates them is whether the energy is consistent with the operator's carrier plan, and where it originates. CID answers the second question when the transmitter cooperates [13], [14]. Without CID or geolocation, adjacent-satellite and unauthorized carriers may be inseparable from the downlink alone, and a recognizer should report that confusion rather than hide it.

Carrier-under-carrier interference is the clearest identifiability limit. In paired carrier multiple access (PCMA), two carriers deliberately share one band, and blind detection of the weaker one is a known hard problem [66]; information-theoretic analysis bounds what blind detection can achieve [67]. Unintended carrier-under-carrier events inherit this difficulty, which is why commercial tools cancel the host carrier before looking for a residual [15]–[17]. At realistic carrier-to-interference ratios the composite power spectrum is essentially that of the host. Features that respond to a second symbol rate, such as the cyclic spectrum [11], [43], are the natural candidates for making this class observable.

The difficulty is visible in second-order statistics. With a host carrier s_h, an under-carrier s_u at power ratio ρ = 10^(−(C/I)dB/10) and independent stationary noise,

$$
y(t) = s_h(t) + \sqrt{\rho}\, s_u(t) + n(t) \quad\Longrightarrow\quad S_y(f) = S_h(f) + \rho\, S_u(f) + N_0
$$

For uncorrelated carriers with identical spectral shapes, a 20 dB C/I raises the host-plus-interferer PSD by 10 log₁₀(1 + 0.01) ≈ 0.043 dB relative to the host alone. Equal bandwidth alone does not provide this pointwise bound: different spectral shapes can produce larger changes in particular bins. Added noise reduces the relative change. This additive model is an illustration before nonlinear distortion, or for signals combined after the payload; an uplink under-carrier must instead pass through the composite nonlinear chain. Weak-carrier suppression depends on loading and operating point. The spectral correlation function

$$
S_y^{\alpha}(f) = \lim_{T \to \infty} \frac{1}{T}\, \mathbb{E}\left[ Y_T\!\left(f + \tfrac{\alpha}{2}\right) Y_T^{*}\!\left(f - \tfrac{\alpha}{2}\right) \right]
$$

Under the ideal model of independent, zero-mean symbols shaped by an RRC pulse with 0 < roll-off < 1, the ordinary nonconjugate second-order SCF has nonzero symbol-clock components at α = ±1/T_s within its support [11]. This is a model-specific statement: pilots, framing, coding, conjugate cyclic statistics and nonlinearity may introduce additional structure. Stationary noise has zero expected SCF at nonzero cycle frequencies, but finite-record estimates retain noise and host-related variance.

If an under-carrier has a cycle frequency outside the host’s cyclic support, the ideal additive expectation there contains its contribution and not the host’s. Different symbol periods alone are insufficient to guarantee that condition for a structured DVB waveform. As interference power decreases, longer observations are generally needed; a universal observation-length law proportional to (C/I)^2 is not claimed without an estimator-specific derivation. Identical symbol rates can make the cyclic signatures overlap. Frequency offsets, higher-order structure, blind PCMA methods [66] or decoded-host cancellation [3], [15] may then provide complementary evidence. Cyclic features are therefore a candidate input, not a necessary or sufficient condition for all carrier-under-carrier detection.

Finally, payload intermodulation must be separated from external interference. Here the transponder physics helps: intermodulation products fall at frequencies set by the carrier plan and change with input back-off in a predictable way [55], [58], whereas external interferers are not constrained to originate from that mixing process. Frequency coincidences and payload-induced changes to uplink interferers remain possible. A recognizer that knows the carrier plan can check whether energy falls at the predicted IM frequencies; one that sees a single unannotated spectrum cannot. Behaviour across drive levels can strengthen the diagnosis, but a monitoring station rarely controls or knows the uplink drive, so the plan is the practical observable. The IMUX/OMUX masking effect [56] complicates this, since the observed signature depends on the filters as well as the amplifier.

Within the reviewed set, we did not identify a formal observability analysis covering this complete GEO monitoring configuration; the closest formal treatment is the information-theoretic study of blind PCMA detection [67]. Mapping each class to the observables it requires — co-polar spectrum, cross-polar spectrum, carrier plan, response to back-off, cyclic features — is therefore open, and contribution C2 addresses it directly.

Table 1 states this argument as a working hypothesis. The ablations in Section 7 test the cross-polar, plan-mask and cyclic columns; the temporal column is the time axis of the spectrogram itself.

**Table 1.** Proposed input priorities: ● primary evidence in the selected design, ○ supplementary evidence, – not emphasized. These entries are hypotheses, not proofs of necessity, sufficiency or absence of information.

| Class | Co-pol spectrogram | Cross-pol spectrogram | Carrier-plan mask | Temporal behaviour | Cyclic features |
| --- | --- | --- | --- | --- | --- |
| Clean | ● | ○ | ● | ○ | ○ |
| CW | ● | ○ | ● | – | ○ |
| Swept CW | ● | – | ○ | ● | – |
| Cross-pol leakage | ● | ● | ○ | – | – |
| Adjacent-satellite | ● | – | ● | ○ | ○ |
| Unauthorized carrier | ● | – | ● | ○ | ○ |
| Carrier-under-carrier | ○ | – | ○ | – | ● |
| Overdrive IM | ● | – | ● | ○ | – |

Two cases deserve comment. CW needs the plan to be told apart from beacons, pilots and plan-predicted IM lines, and the cross-polar view to be told apart from a modulated carrier that has collapsed to CW on the opposite polarization [2]. Adjacent-satellite and unauthorized carriers share the same row, which suggests — but does not prove — that they may be hard to separate from a single downlink snapshot; level dynamics or geolocation may still differ, and C2 measures their confusion empirically. Cyclic features are prioritized for carrier-under-carrier experiments, and the temporal axis for swept-CW experiments. Neither priority excludes alternative detectors. Labels also mix waveform types, entry paths and operational causes; their sampling rules must prevent overlap or expose ambiguous cases. Adjacent-satellite origin cannot generally be established from plan inconsistency alone.

## 6. Open-set recognition

A recognizer trained on a fixed list of classes will, by default, assign every input to one of them. Open-set recognition (OSR) and out-of-distribution (OOD) detection address this by allowing a model to reject inputs that belong to no known class [68], [69]. For a GEO operator, rejection is not an edge case: new forms of jamming continue to appear [5], and in early operator data about a third of incidents were never attributed to a source [1].

The methods most relevant here are post-hoc scores computed on a trained classifier. Maximum softmax probability (MSP) is the standard baseline [70], and ODIN sharpens it with temperature scaling and input perturbation [71]. The energy score replaces the softmax with a log-sum-exp of the logits and separates in- and out-of-distribution data more reliably [72]. The Mahalanobis score fits class-conditional Gaussians to the network's embeddings and measures distance to the nearest class [73]. OpenMax [74] calibrates activation-vector tails and modifies output probabilities for a trained network; it is not, by itself, a representation-learning objective. Adversarial reciprocal-point learning [75] instead introduces training-time objectives. A result with direct consequences for experimental design is that a well-trained closed-set classifier, scored with MSP or maximum logit, matches or beats many specialized OSR methods [76]. Open-set performance is therefore tied to closed-set accuracy, and the open-set classification rate (OSCR) [77] measures both together.

All three post-hoc scores fit one decision rule. With logits g_k(x) over C known classes, embedding v = v(x), and class means μ_k and shared covariance Σ estimated on training data, a threshold τ on a score S(x) turns the classifier into an open-set recognizer:

$$
\hat{y}(x) = \begin{cases} \arg\max_k g_k(x), & S(x) \ge \tau \\ \text{unknown}, & S(x) < \tau \end{cases}
$$

$$
S_{\mathrm{MSP}}(x) = \max_k \frac{e^{g_k(x)}}{\sum_{j} e^{g_j(x)}}, \qquad S_{\mathrm{E}}(x) = -E(x) = T_E \log \sum_{k} e^{g_k(x)/T_E}, \qquad S_{\mathrm{M}}(x) = -\min_k \left(v - \mu_k\right)^{\top} \Sigma^{-1} \left(v - \mu_k\right)
$$

Here S_E is negative free energy, so larger values indicate greater known-class confidence, consistently with the acceptance rule [72]. It is not a calibrated probability. Estimate class means and covariance on training embeddings; choose covariance shrinkage, temperatures and thresholds using designated validation data.

OSCR sweeps τ and traces the correct classification rate on known data D_K against the false-positive rate on unknown data D_U [77]:

$$
\mathrm{CCR}(\tau) = \frac{\left|\{x \in \mathcal{D}_K : \arg\max_k g_k(x) = y,\ S(x) \ge \tau\}\right|}{|\mathcal{D}_K|}, \qquad \mathrm{FPR}(\tau) = \frac{\left|\{x \in \mathcal{D}_U : S(x) \ge \tau\}\right|}{|\mathcal{D}_U|}, \qquad \mathrm{OSCR} = \int_0^1 \mathrm{CCR}\; d\,\mathrm{FPR}
$$

Because CCR counts only correctly classified known samples, OSCR falls when either closed-set accuracy or rejection degrades, which is why it complements AUROC.

These methods have spread widely through RF recognition. Open-set automatic modulation classification has been addressed with LSTM models and extreme-value calibration [78], reconstruction-based rejection [79], few-shot formulations [80] and studies of adversarial robustness [81]. Open-set RF fingerprinting uses prototype learning [82], and pairing a deep model with an expert-feature classifier improves open-set wireless signal classification [83]. Jamming recognition has followed: convolutional prototype learning rejects unknown classes among nine simulated jamming types [84], OpenMax and extreme-value methods handle unknown radar jamming [85], [86], and domain-specific networks and prototype methods continue the line [87], [88]. In GNSS, few-shot learning for new interference classes [34] and uncertainty-based reliability [32] pursue related goals.

The open-set examples cited here do not establish the combined loaded-transponder monitoring task proposed in this review. The satellite interference models of Section 3 are either anomaly detectors, which flag deviations but cannot name known causes, or closed-set classifiers, which name causes but cannot reject unknown ones. Agon's out-of-distribution tests [24] address covariate shift — the same task on different constellations and datasets — rather than unknown interference classes. The observation that OSR has been neglected in deep-learning interference work [47] holds for the GEO case in particular.

The OSR literature also warns of evaluation pitfalls that shape our protocol. How hard the unknowns are depends on how close they lie to the known classes, so results must be reported per unknown class rather than pooled [69], [76]. In our class set, wideband noise is spectrally close to overdrive intermodulation regrowth, and intermittent bursts resemble pulsed interference. AUROC alone hides the operating point, so OSCR [77] and the false-positive rate at 95% true-positive rate are reported alongside it. Thresholds and score parameters must never be tuned on the test unknowns. Define known-class acceptance as the positive outcome: FPR95 is then the fraction of unknowns accepted at a threshold giving 95% known acceptance. Report separately whether that threshold is selected on known validation data (an operational estimate) or swept on the test set (a descriptive benchmark). Unknown families used for development must be disjoint from final unknown families; semantic novelty and known-class covariate shift must be tested separately.

Compound events raise a separate problem. Interference often co-occurs — a CW carrier during a cross-polar fade, for example — and a single-label classifier will either reject such a frame as unknown or assign it to one component. Prior work handles this with explicit two-interferer coexistence classes [25] or with multi-label open-set heads [86]. This project restricts each frame to one event, states that as a limitation, and treats a multi-label head as an extension.

## 7. Evaluation under distribution shift

A simulator-trained recognizer will meet operating conditions it was not trained on, and the RF literature shows that this matters. Over-the-air RadioML experiments found that models trained in simulation lose accuracy on real captures [39]. Fraunhofer's GNSS evaluations found that supervised models degrade under discrepancies between controlled and field recordings, and that unsupervised and domain-adaptation methods recover only part of the loss [35]. Embedding-based domain generalization [89] and synthetic-to-real tests of RF vision-language models [90] reach the same conclusion: without calibration or adaptation, performance drops on shifted data.

Satellite interference studies have only begun to measure this. The TMLCN detectors were tested across modulation orders, bandwidth overlaps and off-axis angles [23], and Agon reports cross-constellation and cross-dataset robustness [24]. The reviewed detection studies do not establish a controlled comparison jointly varying input back-off, transponder bandwidth and multicarrier loading while isolating training with versus without the nonlinear chain. That measurement is contribution C3. It follows the GNSS practice of splitting by condition rather than at random [35]: test sets hold out back-off values and loading levels unseen in training, so that reported numbers measure transfer to held-out conditions. Values held out inside the training range test interpolation; values outside it test extrapolation, and these must be reported separately. A 36 MHz ↔ 72 MHz transfer test checks bandwidth; estimating a trend across bandwidth would need at least three values.

We define the payload gap at a test condition ω as the difference in a metric 𝓜 between a model trained with the full transponder chain and one trained on linearly superposed signals, both evaluated on full-chain test data 𝒟_ω:

$$
\Delta_{\mathrm{payload}}(\omega) = \mathcal{M}\!\left(f_{\mathrm{full}};\, \mathcal{D}_\omega\right) - \mathcal{M}\!\left(f_{\mathrm{lin}};\, \mathcal{D}_\omega\right), \qquad G(\omega) = \mathcal{M}\!\left(f_{\mathrm{full}};\, \mathcal{D}_\omega\right)
$$

Because 𝒟_ω comes from the same simulator that trained f_full, Δ_payload measures what payload modelling buys inside the simulator, not in operation. Two checks address this. The generalization curve G(ω), plotted against |IBO_ω − IBO_train|, shows how far the full-chain model transfers; it is defined for f_full only, since f_lin has no training back-off. And Δ_payload is re-evaluated on data from an independent nonlinearity — a measured amplifier from OpenDPD [61] or a different TWTA model — to test whether the gap survives a change of amplifier. For higher-is-better metrics, the hypothesis is that G may decrease as conditions move away from the training support. The sign and trend of Δ_payload remain empirical questions; the gap can be positive, zero or negative. For error metrics, report an explicitly sign-adjusted improvement. When training spans multiple IBO values, use distance to that training set or range rather than to an undefined single IBO_train. Match architecture, training budget, class priors, waveform realizations and measurement conditions between f_full and f_lin, with the payload transformation as the intended difference.

Random splits of simulated RF data also invite leakage. If the same carrier-plan instance, payload random seed or normalization statistics appear in both training and test data, a model can score well by memorizing scenario-specific features. Split by scenario and recording before creating overlapping windows; keep plans, payload instances, parent captures and derived windows grouped. Use independent random streams across partitions, with deliberately shared condition values only where the protocol calls for them. Fit dataset-level normalization and feature transforms on training data only, then freeze them for validation and test [96]. Do not fit a separate scaler on each partition. A fixed per-frame transform is permissible if computable from a single deployment frame and its effect on absolute-power cues is documented. Report results over multiple training seeds with scenario-level uncertainty estimates; adjacent windows are not independent replicates.

The metrics follow from the operator's use. Detection probability at a fixed false-alarm rate, plotted against interference power (INR or ISNR), is the standard figure of merit in the detection literature [8], [9], [23]; this project plots it against C/I, where INR_dB = CNR_dB − (C/I)_dB for powers integrated over the same bandwidth at the same reference plane. This conversion is not valid across mismatched integration bandwidths or before/after-payload reference planes. Macro-F1 on known classes, AUROC and OSCR [77] on unknowns, and binned expected calibration error cover recognition and rejection. Parameter count, FLOPs and per-frame latency matter because monitoring systems sweep many carriers continuously — one vendor advertises up to 200 carriers per second [16] — and because compact models are known to suffice for interference tasks [28], [45]. Baselines include CA-CFAR [10], expert spectral and cyclostationary features with gradient boosting [11], [91], signal-cancellation energy detection [8], and a reconstruction detector of the TrID type [23].

For a detection statistic Λ and C known classes, the two headline metrics are

$$
P_{\mathrm{D}}(P_{\mathrm{FA}}) = \Pr\{\Lambda > \gamma \mid \mathcal{H}_1\}, \qquad \gamma : \Pr\{\Lambda > \gamma \mid \mathcal{H}_0\} = P_{\mathrm{FA}}
$$

$$
\mathrm{macro\text{-}F_1} = \frac{1}{C} \sum_{k=1}^{C} \frac{2\, \mathrm{Prec}_k\, \mathrm{Rec}_k}{\mathrm{Prec}_k + \mathrm{Rec}_k}
$$

Macro averaging weights every known class equally, so a model cannot score well by neglecting a hard class such as carrier-under-carrier. Known samples that the open-set stage rejects count as false negatives for recall; set F1 to zero for undefined classwise denominators and report class support. Report closed-set macro-F1 before rejection separately from macro-F1 after rejection. State whether clean is included in C and provide interference-only results as well.

Public data supports these checks without replacing operator recordings. SnT's on-board and NGSO-to-GSO datasets [92], [93] allow direct comparison with prior GEO work, though they are released for non-commercial research only and contain no payload effects. Fraunhofer's GNSS recordings [94], [95], released under Creative Commons licences (some of them non-commercial), supply real pulsed, chirp and bursty interferers for testing unknown-class rejection. TorchSig [40], [41] supports pre-training and waveform generation, and OpenDPD [61] supports amplifier-mismatch tests.

## 8. Positioning of this work

The literature contains the pieces of a payload-aware, open-set interference recognizer, but in separate fields that have not been combined. Satellite payload modeling is mature but serves compensation [53]–[56]. Satellite interference learning is active but uses linear, single-carrier, single-polarization signal models with binary or closed-set tasks [20]–[24]. Open-set recognition is mature and widely applied to RF signals, but not to satellite transponders [76], [84]. The table shows where the closest prior work stands on the properties this project targets.

| Work | Payload nonlinearity | IMUX/OMUX | Multicarrier IM | Dual polarization | Carrier plan | Detects unseen interferers | Classifies known, rejects unknown | Data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| On-board detection with cancellation [8], [9] | No | No | No | No | No | Yes (energy test) | No | Analytical / simulated |
| Autoencoder and LSTM detectors [18], [19] | Implicit (real data, uncontrolled) | Implicit | Implicit | No | No | Yes | No | Real Ku-band and operator spectra |
| Operator ML study [6] | Implicit (real data, uncontrolled) | Implicit | Implicit | No | No | Yes | No | Real data |
| On-board CNN [20] | No | No | No | No | Partial (subband grid) | No | No | Simulated |
| NGSO-to-GSO detectors [21]–[23] | No | No | No | No | No | Yes (reconstruction error) | No | Simulated, public |
| Agon [24] | Testbed only, not swept | No | No | No | No | Yes | No (covariate shift only) | Public, own simulation, testbed |
| Closed-set classifiers [25]–[27] | No | No | No | No | No | No | No | Mostly simulated AWGN; hardware chain in [26] |
| Open-set jamming recognition [84]–[87] | No | No | No | No | No | Yes | Yes | Simulated |
| GNSS interference ML [32]–[35] | No | No | No | No | No | Partial | Partial (novel classes) | Real and controlled |
| DVB-S2X reference channel [54] | Yes | Yes | Partial (two carriers per TWTA) | Aggregate C/I only | Partial | Not applicable | Not applicable | Reference model |
| Proposed project (design targets; not demonstrated results) | Planned | Planned | Planned | Planned | Planned | To evaluate | To evaluate | Simulation planned, with independent mismatch checks |

Table 2 collects the results the closest studies report. No two rows share a dataset, a task and a metric, so the numbers cannot be ranked against one another; they show what has been claimed and under which signal model.

**Table 2.** Results attributed to the closest prior work in the original draft. These are source-reported numbers, not reproduced measurements. Agon’s AUC/F1 entries were checked against its primary text in this revision; the remaining precise percentages require page/table-level verification before submission.

| Work | Task | Data | Signal model | Reported result |
| --- | --- | --- | --- | --- |
| Vázquez et al. [6] | Binary detection | Real data; ESA-funded, with Eutelsat | Real captures | 44% lower false-detection probability than the compared approaches |
| Pellaco et al. [19] | Detection by spectrum prediction | Real spectra from the Swedish Space Corporation | Real captures with artificially added interference | More reliable than a model-based baseline; no single figure given |
| Daoud et al. [20] | Subband localization, on-board CNN | Simulated | BPSK, linear superposition | Reduced-dimension FFT magnitude gives the best accuracy |
| Saifaldawla et al. [22] | Binary detection, convolutional autoencoders | Simulated NGSO→GSO | Linear superposition | About 11 percentage points higher detection probability (recall) than energy detection |
| Saifaldawla et al. [23] | Binary detection, VAE and transformer (TrID) | Public NGSO–GSO set | Linear superposition | Up to 31.23% higher detection accuracy than the compared autoencoders and energy detection |
| Yang et al. (Agon) [24] | Binary detection with a modulation-classification head, semi-supervised transformer | Public NGSO–GSO set; authors' NGSO–NGSO simulation; testbed | Linear superposition; testbed hardware | AUC 0.9327, F1 0.8351 (NGSO–GSO); AUC 0.9085, F1 0.9055 (NGSO–NGSO) |
| Chen et al. [84] | Open-set jamming recognition | Simulated, nine jamming types | Generic jamming in noise | Unknown-rejection plateau 0.9883 at openness 0.030; above 0.89 at 0.397 |
| Ouyang [87] | Open-set jamming recognition | Compound jamming dataset | Generic jamming | 98.22% closed-set accuracy |
| Liu et al. [88] (preprint) | Open-set radar jamming recognition | Simulated | Radar jamming | Unknown-jamming recognition above 90% at JSR 5 dB, SNR above 0 dB |
| Ott et al. [34], [94] | GNSS interference classification | Real highway recordings, 8 interference + 3 clean classes | Real captures | 97.66% accuracy (dataset baseline) |

Two patterns stand out. The satellite rows report detection, not recognition, and several simulated satellite rows use additive interference models; the real-data rows contain payload effects but cannot vary them. The open-set rows report rejection of unknown jamming, but none involves a satellite payload.

Against this background, the three candidate contributions can be stated precisely.

**C1 — a proposed payload-aware, open-source data generator.** The target is to combine what the reference channel models — multicarrier DVB-S2 loading, TWTA AM/AM–AM/PM over an IBO sweep, IMUX/OMUX filtering, phase noise [53], [54] — with what it omits: carrier-level cross-polar leakage on the uplink and downlink, downlink-entry interferers, carrier-plan metadata and a labelled interference catalogue. Following open dataset practice in GNSS [37], it should ship with fixed benchmark splits and randomized payload parameters.

**C2 — a plan-conditioned, dual-polarization open-set recognizer with an identifiability analysis.** Section 5 motivates dual-polarization observations for leakage tests, carrier-plan information for occupancy and intermodulation consistency, and cyclic features for some hidden-carrier regimes. Ablations will test their incremental value. A formal identifiability claim would additionally require defining equivalence classes of latent mechanisms under each observation operator and showing when their induced distributions differ. The present review proposes observability hypotheses and empirical confusion tests rather than such a proof.

**C3 — a quantified payload gap.** Sim-to-real losses behind real RF hardware have been measured for generic signal classifiers [39], and Agon reports cross-dataset results that include a testbed with amplifier distortion [24]. Within the reviewed set, we did not identify an interference-recognition study that isolates the contribution of the transponder chain to such losses, or that measures how performance falls with distance from the training back-off, bandwidth and loading. Reporting this as a curve rather than a single number would give operators and later studies a concrete measure of what simulation fidelity buys.

Three limits of the literature should be stated alongside these claims. Agon [24], the Eutelsat/CTTC operational work [6] and open-set jamming recognition [84] each overlap part of the problem, so the novelty lies in the joint treatment rather than in any single element. Most comparable GEO studies are simulation-based, and the real-data ones cannot vary the payload, so realism must be demonstrated through traceability to the DVB-S2X reference channel [54], measured amplifier data [61] and comparison with public datasets [92], [93]. And the interference statistics that motivate the work come from industry sources [1]–[3], [5], partly from 2005, not from peer-reviewed measurement. Finally, each frame is assumed to hold one interference event; compound events are left to a multi-label extension (Section 6).

## References

The original draft states that entries were checked against bibliographic services, but the referenced verification manifest was not supplied with this file. This revision does not certify all 95 entries. Selected primary sources and added reference [96] were inspected; exact performance claims elsewhere retain a verification requirement (Appendix A). Trade-press and vendor sources [1]–[3], [5], [14]–[17] are cited only for operator statistics and product capabilities and are not peer-reviewed.

- [1] J. Bates, "Satellite operators target interference problem," Via Satellite, 2005. [Link](https://www.satellitetoday.com/connectivity/2005/08/01/satellite-operators-target-interference-problem/)
- [2] M. Coleman, "Tackling satellite interference," Microwave Journal, 2012. [Link](https://www.microwavejournal.com/articles/18088-tackling-satellite-interference)
- [3] Kratos, "Complete VSAT interference mitigation," fact sheet. [Link](https://www.kratosspace.com/-/media/communications/pdf/fact-sheet---complete-vsat-interference-mitigation.pdf)
- [4] M. Á. Vázquez, P. Henarejos, A. I. Pérez-Neira, E. Grechi, A. Voight, J. C. Gil, I. Pappalardo, F. Di Credico, R. M. Lancellotti, "On the use of AI for satellite communications," IEEE ComSoc SSC Newsletter, 2019, arXiv:2007.10110. [Open access](https://arxiv.org/abs/2007.10110)
- [5] Kratos, "Kratos KnownSpace detects sustained Iran origin RF interference targeting GEO communications," press release, 2026. [Link](https://www.kratosspace.com/sdatracker/kratos-knownspace-detects-sustained-iran-origin-rf-interference-targeting-geo-communications)
- [6] M. Á. Vázquez, P. Henarejos, I. Pappalardo, E. Grechi, J. Fort, J. C. Gil, R. M. Lancellotti, "Machine learning for satellite communications operations," IEEE Commun. Mag., vol. 59, no. 2, pp. 22-27, 2021, doi: 10.1109/MCOM.001.2000367. [DOI](https://doi.org/10.1109/MCOM.001.2000367)
- [7] A. I. Pérez-Neira, M. Á. Vázquez, S. Maleki, M. R. B. Shankar, S. Chatzinotas, "Signal processing for high throughput satellite systems: Challenges in new interference-limited scenarios," arXiv:1802.03958, 2018. [Open access](https://arxiv.org/abs/1802.03958)
- [8] C. Politis, S. Maleki, C. Tsinos, S. Chatzinotas, B. Ottersten, "On-board the satellite interference detection with imperfect signal cancellation," Proc. IEEE SPAWC, pp. 1-5, 2016, doi: 10.1109/SPAWC.2016.7536813. [DOI](https://doi.org/10.1109/SPAWC.2016.7536813)
- [9] C. Politis, S. Maleki, C. Tsinos, S. Chatzinotas, B. Ottersten, "Weak interference detection with signal cancellation in satellite communications," Proc. IEEE ICASSP, pp. 6289-6293, 2017, doi: 10.1109/ICASSP.2017.7953366. [Link](https://orbilu.uni.lu/bitstream/10993/29259/1/icassp_final.pdf)
- [10] H. M. Finn, R. S. Johnson, "Adaptive detection mode with threshold control as a function of spatially sampled clutter-level estimates," RCA Review, vol. 29, no. 3, pp. 414-464, 1968.
- [11] W. A. Gardner, "Exploitation of spectral redundancy in cyclostationary signals," IEEE Signal Process. Mag., vol. 8, no. 2, pp. 14-36, 1991, doi: 10.1109/79.81007. [DOI](https://doi.org/10.1109/79.81007)
- [12] B. Kim, H. Yu, S. Noh, "Cognitive interference cancellation with digital channelizer for satellite communication," Sensors, vol. 20, no. 2, art. 355, 2020, doi: 10.3390/s20020355. [Link](https://www.mdpi.com/1424-8220/20/2/355)
- [13] ITU-R, "Carrier identification system for FSS occasional use earth station transmissions," Recommendation S.2062-0, 2014. [Link](https://www.itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.2062-0-201409-I!!PDF-E.pdf)
- [14] B. Potter, "Preventing adjacent satellite interference," Via Satellite, 2014. [Link](https://www.satellitetoday.com/technology/2014/03/26/preventing-adjacent-satellite-interference/)
- [15] Rohde & Schwarz, "R&S GSACSM communications system monitoring," product page. [Link](https://www.rohde-schwarz.com/us/products/aerospace-defense-security/secure-communications-options/rs-gsacsm-communications-system-monitoring_63493-636288.html)
- [16] Integrasys, "VectorSat interference detection," product page. [Link](https://www.integrasys-space.com/interference-detection)
- [17] Calian, "Decimator carrier-under-carrier detection," product page. [Link](https://www.calian.com/advanced-technologies/space-satcom/decimator-carrier-under-carrier-detection/)
- [18] P. Henarejos, M. Á. Vázquez, A. I. Pérez-Neira, "Deep learning for experimental hybrid terrestrial and satellite interference management," Proc. IEEE SPAWC, pp. 1-5, 2019, doi: 10.1109/SPAWC.2019.8815532, arXiv:1906.03012. [Open access](https://arxiv.org/abs/1906.03012)
- [19] L. Pellaco, N. Singh, J. Jaldén, "Spectrum prediction and interference detection for satellite communications," Proc. ICSSC, 2019, arXiv:1912.04716. [Open access](https://arxiv.org/abs/1912.04716)
- [20] S. Daoud, G. Eappen, F. Ortiz, E. Lagunas, W. Martins, S. Chatzinotas, "CNN-based on-board interference detection in satellite systems: An analysis of dataset impact on performance," Proc. IEEE ICASSP Workshops (ICASSPW), pp. 1-5, 2023, doi: 10.1109/ICASSPW59220.2023.10193395. [Link](https://orbilu.uni.lu/bitstream/10993/55407/1/ICASSP_2023_Saed.pdf)
- [21] A. Saifaldawla, F. Ortiz, E. Lagunas, S. Daoud, S. Chatzinotas, "NGSO-to-GSO satellite interference detection based on autoencoder," Proc. IEEE PIMRC, pp. 1-7, 2023, doi: 10.1109/PIMRC56721.2023.10293839. [Link](https://www.semanticscholar.org/paper/2e58ac0017ce6245ed8328d3e892e0fe7c7360a4)
- [22] A. Saifaldawla, F. Ortiz, E. Lagunas, S. Chatzinotas, "Convolutional autoencoders for non-geostationary satellite interference detection," Proc. IEEE ICC Workshops, pp. 1334-1339, 2024, doi: 10.1109/ICCWorkshops59551.2024.10615457. [Link](https://orbilu.uni.lu/bitstream/10993/60597/1/Moatssim__ICC__Final.pdf)
- [23] A. Saifaldawla, F. Ortiz, E. Lagunas, A. B. M. Adam, S. Chatzinotas, "GenAI-based models for NGSO satellites interference detection," IEEE Trans. Mach. Learn. Commun. Netw., vol. 2, pp. 904-924, 2024, doi: 10.1109/TMLCN.2024.3418933. [DOI](https://doi.org/10.1109/TMLCN.2024.3418933)
- [24] B. Yang, C. Yang, Z. Chen, K. Qiu, Y. Gao, "Agon: A semi-supervised framework for robust satellite interference detection," arXiv:2606.14147 (preprint), 2026. [Open access](https://arxiv.org/abs/2606.14147)
- [25] H. Yu, R. Zhang, R. Ding, "Interference recognition based on machine learning for satellite communications," Proc. Int. Conf. Machine Learning Technologies (ICMLT), pp. 18-23, 2018, doi: 10.1145/3231884.3231901. [DOI](https://doi.org/10.1145/3231884.3231901)
- [26] X. Han, "Artificial intelligence-based interference signal recognition for satellite communications," Proc. ACSAT, pp. 279-282, 2024, doi: 10.1109/ACSAT63853.2024.10823708. [Link](https://ieeexplore.ieee.org/document/10823708/)
- [27] H. Xiong, "Research on interference detection and identification algorithms for satellite communication systems," Proc. ICECAI, pp. 84-87, 2025, doi: 10.1109/ICECAI66283.2025.11170987. [Link](https://www.semanticscholar.org/paper/08c7cf481ab890ff1f6f8c45353fa4c4bc9406bc)
- [28] F. Ortiz, V. Monzon Baeza, L. M. Garces-Socarras, J. A. Vásquez-Peralvo, J. L. Gonzalez et al., "Onboard processing in satellite communications using AI accelerators," Aerospace, vol. 10, no. 2, art. 101, 2023, doi: 10.3390/aerospace10020101. [Link](https://www.mdpi.com/2226-4310/10/2/101)
- [29] F. Fourati, M.-S. Alouini, "Artificial intelligence for satellite communication: A review," arXiv:2101.10899, 2021. [Open access](https://arxiv.org/abs/2101.10899)
- [30] G. Fontanesi, F. Ortíz, E. Lagunas et al., "Artificial intelligence for satellite communication: A survey," preprint, Univ. Luxembourg ORBilu. [Link](https://orbilu.uni.lu/bitstream/10993/65397/1/Artificial_Intelligence_for_Satellite_Communication_A_Survey.pdf)
- [31] A. Bhattacharyya, S. M. Nambiar, R. Ojha, A. Gyaneshwar, U. Chadha, K. Srinivasan, "Machine learning and deep learning powered satellite communications: Enabling technologies, applications, open challenges, and future research directions," Int. J. Satell. Commun. Netw., vol. 41, no. 6, pp. 539-588, 2023, doi: 10.1002/sat.1482. [DOI](https://doi.org/10.1002/sat.1482)
- [32] T. Brieger, N. L. Raichur, D. Jdidi, F. Ott, T. Feigl, J. R. van der Merwe et al., "Multimodal learning for reliable interference classification in GNSS signals," Proc. ION GNSS+, pp. 3210-3234, 2022, doi: 10.33012/2022.18586. [Link](https://www.researchgate.net/publication/364056875)
- [33] J. R. van der Merwe et al., "Low-cost COTS GNSS interference monitoring, detection, and classification system," Sensors, vol. 23, no. 7, art. 3452, 2023, doi: 10.3390/s23073452. [DOI](https://doi.org/10.3390/s23073452)
- [34] F. Ott, L. Heublein, N. L. Raichur, T. Feigl, J. Hansen, A. Rügamer, C. Mutschler, "Few-shot learning with uncertainty-based quadruplet selection for interference classification in GNSS data," Proc. ICL-GNSS, pp. 1-7, 2024, doi: 10.1109/ICL-GNSS60721.2024.10578525. [DOI](https://doi.org/10.1109/ICL-GNSS60721.2024.10578525)
- [35] L. Heublein, N. L. Raichur, T. Feigl, T. Brieger, F. Heuer et al., "Evaluation of (un-)supervised machine learning methods for GNSS interference classification with real-world data discrepancies," Proc. ION GNSS+, 2024, arXiv:2503.23775. [Open access](https://arxiv.org/abs/2503.23775)
- [36] L. Heublein et al., "VAE-based feature disentanglement for data augmentation and compression in generalized GNSS interference classification," arXiv:2504.10556, 2025. [Open access](https://arxiv.org/abs/2504.10556)
- [37] C. Wielenberg, L. Heublein, J. Ott et al., "The S-ICDF dataset: Sionna-simulated dynamic interference characterization and direction finding," arXiv:2607.03411, 2026. [Open access](https://arxiv.org/abs/2607.03411)
- [38] I. Ebrahimi Mehr, F. Dovis, "A deep neural network approach for classification of GNSS interference and jamming," IEEE Trans. Aerosp. Electron. Syst., vol. 61, no. 2, pp. 1660-1676, 2025, doi: 10.1109/TAES.2024.3462662. [Link](https://www.researchgate.net/publication/384100236)
- [39] T. J. O'Shea, T. Roy, T. C. Clancy, "Over-the-air deep learning based radio signal classification," IEEE J. Sel. Topics Signal Process., vol. 12, no. 1, pp. 168-179, 2018, doi: 10.1109/JSTSP.2018.2797022, arXiv:1712.04578. [Open access](https://arxiv.org/abs/1712.04578)
- [40] L. Boegner, M. Gulati, G. Vanhoy, P. Vallance, B. Comar, S. Kokalj-Filipovic, C. Lennon, R. D. Miller, "Large scale radio frequency signal classification," arXiv:2207.09918, 2022. [Open access](https://arxiv.org/abs/2207.09918)
- [41] L. Boegner et al., "Large scale radio frequency wideband signal detection & recognition," arXiv:2211.10335, 2022. [Open access](https://arxiv.org/abs/2211.10335)
- [42] M. Kulin, T. Kazaz, I. Moerman, E. De Poorter, "End-to-end learning from spectrum data: A deep learning approach for wireless signal identification in spectrum monitoring applications," IEEE Access, vol. 6, pp. 18484-18501, 2018, doi: 10.1109/ACCESS.2018.2818794, arXiv:1712.03987. [Open access](https://arxiv.org/abs/1712.03987)
- [43] K. Tekbıyık, Ö. Akbunar, A. R. Ekti, A. Görçin, G. K. Kurt, "Spectrum sensing and signal identification with deep learning based on spectral correlation function," arXiv:2003.08359, 2020. [Open access](https://arxiv.org/abs/2003.08359)
- [44] R. Wu, C. J. Li, W. Zhang, X. Liu, P. H. W. Leong, "Cyclo-AMC: Automatic modulation classification on Versal utilising cyclostationary features," Proc. FPT, 2025. [Link](http://phwl.org/assets/papers/cycloamc_fpt25.pdf)
- [45] T. Oyedare, V. K. Shah, D. J. Jakubisin, J. H. Reed, "Keep it simple: CNN model complexity studies for interference classification tasks," arXiv:2303.03326, 2023. [Open access](https://arxiv.org/abs/2303.03326)
- [46] C. Xu, J. Ren, W. Yu, Y. Jin, Z. Cao, X. Wu, W. Jiang, "Time-frequency analysis based deep interference classification for frequency hopping system," arXiv:2108.10056, 2021. [Open access](https://arxiv.org/abs/2108.10056)
- [47] T. Oyedare, V. K. Shah, D. J. Jakubisin, J. H. Reed, "Interference suppression using deep learning: Current approaches and open challenges," arXiv:2112.08988, 2021. [Open access](https://arxiv.org/abs/2112.08988)
- [48] K. He, X. Zhang, S. Ren, J. Sun, "Deep residual learning for image recognition," Proc. CVPR, 2016, arXiv:1512.03385. [Open access](https://arxiv.org/abs/1512.03385)
- [49] Y. Gong, Y.-A. Chung, J. Glass, "AST: Audio spectrogram transformer," Proc. Interspeech, 2021, arXiv:2104.01778. [Open access](https://arxiv.org/abs/2104.01778)
- [50] E. Perez, F. Strub, H. de Vries, V. Dumoulin, A. Courville, "FiLM: Visual reasoning with a general conditioning layer," Proc. AAAI, 2018, arXiv:1709.07871. [Open access](https://arxiv.org/abs/1709.07871)
- [51] A. A. M. Saleh, "Frequency-independent and frequency-dependent nonlinear models of TWT amplifiers," IEEE Trans. Commun., vol. 29, no. 11, pp. 1715-1720, 1981, doi: 10.1109/TCOM.1981.1094911. [DOI](https://doi.org/10.1109/TCOM.1981.1094911)
- [52] A. Morello, V. Mignone, "DVB-S2: The second generation standard for satellite broad-band services," Proc. IEEE, vol. 94, no. 1, pp. 210-227, 2006, doi: 10.1109/JPROC.2005.861013. [DOI](https://doi.org/10.1109/JPROC.2005.861013)
- [53] E. Casini, R. De Gaudenzi, A. Ginesi, "DVB-S2 modem algorithms design and performance over typical satellite channels," Int. J. Satell. Commun. Netw., vol. 22, no. 3, pp. 281-318, 2004, doi: 10.1002/sat.791. [DOI](https://doi.org/10.1002/sat.791)
- [54] ETSI/DVB, "DVB-S2X implementation guidelines," TR 102 376-2 (DVB BlueBook A171-2), 2020. [Link](https://dvb.org/wp-content/uploads/2020/02/A171-2_DVB-S2X_Implementation-Guidelines_Draft-TR-102-376-2_v121_Apr-2020.pdf)
- [55] B. F. Beidas, "Intermodulation distortion in multicarrier satellite systems: Analysis and turbo Volterra equalization," IEEE Trans. Commun., vol. 59, no. 6, pp. 1580-1590, 2011, doi: 10.1109/TCOMM.2011.042111.100320. [Link](https://www.researchgate.net/publication/224232286)
- [56] M. Allegue-Martínez et al., "Digital linear pre-compensation technique to enhance predistortion performance in multicarrier DVB-S2 satellite communication systems," Electron. Lett., vol. 50, no. 13, pp. 957-959, 2014, doi: 10.1049/el.2014.1172. [DOI](https://doi.org/10.1049/el.2014.1172)
- [57] A. A. Gözütok, M. M. Nefes, S. Demirel, "NPR and intermodulation distortion modelling of travelling-wave tube amplifier of telecommunication spacecraft," Proc. 11th Ankara Int. Aerospace Conf. (AIAC-2021-015), 2021. [Link](https://www.researchgate.net/publication/349494998)
- [58] J. C. Fuenzalida, O. Shimbo, W. L. Cook, "Time-domain analysis of intermodulation effects caused by nonlinear amplifiers," COMSAT Tech. Rev., vol. 3, no. 1, pp. 89-143, 1973.
- [59] Y. Luo, A. Jayaprakash, G. Chen, C. Huang, Q. Luo, P. Xiao, "Widely linear augmented extreme learning machine based impairments compensation for satellite communications," arXiv:2506.14557, 2025. [Open access](https://arxiv.org/abs/2506.14557)
- [60] X. Sun et al., "Kernel-FastICA-based nonlinear blind source separation for anti-jamming satellite communications," Sensors, vol. 25, no. 12, art. 3743, 2025, doi: 10.3390/s25123743. [Link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12197282/)
- [61] Y. Wu, G. D. Singh, M. Beikmirza, L. C. N. de Vreede, M. Alavi, C. Gao, "OpenDPD: An open-source end-to-end learning & benchmarking framework for wideband power amplifier modeling and digital pre-distortion," Proc. IEEE ISCAS, 2024, arXiv:2401.08318. [Open access](https://arxiv.org/abs/2401.08318)
- [62] Y. Wu, A. Li, C. Gao, "OpenDPDv2: A unified learning and optimization framework for neural network digital predistortion," arXiv:2507.06849, 2025. [Open access](https://arxiv.org/abs/2507.06849)
- [63] S. Hanna, D. Čabrić, "Deep learning based transmitter identification using power amplifier nonlinearity," arXiv:1811.04521, 2018. [Open access](https://arxiv.org/abs/1811.04521)
- [64] A. S. Karasuwa, J. D. Eastment, I. E. Otung, "Cross-polarisation discrimination-induced interference in dual-polarised high-capacity satellite communication systems," J. Eng., vol. 2016, no. 6, pp. 162-170, 2016, doi: 10.1049/joe.2015.0178. [Link](https://www.researchgate.net/publication/303477998)
- [65] E. Satorius, T. Jedrey, C. Wang, "Impact of cross-polarization interference on dual polarization communication systems," IPN Progress Report 42-213, JPL, 2018. [Link](https://ipnpr.jpl.nasa.gov/progress_report/42-213/42-213A.pdf)
- [66] P. Mo, X. Fan, L. You, "A novel and blind detection scheme for asymmetric PCMA system," Proc. ICCSNT, pp. 854-857, 2013, doi: 10.1109/ICCSNT.2013.6967240. [Link](https://ieeexplore.ieee.org/document/6967240/)
- [67] X. Liu, X. Tao, X. Chen, N. Ge, "Information theory analysis of blind detection for PCMA satellite communication systems," Proc. IEEE VTC-Fall, pp. 1-5, 2013, doi: 10.1109/VTCFall.2013.6692242. [Link](https://www.researchgate.net/publication/261383218)
- [68] C. Geng, S.-J. Huang, S. Chen, "Recent advances in open set recognition: A survey," IEEE Trans. Pattern Anal. Mach. Intell., vol. 43, no. 10, pp. 3614-3631, 2021, doi: 10.1109/TPAMI.2020.2981604, arXiv:1811.08581. [Open access](https://arxiv.org/abs/1811.08581)
- [69] J. Yang, K. Zhou, Y. Li, Z. Liu, "Generalized out-of-distribution detection: A survey," Int. J. Comput. Vis., vol. 132, no. 12, pp. 5635-5662, 2024, doi: 10.1007/s11263-024-02117-4, arXiv:2110.11334. [Open access](https://arxiv.org/abs/2110.11334)
- [70] D. Hendrycks, K. Gimpel, "A baseline for detecting misclassified and out-of-distribution examples in neural networks," Proc. ICLR, 2017, arXiv:1610.02136. [Open access](https://arxiv.org/abs/1610.02136)
- [71] S. Liang, Y. Li, R. Srikant, "Enhancing the reliability of out-of-distribution image detection in neural networks," Proc. ICLR, 2018, arXiv:1706.02690. [Open access](https://arxiv.org/abs/1706.02690)
- [72] W. Liu, X. Wang, J. D. Owens, Y. Li, "Energy-based out-of-distribution detection," Proc. NeurIPS, 2020, arXiv:2010.03759. [Open access](https://arxiv.org/abs/2010.03759)
- [73] K. Lee, K. Lee, H. Lee, J. Shin, "A simple unified framework for detecting out-of-distribution samples and adversarial attacks," Proc. NeurIPS, 2018, arXiv:1807.03888. [Open access](https://arxiv.org/abs/1807.03888)
- [74] A. Bendale, T. Boult, "Towards open set deep networks," Proc. CVPR, 2016, arXiv:1511.06233. [Open access](https://arxiv.org/abs/1511.06233)
- [75] G. Chen, P. Peng, X. Wang, Y. Tian, "Adversarial reciprocal points learning for open set recognition," IEEE Trans. Pattern Anal. Mach. Intell., 2021, doi: 10.1109/TPAMI.2021.3106743, arXiv:2103.00953. [Open access](https://arxiv.org/abs/2103.00953)
- [76] S. Vaze, K. Han, A. Vedaldi, A. Zisserman, "Open-set recognition: A good closed-set classifier is all you need?," Proc. ICLR, 2022, arXiv:2110.06207. [Open access](https://arxiv.org/abs/2110.06207)
- [77] A. R. Dhamija, M. Günther, T. E. Boult, "Reducing network agnostophobia," Proc. NeurIPS, 2018, arXiv:1811.04110. [Open access](https://arxiv.org/abs/1811.04110)
- [78] Y. Guo, H. Jiang, J. Wu, J. Zhou, "Open set modulation recognition based on dual-channel LSTM model," arXiv:2002.12037, 2020. [Open access](https://arxiv.org/abs/2002.12037)
- [79] Z. Zhang, M. Zhu, J. Liu, Y. Li, S. Wang, "Class information guided reconstruction for automatic modulation open-set recognition," arXiv:2312.13023, 2023. [Open access](https://arxiv.org/abs/2312.13023)
- [80] H. Zhang, F. Zhou, Q. Wu, C. Yuen, "FSOS-AMC: Few-shot open-set learning for automatic modulation classification," arXiv:2410.10265, 2024. [Open access](https://arxiv.org/abs/2410.10265)
- [81] Y. Yang, S. Zhang, K. Li, Q. Tian, Y. Lin, "Adversarial threats to automatic modulation open set recognition in wireless networks," arXiv:2405.05022, 2024. [Open access](https://arxiv.org/abs/2405.05022)
- [82] W. Wang, H. Liao, L. Gan, "Open-set RF fingerprinting via improved prototype learning," arXiv:2306.13895, 2023. [Open access](https://arxiv.org/abs/2306.13895)
- [83] S. R. Shebert, B. H. Kirk, R. M. Buehrer, "Open set wireless signal classification: Augmenting deep learning with expert feature classifiers," arXiv:2302.03749, 2023. [Open access](https://arxiv.org/abs/2302.03749)
- [84] X. Chen, Z. Zhao, X. Ye, S. Zheng, C. Lou, X. Yang, "Efficient open-set recognition for interference signals based on convolutional prototype learning," Appl. Sci., vol. 12, no. 9, art. 4380, 2022, doi: 10.3390/app12094380. [DOI](https://doi.org/10.3390/app12094380)
- [85] Y. Zhou, S. Shang, X. Song, S. Zhang, T. You et al., "Intelligent radar jamming recognition in open set environment based on deep learning networks," Remote Sens., vol. 14, no. 24, art. 6220, 2022, doi: 10.3390/rs14246220. [DOI](https://doi.org/10.3390/rs14246220)
- [86] Y. Xiao, R. Zhang, X. Yu, Y. Jiang, "Open-set recognition of compound jamming signal based on multi-task multi-label learning," IET Radar Sonar Navig., vol. 18, no. 8, pp. 1235-1246, 2024, doi: 10.1049/rsn2.12561. [DOI](https://doi.org/10.1049/rsn2.12561)
- [87] M. Ouyang, "An open-set jamming signal recognition method based on domain-specific network," IET Commun., vol. 20, no. 1, 2026, doi: 10.1049/cmu2.70198. [DOI](https://doi.org/10.1049/cmu2.70198)
- [88] Y. Liu, S. Han, Z. Lin, C. Guo, Q. Zhao, W. Chen, T. Qiu, "An open-set recognition method for active radar jamming signals based on multi-dimensional prototype feature constraints and adversarial reciprocal point learning," Preprints.org (not peer-reviewed), 2025, doi: 10.20944/preprints202503.2079.v1. [Link](https://www.preprints.org/manuscript/202503.2079)
- [89] L. Henneke, F. Kurth, "Approaching domain generalization with embeddings for robust discrimination and recognition of RF communication signals," arXiv:2510.23186, 2025. [Open access](https://arxiv.org/abs/2510.23186)
- [90] A. Bara, L. Bariah, H. Zou, B. Mefgouda, M. Debbah, "RF-Analyzer: Can vision-language models learn RF understanding from synthetic data?," arXiv:2605.04676, 2026. [Open access](https://arxiv.org/abs/2605.04676)
- [91] T. Chen, C. Guestrin, "XGBoost: A scalable tree boosting system," Proc. ACM KDD, 2016, arXiv:1603.02754. [Open access](https://arxiv.org/abs/1603.02754)
- [92] SnT SmartSpace, "Satellite on-board interference detection dataset," dataset (non-commercial research use). [Link](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/)
- [93] SnT SmartSpace, "NGSO to GSO's users interference dataset," dataset (non-commercial research use). [Link](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/)
- [94] F. Ott, L. Heublein, N. Raichur, T. Feigl, A. Rügamer, "GNSS interference spectrum highway dataset 1," IEEE DataPort, CC BY-NC-SA 4.0, 2024, doi: 10.21227/xpm9-tt28. [Link](https://ieee-dataport.org/documents/gnss-interference-spectrum-highway-dataset-1)
- [95] Fraunhofer IIS, "Highway 2, LC Laboratory and Jammertest 2025 GNSS interference datasets," Zenodo, licence per record. [Highway 2](https://zenodo.org/records/21336653) · [LC Laboratory](https://zenodo.org/records/21333335) · [Jammertest 2025](https://zenodo.org/records/21332689)

- [96] scikit-learn developers, “Common pitfalls and recommended practices,” documentation, Section 12.2, accessed 23 October 2026. [Official documentation](https://scikit-learn.org/stable/common_pitfalls.html).

## Appendix A. Teknik düzeltme kaydı ve doğrulama sınırları

Bu ek 23 Ekim 2026 tarihli editoryal incelemeyi kaydeder. Ana metnin İngilizcesi korunmuştur. Bu dosya depo durumunu veya tamamlanmış deneyleri doğrulamaz.

| Öncelik | Konu | Uygulanan düzeltme |
| --- | --- | --- |
| Kritik | Veri sızıntısı | Bölüm başına ayrı normalizasyon kaldırıldı; eğitimde öğrenilen dönüşümün dondurulması ve senaryo/kayıt düzeyinde ayırma eklendi. |
| Kritik | C/I ve güç birimleri | Lineer oran ile dB ayrıldı; yaklaşık 0.043 dB hesabı aynı spektral şekil varsayımıyla sınırlandı; normalize güç referansı açıklandı. |
| Kritik | Kanıtsız sonuçlar | Eksik Şekil 2–3 varlıklarına bağlı sayısal simülasyon sonuçları çıkarıldı; önerilen katkılar tamamlanmış sonuçlardan ayrıldı. |
| Yüksek | Genelleme yönü | G için beklenen düşüş belirtildi; payload gap işareti ve monotonluğu deney sorusu olarak bırakıldı. |
| Yüksek | Gözlenebilirlik | Özelliklerin zorunlu/yeterli olduğu savı yumuşatıldı; aynı spektrumu üretebilen farklı nedenler açıklandı. |
| Yüksek | SCF | İdeal RRC bağımsız sembol modeli ile gerçek DVB yapısı ayrıldı; evrensel gözlem uzunluğu ölçeklemesi kaldırıldı. |
| Yüksek | Açık küme | OpenMax sınıflandırması düzeltildi; negatif enerji işareti ve FPR95 pozitif sınıfı açıklandı. |
| Yüksek | Özgünlük | İncelenen kaynaklarla sınırlı araştırma boşluğu kullanıldı; literatürün tamamına ilişkin kesin yokluk iddiası kaldırıldı. |
| Orta | Sunum | Kaçış karakterleri temizlendi, denklemler görüntülenebilir matematik bloklarına çevrildi, eksik şekil yer tutucuları kaldırıldı. |

### Bu revizyonda yapılan kaynak kontrolleri

- [24] Agon: birincil tam metinde Tablo III üzerinden kamu NGSO–GSO verisi için AUC 0.9327 / F1 0.8351 ve NGSO–NGSO için AUC 0.9085 / F1 0.9055 kontrol edildi. Bu sonuçlar bağımsız tekrar değildir. [Tam metin](https://arxiv.org/html/2606.14147).
- [37] S-ICDF: arXiv kaydında başlık, yazarlar, 3 Temmuz 2026 gönderim tarihi ve simülasyon veri seti kapsamı kontrol edildi. GEO transponder veri seti olduğu sonucuna varılmadı.
- [61] OpenDPD: birincil özetindeki ölçülmüş dijital güç yükselteci veri seti ve çerçeve kapsamı kontrol edildi; GEO TWTA doğrulaması olarak kullanılmaması korundu.
- [72] Energy-based OOD: birincil tam metindeki E = −T logsumexp ve kabul için −E kullanımı kontrol edildi.
- [74] OpenMax: birincil metindeki aktivasyon tabanlı kalibrasyon yaklaşımı kontrol edildi.
- [76] İyi kapalı küme sınıflandırıcısı: birincil özette güçlü maximum-logit taban çizgisi ve semantik yenilik ayrımı kontrol edildi.
- [96] Normalizasyon: resmi dokümantasyonda yalnız eğitim verisinde fit, diğer bölümlerde aynı dönüşümü uygulama ilkesi kontrol edildi.

### Gönderimden önce açık kalan işler

1. Tekrarlanabilir tarama kaydı ekleyin: kullanılan veri tabanları, tam sorgular, son arama tarihi, dahil etme/dışlama ölçütleri ve seçim akışı. Mevcut çalışma anlatısal taramadır; sistematik derleme olarak sunulmamalıdır.
2. 95 kaynak için DOI/başlık/yıl ve iddia–sayfa/tablo eşleştirme çizelgesi oluşturun. Özellikle [6], [22], [23], [84], [87], [88], [94] yüzdelerinin koşullarını; [54] standart sürümünü ve [92]–[95] lisanslarını doğrudan kayıtlardan doğrulayın. Erişilemeyen kaynakları doğrulanmış saymayın.
3. Şekilleri kod, parametreler, tohumlar, filtre ve PSD ayarlarıyla yeniden üretin. Eski 1–16 dB eğim ve 9 dB back-off sonuçlarını kayıt olmadan geri eklemeyin.
4. Bilinen/bilinmeyen sınıfları, clean tanımını, C/I ölçüm düzlemini, yanlış alarm birimini ve eşik seçim protokolünü deney başlamadan sabitleyin. Plan metadatası test etiketinden türetilmemeli; gerçek operatörün erişebileceği bilgiyle sınırlanmalıdır.
5. Taşıyıcı planı hatası/eksikliği, kutuplar arası senkronizasyon hatası ve düşük karşı-kutup SNR koşullarında sağlamlığı ölçün. Ayırt edilemeyen kaynak nedenleri için birleşik etiket veya belirsiz sonuç değerlendirin.
6. Pilot, kontrollü simülasyon, bağımsız yükselteç uyumsuzluğu ve gerçek operatör verisi sonuçlarını ayrı raporlayın. Ölçülmüş farklı bir PA ile test, operasyonel GEO doğrulaması sağlamaz.
