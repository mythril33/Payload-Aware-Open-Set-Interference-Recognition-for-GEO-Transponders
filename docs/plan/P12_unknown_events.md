# U1-dev/1: test-only unknown source families

The standalone `geosim.unknowns` module leaves A1 classes, splits and samplers
unchanged. It produces uplink events through the same IMUX/TWTA/OMUX and
monitoring chain as A1. It is a development source protocol, not a complete GEO
open-set benchmark.

| Family | Source definition |
|---|---|
| `pulsed` | Periodic gated CW, 6–18 ms ON per 40–90 ms period |
| `wideband_noise` | Circular Gaussian noise, rectangular FFT-bandlimited to 60–90% of transponder bandwidth, centered in band |
| `intermittent_bursts` | Irregular gated CW intervals, 80–160 ms ON, separated by 120–300 ms OFF |

The two temporal families deliberately have non-overlapping ON-duration ranges.
Their timing uses physical seconds. The 128 monitoring snapshots are separated
by 10 ms; they are not a continuous IQ record. Generated temporal samples must
contain both occupied and unoccupied sampled windows. A phase transition can
occur inside a snapshot and can be smeared by payload filtering.

Pulse period, ON duration and phase are deterministically rejection-sampled
until the actual retained monitor windows contain at least one full ON and one
full OFF window. This prevents rare aliases from making a generated pulse
invisible at every sampled instant. At most 64 random draws are tried, followed
by a finite deterministic in-range fallback; an unsupported sampling pattern
fails explicitly. Metadata records the rejected-draw count, fallback use and
visibility condition. This is a distribution of observable pulse events, not
unconditional physical pulse occurrence. Active power is never renormalized.

`active_c_over_i_db` is total planned carrier power divided by active source
power, expressed in dB. The planned uplink carrier load has unit power. Sources
are not divided by duty fraction: sparse signals retain the specified active
power and have lower observation-average interference power. Metadata records
source duty, sampled occupancy, active power, observed mean source power and
observation-average C/I. For noise, the requested active power is an ensemble
expectation, not a per-frame amplitude normalization. Observed occupancy and
mean source power exclude the leading simulation samples discarded by the
monitoring receiver for filter warm-up.

All families with one scenario seed share their plan, nominal IBO (9–13 dB),
uplink/downlink C/N (15–30 dB), carrier symbols and thermal-noise RNG streams.
Family parameters use a separate RNG namespace. Default seeds start at 900000,
outside A1 source split ranges. Unknowns are test-only and must never enter
weight selection, feature-statistic fitting or rejection calibration.

Extra wideband noise may be observationally indistinguishable from an elevated
uplink noise floor. Detecting it does not establish a distinct physical cause.
The generator's name is ground truth for controlled evaluation, not evidence
that a spectrum-only recognizer can infer source identity.

```bash
python -m geosim.unknowns --out data/unknowns-pilot --n-seeds 6
```

The output contains 100-seed shards with float16 spectra/masks, family indices,
scenario seeds, JSONL metadata and checksum-backed request/manifest files.
Completed verified reuse preserves original provenance. Changed generator,
runtime or configuration requires a fresh output directory; corruption and
unverified partial shards are rejected. Historical verified artifacts remain
readable after source changes. `load_unknowns`, `read_unknown_manifest` and
`unknown_fingerprint` validate the complete dataset before returning.
