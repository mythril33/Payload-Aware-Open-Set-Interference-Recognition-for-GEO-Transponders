# RF and mathematics validation — V4.3 literature review

Date: 26 October 2026. Scope: static review of physics, reference planes, equations and open-set metric definitions in `GEO_Payload_Aware_Interference_Literature_Review_V4_3_FINAL.docx` (source `literature_review_v4_3.md`). No simulation, data generation, training or evaluation was run. Numerical checks below are closed-form arithmetic only.

## 1. Evidence levels used in this audit

- **Derivation (E1):** checked by hand or closed-form arithmetic in this audit.
- **Standards (E2):** ETSI documents could not be opened (network policy). Edition metadata and selected clause content were confirmed at search-excerpt level; full-text inspection reported by a previous revision (V4.1, 25 Oct 2026) is cited as inherited evidence and labelled as such.
- No statement in the manuscript relies on project simulation outputs.

## 2. RF reference planes

| Item | V4.2 baseline (uploaded researcher DOCX) | V4.3 | Status |
|---|---|---|---|
| Uplink composite | $y_u(t)$ in the equation, but called $x(t)$ in the text and notation table | $x_{\mathrm{co}}(t)$ per polarization, Eq. (1); the notation and the equation agree | resolved |
| Cross-polar coupling | Single symmetric $\kappa$ matrix applied **after** the transponder outputs (downlink only) | Separate complex $\kappa_u$ (common uplink), $\kappa_{u,q}$ (station-specific), $\kappa_d$ (downlink) and $\kappa_R$ (monitoring feed, EP-R), Eqs. (2) and (4); reverse coefficients specified separately; non-reciprocity noted | resolved |
| Downlink-entry interferers | Absent | $i_{d,l}(t)$ enters after the OMUX and bypasses the payload, Eq. (4); EP-D | resolved |
| Satellite LO phase noise | Absent from the equations | $\phi_{\mathrm{LO,co}}(t)$, the receiver down-converter phase noise per polarization receiver, applied before the IMUX (EP-P), Eq. (2) | resolved |
| Monitoring receiver | Only additive $n_d$ | Receiver operator $\mathcal{R}\{\cdot\}$ plus noise (EP-R): gain, flatness, LO offset, quantization; co/cross synchronization in Figure 2 | resolved |
| Adjacent-satellite interference | Treated as one mechanism, implicitly on the downlink | Split into uplink-entry ASI (EP-U1, traverses the payload) and downlink-entry ASI (EP-D, bypasses it), Tables 1–3 | resolved |
| Overdrive | Treated as a class without a cause/manifestation distinction | Cause at EP-U0/EP-U1 or an operational gain setting; manifestation at EP-P (Table 1) | resolved |
| Figure 1 (old) | Showed "four views", with no planes | New Figure 2 is drawn directly from Eqs. (1)–(4), shows planes EP-U0 to EP-R, the receiver/down-converter inside EP-P, PIM and receiver nonlinearity, and states its conceptual status | resolved |
| Payload-internal sources | Only TWTA IM/overdrive | Adds wideband-receiver nonlinearity and passive intermodulation (EP-P) as E1 physical inferences | qualified (primary sources not searched) |

**Physical consistency check of Figure 2 against the equations.**
- Uplink interferers enter before the satellite front end and IMUX (Eq. 1).
- $\kappa_u$ couples the two uplink composites before each transponder (Eq. 2).
- Each polarization has its own IMUX–TWTA–OMUX chain (Eq. 3).
- $\kappa_d$ couples the transponder outputs after the OMUX (Eq. 4).
- Downlink-entry interferers and receiver impairments enter after the payload (Eq. 4).
- Side information is drawn as conditional (dashed).

Result: consistent.

## 3. Equation-by-equation audit (final numbering after the red-team revision)

| Eq. | Content | Check | Result |
|---|---|---|---|
| (1) | Uplink composite | $s_k$ unit power, $P_k$ power weight, so $\sqrt{P_k}$ is an amplitude; phase in rad; additive interferer and noise terms | correct |
| (2) | $u_{\mathrm{co}}=[x_{\mathrm{co}}+\kappa_u x_{\mathrm{x}}+\sum_q\kappa_{u,q}x_{\mathrm{x},q}]e^{j\phi_{\mathrm{LO,co}}}$ | Common coupling (satellite receive antenna, propagation) is separated from station-specific misalignment leakage (red-team RT-04). Down-converter phase noise is defined per polarization receiver and applied before the IMUX (RT-13). Scalar couplings are flagged as a simplification. | correct (simplification stated) |
| (3) | $z=h_{\mathrm{OMUX}}*\mathcal{G}\{g_c(h_{\mathrm{IMUX}}*u)\}$ | Order IMUX → gain → amplifier → OMUX. The channel gain $g_c$ (fixed gain or ALC) is added because later arguments depend on gain mode (RT-30). | correct |
| (4) | $y=\mathcal{R}\{z_{\mathrm{co}}+\kappa_d z_{\mathrm{x}}+\sum i_d+n_d\}$ | $\kappa_d$ covers satellite transmit isolation and downlink depolarization. Monitor-feed leakage $\kappa_R$ sits inside $\mathcal{R}$ at EP-R (RT-14). | correct |
| (5) | Saleh AM/AM–AM/PM | Form matches the frequency-independent model. Derivative check gives $r_{\mathrm{sat}}=1/\sqrt{\beta_a}$ and $A_{\max}=\alpha_a/(2\sqrt{\beta_a})$. With the illustrative coefficients, $r_{\mathrm{sat}}=0.9318$, $A_{\max}=1.0058$ and $\Phi(r_{\mathrm{sat}})=0.390$ rad (22.4°). The wording about Saleh's I/Q and frequency-dependent models is corrected (RT-16). | correct; coefficient provenance (4.0033 vs 4.033) disclosed as unresolved |
| (6) | IBO, OBO | Positive dB back-off. Under multicarrier loading, $P_{\mathrm{in}}$ and $P_{\mathrm{out}}$ are total mean powers, with $P_{\mathrm{out}}$ including IM and amplified noise (RT-30). | correct |
| (7) | IM3 frequency set | $\{2f_i-f_j: i\ne j\}\cup\{f_i+f_j-f_k\}$ with $i,j,k$ pairwise distinct. The baseline's "i,j,k distinct" for $2f_i-f_j$ was ill-posed. | corrected |
| (8) | IM3 law; 2 dB/dB | Asymptotic cubic-regime result; the constant $c$ is defined. The near-saturation reduction and the AM/PM contribution are supported by classical analyses [N032; R058] (RT-17). | correct with stated validity |
| (9) | Distinguishability with a total-variation margin | $\inf_{\psi_1,\psi_2} d_{\mathrm{TV}}\ge1-2\epsilon$ is equivalent to a test with worst-case error $\le\epsilon$ for equal priors (Le Cam). It is the same notion as fault isolability (RT-01). | correct |
| (10) | CuC PSD | Valid for uncorrelated zero-mean signals. 0.0432 dB is checked. The text now separates effect size from identifiability: the periodogram dB standard deviation is about 4.34 dB per look, so $KM\approx10^4$ resolves 0.043 dB; the pair is non-identifiable under host-level nuisance (RT-03). | correct |
| (11) | SCF | The stochastic definition (now written with $T^{-1}$) is acceptable. RRC with $0<\beta_{\mathrm{rc}}<1$ gives $\alpha\in\{0,\pm1/T_s\}$. The record-length scaling $N\propto\rho_{\mathrm{eff}}^{-2}$ is stated only under a Gaussian-background model (RT-35). | correct (conditional) |
| (12) | Residual energy detector | Attribution: pilot cancellation [R008] and decoded-signal cancellation [R009], both on board. The added derivation: residual fraction $\approx\varepsilon^2+\vartheta^2$; 1° rms gives −35.2 dB and 0.1 dB gives −38.7 dB. | correct |
| (13) | CA-CFAR | $\gamma_i=\eta\frac{1}{N_r}\sum_{j\in\mathcal{W}_i}P_j$, with $\eta=N_r(P_{\mathrm{FA}}^{-1/N_r}-1)$. Check: $N_r=16$, $P_{\mathrm{FA}}=10^{-6}$ gives $\eta=21.94$. Single-look validity is stated. | corrected (baseline garbled) |
| (14) | Open-set decision rule | Accept if $Q\ge\tau$, where $Q$ is known-confidence | correct |
| (15) | MSP, energy, Mahalanobis | $Q_E=T_E\log\sum e^{g/T_E}=-E(x)$, which is larger for known inputs, consistent with [R072]. $Q_M$ is a single-embedding simplification of [R073]. $U=-Q$. | correct |
| (16) | CCR, UAR, OSCR | The unknown acceptance rate is renamed from "FPR" to avoid conflict with the unknown-positive FPR | corrected |
| (17) | Unknown-positive FPR@95TPR | $t_{95}$ is computed on $\mathcal{D}^{\mathrm{near}}_{\mathrm{unk}}$ (sample-pooled); FPR is computed over $\mathcal{D}_{\mathrm{kn}}$. It is described as a single operating point at a test-oracle threshold, not threshold-free, and as not comparable with ID-positive FPR95 (RT-15). | correct, matches the repository E12 D-4 wording |
| (18) | Macro-F1; $P_D(P_{\mathrm{FA}})$ | $L$ known classes | correct |
| (19) | Payload gap $\Delta^{(4)}$ | Four common classes, M-nl4 vs M-lin on identical eligible nonlinear test observations; M-nl5 is separate; simulator-internal | corrected |

**Editability.** Display and inline mathematics are native Office Math. There are 185 `m:oMath` objects and no equation images. The baseline DOCX had 3 OMML objects, and most of its equations were raw LaTeX text. Rendering was checked in the LibreOffice PDF proof, after installing the LibreOffice Math component in the container only. Cosmetic differences from Word (equation-number spacing, script-letter fonts) are possible.

## 4. Standards and primary-source cross-checks

| Item | What was confirmed in this audit | Level | Remaining dependency |
|---|---|---|---|
| ETSI TR 102 376-2 V1.2.1 (2021-01) vs DVB A171-2 (2020) | The official ETSI V1.2.1 PDF listing exists. A171-2 is the "Draft TR 102 376-2 v1.2.1" (Feb/Apr 2020). | search-excerpt metadata | none for edition identity |
| §4.4.1.3 cross-polar models | Three-term model: satellite-antenna XPI about 32 dB; terminal XPI 25 dB in simulations; depolarization XPD 38 dB (Ku linear) and 18 dB (Ka circular) at 99.9% availability. Aggregate C/I is about 24 dB (Ku) and 17 dB (Ka deep fade). The power sum of 32/25/38 dB gives 24.03 dB, and 32/25/18 dB gives 17.07 dB, which is consistent. | V1.1.1 text and V1.2.1 draft excerpts; full text inspected only in V4.1 (inherited) | Table number and V1.2.1 wording need full-text confirmation |
| §4.4.1.4 TWTA | Excerpts: conventional and linearized TWTA AM/AM and AM/PM characteristics for transponder bandwidths in Ku and Ka. The clause attribution comes from a search summary. | search excerpt | full-text confirmation |
| "Negligible" cross-polar statement | Only "negligible co-channel interference" for multi-carrier per TWTA with many colours (4.4.2.3.2) was seen. The earlier claim that "DVB-S2X assumes cross-polar negligible" is contradicted, and V4.3 does not make it. | search excerpt | — |
| EN 302 307-1 V1.4.1 Annex H | The official PDF listing exists. Annex H is titled "Examples of possible use of the System", and H.7 covers transponder models (IMUX, TWTA, OMUX; linearized and non-linearized TWTA). | search excerpt; informative status inherited from V4.1 | informative status and figure numbering need full-text confirmation |
| Saleh 1981 | Metadata and model form confirmed; the paper includes a frequency-dependent model | secondary (Semantic Scholar, software docs) | coefficient provenance |
| PCMA / CuC primary sources | R066 (secondary metadata), R067 (not found), N013 (repository record) | weak | Dankberg/ViaSat PCMA patent and Comtech carrier-in-carrier primary sources not searched (budget) |
| Cyclostationarity | R011 metadata (secondary). The RRC cycle-frequency result is derived in this audit. | E1 + secondary | primary Gardner 1986/1987 and Gardner–Napolitano–Paura 2006 not searched (budget) |
| CID level | The range is 17.5–27.5 dB below the host PSD depending on host symbol rate (ESA/Via Satellite excerpts; repository record of ETSI TS 103 129 Table 6). The fixed 27.5 dB statement was removed. | excerpt + repository | TS 103 129 full text |
| C/IM slope | ITU-R SM.1446 excerpt shows a relation linear in output back-off with coefficient 2 (≈1.64 per dB input under its BO mapping). The manuscript states only qualitatively that the slope can be lower than asymptotic. | excerpt | full text if numbers are ever quoted |

## 5. Open-set metric conventions (final)

- Known-confidence score $Q(x)$ (renamed from $S(x)$ to avoid a clash with the PSD $S_y(f)$); known classes $L$; test sets $\mathcal{D}_{\mathrm{kn}}$, $\mathcal{D}_{\mathrm{unk}}$, $\mathcal{D}^{\mathrm{near}}_{\mathrm{unk}}$.

- Unknown score: $U(x)=-Q(x)$, where larger means more unknown-like. This matches the repository convention.
- Primary analysis target in the separate programme (descriptive): near-family pooled unknown-positive FPR@95TPR. Unknown-family observations are the positives, TPR is computed over unknown observations and FPR over known test observations. Both denominators and group counts are reported.
- Operating thresholds (separate quantities):
  - known-class acceptance threshold at 95% on known-only calibration data;
  - clean-only alarm threshold at a 5% false-alarm target on clean calibration scenes;
  - both are frozen before test access.
- AUROC and OSCR are reported as distinct summaries. OSCR uses the unknown acceptance rate (UAR).
- The primary scorer is open and is not invented in the manuscript.

## 6. Operator observables vs simulator truth

The following are explicitly excluded from operator observables (Section 5.1): activity masks, realized IBO/OBO, XPD, C/I, event labels and parameters, and transmitted symbols. Oracle cancellation is labelled as an upper bound only. This is consistent with the repository's scientific invariants (`.claude/rules/scientific-invariants.md`) and with the P20 observation-based cancellation contract.

## 7. Residual risks

1. The ETSI clause contents are confirmed only at excerpt level in this audit.
2. Saleh coefficient provenance is unresolved.
3. Primary PCMA and cyclostationarity sources were not searched.
4. The identifiability classes are model-based and do not include estimator-specific bounds.
5. LibreOffice and Word rendering of OMML may differ cosmetically.
