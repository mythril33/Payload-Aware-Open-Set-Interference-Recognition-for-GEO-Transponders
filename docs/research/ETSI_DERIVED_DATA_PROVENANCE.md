# ETSI-derived numerical data: provenance record

Status: 2026-10-27. Repository revision `3a6bd910e61ed0fced4abeace929f73163ebe742` (merge of PR #54); working tree clean when checked. This is a documentation record. No source file, data file, checkpoint or Git history was changed, and nothing is committed.

Scope: the two derived files committed under `src/geosim/data/`. The raw ETSI documents and the extracted text tables are not in the repository.

Applicability: this is a data-derivation check, not a pipeline result under `docs/results/`. The revision, fingerprint, command, runtime, memory, size and regeneration items are recorded below. The `--reuse`, role and protocol checks of the reproducibility audit do not apply.

## 1. What is committed, and where it comes from

| File | Content | Derived from | Generator |
|---|---|---|---|
| `src/geosim/data/mux_fir.npz` (32,121 bytes) | Complex FIR taps of IMUX and OMUX, 1024 taps at 288 MHz (`imux_36`, `omux_36`, `imux_72`, `omux_72`); `fs`; `bulk_delay` = 256 samples | ETSI TR 102 376-2 V1.2.1, Annex E attachment: `36_MHz_IMUX.txt`, `36_MHz_OMUX.txt` | `scripts/build_mux_filters.py` |
| `src/geosim/data/dvbs2_twta.json` (3,360 bytes) | Digitized TWTA curves: `linearized_ku_twta_fig_h2` (EN 302 307-1 Figure H.2) and `nonlinearized_ka_twta_fig_h3` (Figure H.3) | ETSI EN 302 307-1 V1.4.1, Annex H.7, from the vector paths of the PDF | `scripts/digitize_twta_figures.py <en_30230701v010401p.pdf>` (PDF not in the repository) |

- The 26 MHz and 33 MHz tables in the attachment are not used.
- The 72 MHz taps have no table of their own. `build_mux_filters.py` applies the bandwidth-scaling rule of TR 102 376-2 §4.4.1.2 (also EN 302 307-1 H.7) to the 36 MHz table: R(f) = Rejection(f·36/BW) and G(f) = (36/BW)·GroupDelay(f·36/BW). In the code, k = 36 MHz/BW, and gain and group delay are interpolated at f·k. The attachment contains no 72 MHz table, so these taps are not checked numerically.

## 2. Fingerprints (SHA-256)

| Item | SHA-256 |
|---|---|
| `src/geosim/data/mux_fir.npz` (committed) | `58b78bdaf6b749f9f45e8c1f0541674ad0d81f9bd6f17762e667965cd8ba11e8` |
| `src/geosim/data/dvbs2_twta.json` (committed) | `0da3a624f9e94058ed100d6c06b62aff08f49f3a5a93df3ddc23f4b3f082c4f1` |
| `tr_10237602v010201p0.zip` (Annex E attachment, as uploaded) | `e4e1936a5e03bed7161387ee609b394567965a4783dfc936e36564bba2925f14` |
| `36_MHz_IMUX.txt` (extracted from the zip) | `9c65565dcd1f46746a09153f25273831cdf78c8c2264c98da28cab28fd2217d4` |
| `36_MHz_OMUX.txt` (extracted from the zip) | `b229565369c9e1867039506c2031b4dbe3e6d6749fd12e77109759982a6172e3` |

The extracted text files are kept in the session scratch directory and are not part of the repository.

## 3. Regeneration check

The committed generator was run on the extracted Annex E text tables in a scratch directory that contains only `src/geosim/data/`. The repository was not modified:

```
python3 -I <repository>/scripts/build_mux_filters.py <directory with 36_MHz_IMUX.txt and 36_MHz_OMUX.txt>
```

Result: all six arrays are exactly equal to the committed arrays (`np.array_equal` for `fs`, `bulk_delay`, `imux_36`, `imux_72`, `omux_36`, `omux_72`). The archive differs in size (32,088 bytes regenerated, 32,121 bytes committed); this was not investigated further. The build script writes `src/geosim/data/mux_fir.npz` relative to the working directory, so regeneration must run in a copy, never in place.

## 4. Verification of the FIR against the table

Commands (from the repository root). Appendix A is the per-band script and Appendix B the level analysis; both are reproduced below.

```
python3 -I check_mux_detail.py <36_MHz_IMUX.txt> src/geosim/data/mux_fir.npz imux_36
python3 -I check_mux_detail.py <36_MHz_OMUX.txt> src/geosim/data/mux_fir.npz omux_36
python3 -I - < level_analysis.py      # Appendix B, run from the repository root
```

Runtime: about 0.96 s wall time per invocation of the per-band script on this workspace. Peak RSS: about 101 MB (Python with NumPy and SciPy). Runtime of the level analysis was not measured separately.

### 4.1 Per band (36 MHz; FIR evaluated at the table frequencies)

| Table | \|f\| band (MHz) | max \|Δgain\| (dB) | median \|Δgain\| (dB) | median group delay, table / repository (ns) |
|---|---|---|---|---|
| IMUX | 0–18 | 0.00 (below 0.005) | 0.000 | 1.0 / 0.2 |
| IMUX | 18–25 | 0.12 | 0.006 | 49.4 / 48.9 |
| IMUX | 25–45 | 2.03 | 0.026 | −55.7 / −55.1 |
| OMUX | 0–18 | 0.00 (below 0.005) | 0.000 | 3.7 / 3.7 |
| OMUX | 18–25 | 0.00 (below 0.005) | 0.001 | 16.9 / 17.0 |
| OMUX | 25–45 | 1.00 | 0.005 | −20.7 / −20.8 |

The IMUX median group-delay differences are 0.5–0.8 ns in magnitude: the repository is lower below 25 MHz and higher at 25–45 MHz. The cause is not investigated. The OMUX differences are at most 0.1 ns.

### 4.2 By table gain level (Appendix B)

IMUX (801 table points, |f| ≤ 45 MHz):

| Table gain ≥ (dB) | Points | max \|Δgain\| (dB) | max \|Δτg\| (ns) | median \|Δτg\| (ns) |
|---|---|---|---|---|
| 0 | 1 | 0.00 | 0.9 | 0.87 |
| −20 | 386 | 0.07 | 4.1 | 0.86 |
| −40 | 492 | 0.12 | 16.5 | 0.86 |
| −60 | 726 | 0.23 | 24.9 | 0.88 |

OMUX (801 table points, |f| ≤ 50 MHz):

| Table gain ≥ (dB) | Points | max \|Δgain\| (dB) | max \|Δτg\| (ns) | median \|Δτg\| (ns) |
|---|---|---|---|---|
| 0 | 1 | 0.00 | 0.0 | 0.03 |
| −20 | 388 | 0.00 | 0.4 | 0.03 |
| −40 | 647 | 0.05 | 11.5 | 0.07 |
| −60 | 801 | 1.00 | 69.2 | 0.12 |

Points with \|Δgain\| > 0.5 dB:
- IMUX: 4 points, |f| 35.5–37.8 MHz, table gain −72.6 to −64.3 dB.
- OMUX: 4 points, |f| 29.9–30.0 MHz, table gain −56.1 to −53.1 dB.

Full-table extremes:
- Gain: IMUX table [−75.0, 0.0] dB, repository [−75.0, −0.0] dB, maximum \|Δgain\| 2.03 dB. OMUX table [−56.1, 0.0] dB, repository [−55.9, −0.0] dB, maximum \|Δgain\| 1.00 dB.
- Group delay: IMUX table [−66.6, 194.0] ns, repository [−92.6, 318.6] ns (the bulk delay is removed in the repository), largest \|Δτg\| 126.6 ns at −35.77 MHz (table gain −74.7 dB). OMUX table [−275.2, 55.6] ns, repository [−339.3, 55.3] ns, largest \|Δτg\| 69.2 ns at −30.12 MHz (table gain −55.8 dB).

### 4.3 Interpretation

- Where the table gain is at least −20 dB, the 36 MHz FIR matches the Annex E gain to within 0.07 dB (IMUX) and below 0.005 dB (OMUX). The worst group-delay deviation in that region is 4.1 ns (IMUX) and 0.4 ns (OMUX).
- Deviations above 0.5 dB in gain occur only at table gains below −53 dB, in the deep stopband. The cause is not isolated. Candidates to test: truncation to 1024 taps, and the resolution of the stopband entries in the table.
- Analyses that depend on rejection deeper than about −50 dB should not use these taps without further checks.

## 5. Permission status

- The researcher reports that ETSI permission exists for the derived tables committed here (statement of 2026-10-27). No written permission is stored in this repository, and the statement has not been checked against a document.
- Before publication, fill in:
  - ETSI permission reference: [to be filled in]
  - Date: [to be filled in]
  - Scope (numerical tables, figure-derived curves, public repository, publication): [to be filled in]

## 6. Manuscript wording

`paper/manuscript.md` (line 87) already cites `[@etsi2014dvbs2; @etsi2021dvbs2guide]`, states that the default reference filters are FIR responses derived from the Annex E tables, and states that the default nonlinear response is digitized from the H.3 curve. Suggested addition to the data-source statement:

> The 36 MHz IMUX and OMUX responses were derived from the numerical tables in the Annex E attachment of ETSI TR 102 376-2. They agree with those tables to within 0.07 dB (IMUX) and below 0.005 dB (OMUX) wherever the table gain is at least −20 dB. The 72 MHz responses follow the bandwidth-scaling rule of that document and are not checked against a separate table. The TWTA curves were digitized from Figures H.2 and H.3 of ETSI EN 302 307-1 V1.4.1, Annex H.7. These derived data are used with ETSI permission [reference and date to be inserted].

## 7. Limits

- Only the 36 MHz tables were checked numerically. The 72 MHz taps follow the scaling rule and are not checked.
- The TWTA curves were digitized from vector paths; the digitization error is not quantified. Figure H.2 has one point per dB with a stepped phase, and intermediate values are linearly interpolated (see the limits in `docs/plan/kaynak_transponder_modeli.md`).
- The check compares the repository FIR with the Annex E text tables. It does not check the text tables against the printed figures of TR 102 376-2.
- The comparison uses the 801 table frequencies per table; it does not test intermediate frequencies.

## Appendix A — per-band script (`check_mux_detail.py`)

```python
import sys, numpy as np
from scipy.signal import freqz
tab_path, npz_path, key = sys.argv[1], sys.argv[2], sys.argv[3]
FS = 288e6
rows=[]
for line in open(tab_path, encoding="utf-8", errors="replace").read().splitlines()[4:]:
    p=line.split()
    if len(p)>=3:
        try: rows.append([float(v) for v in p[:3]])
        except ValueError: pass
t=np.array(rows); f=t[:,0]*1e6; g=t[:,1]; gd=t[:,2]*1e-9
d=np.load(npz_path); taps=d[key]; bulk=int(d["bulk_delay"])
w=2*np.pi*np.clip(f,-FS/2,FS/2-1)/FS
_,H=freqz(taps,1,worN=w)
gr=20*np.log10(np.maximum(np.abs(H),1e-12))
ph=np.unwrap(np.angle(H))
gdr=(-np.gradient(ph,2*np.pi*f)-bulk/FS)*1e9
diff=np.abs(g-gr)
for lo,hi in [(0,18),(18,25),(25,45)]:
    m=(np.abs(f)/1e6>=lo)&(np.abs(f)/1e6<hi)
    if m.any():
        print(f"|f| in [{lo},{hi}) MHz: gain |diff| max {diff[m].max():.2f} dB, median {np.median(diff[m]):.3f} dB; "
              f"table gd median {np.median(gd[m])*1e9:.1f} ns, repo gd median {np.median(gdr[m]):.1f} ns")
```

## Appendix B — level analysis

Run from the repository root (reads `src/geosim/data/mux_fir.npz`); the text tables are read from the scratch directory.

```python
import numpy as np
from scipy.signal import freqz
FS = 288e6
d = np.load("src/geosim/data/mux_fir.npz")   # run from repository root
bulk = int(d["bulk_delay"])
S = "/tmp/claude-0/-home-claude/b57d6a4e-dc81-5c81-ada3-297595613d88/scratchpad/etsi_annexE/"
def load(path):
    rows = []
    for line in open(path, encoding="utf-8", errors="replace").read().splitlines()[4:]:
        p = line.split()
        if len(p) >= 3:
            try: rows.append([float(v) for v in p[:3]])
            except ValueError: pass
    t = np.array(rows)
    return t[:,0]*1e6, t[:,1], t[:,2]*1e-9
for name, fn, key in [("IMUX", "36_MHz_IMUX.txt", "imux_36"), ("OMUX", "36_MHz_OMUX.txt", "omux_36")]:
    f, g, gd = load(S + fn)
    w = 2*np.pi*np.clip(f, -FS/2, FS/2-1)/FS
    _, H = freqz(d[key], 1, worN=w)
    gr = 20*np.log10(np.maximum(np.abs(H), 1e-12))
    ph = np.unwrap(np.angle(H))
    gdr = (-np.gradient(ph, 2*np.pi*f) - bulk/FS)*1e9
    gdt = gd*1e9
    dg = np.abs(g - gr)
    dd = np.abs(gdt - gdr)
    print(f"{name}: n={len(f)} f=[{f.min()/1e6:.1f},{f.max()/1e6:.1f}] MHz")
    for thr in (0.0, -20.0, -40.0, -60.0):
        m = g >= thr
        if m.any():
            print(f"  table gain >= {thr:+.0f} dB: n={m.sum()}  gain|diff| max {dg[m].max():.2f} dB  gd|diff| max {dd[m].max():.1f} ns  gd|diff| median {np.median(dd[m]):.2f} ns")
    big = dg > 0.5
    if big.any():
        print(f"  gain|diff|>0.5 dB: n={big.sum()}, table gain {g[big].min():.1f}..{g[big].max():.1f} dB, |f| {np.abs(f[big]).min()/1e6:.1f}..{np.abs(f[big]).max()/1e6:.1f} MHz")
    print(f"  full-band gain: table [{g.min():.1f},{g.max():.1f}] dB, repo [{gr.min():.1f},{gr.max():.1f}] dB; max gain|diff| {dg.max():.2f} dB")
    print(f"  full-band gd: table [{gdt.min():.1f},{gdt.max():.1f}] ns, repo [{gdr.min():.1f},{gdr.max():.1f}] ns")
    i = np.argmax(dd)
    print(f"  largest gd|diff| {dd[i]:.1f} ns at f={f[i]/1e6:.2f} MHz, table gain {g[i]:.1f} dB")
```
