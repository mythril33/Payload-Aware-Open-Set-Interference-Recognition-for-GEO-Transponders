# P19 — B2 physical-observation foundation

Date: 2026-10-21. Parent protocol: frozen [B2/1](P18_b2_protocol.md).
Artifact stage: **B2-base/1**, known physical observations. The manifest records
`benchmark_complete: false`. The five-channel model, observation-based
cancellation, unknown/CID tests and matched ASI test set are later stages.

## Block contracts

`geosim.b2_protocol` fixes the eight labels, role counts and reserved scenario
IDs from P18. The known-label order is `clean`, `cw`, `swept_cw`, `unauthorized`,
`overdrive`, `cross_pol`, `adjacent_satellite`, `carrier_under_carrier`.
Known `adjacent_satellite` is uplink ASI. The future test family
`adjacent_satellite_downlink` has a distinct name. Historical E1 files and labels
remain readable without rewriting their contents.

| Role | Full B2 groups | First scenario ID |
|---|---:|---:|
| train | 1500 | 3000000 |
| val-select | 150 | 3100000 |
| val-calib | 150 | 3150000 |
| test | 500 | 3200000 |
| test-matched, reserved for a later generator | 150 | 3300000 |

Pilot limits select prefixes of these roles. They do not redefine their ranges.
The base generator emits only the eight known variants in the first four roles.
Unknowns and benign CID overlays cannot enter its training or calibration data.

`geosim.b2_scenarios` combines existing event factories with the dual engine.
Every group's eight variants share plans, carrier/noise RNG streams, phase
realizations, link settings and missing-carrier state. Overdrive changes only
the co-feed IBO to 1–4 dB; cross-pol changes uplink XPD to 10 dB. Other external
events enter the co uplink before physical coupling and the wanted payload.

Operator plans are conditioned on feasibility of all known event placements.
Only an explicit `InfeasibleCarrierError` permits a new co plan, with at most
64 draws. The opposite plan and waveform/noise seeds remain fixed. Metadata
records rejected draws and the actual plan RNG namespace. Simulator errors
propagate; no label or scenario is silently skipped.

## Planned and transmitted carriers

`simulate_dual(..., active_carriers=(co_mask, cross_mask))` accepts strict boolean
masks aligned with the full operator plans. All planned waveforms consume their
original RNG draws, including muted carriers. This preserves other carrier
realizations. The operator masks retain the missing carrier, while the actual
transmitted power falls. Gain and uplink-noise references stay tied to nominal
unit loading: **fixed gain, no power renormalization**. Actual IBO/OBO and active
planned power are retained as simulator metadata.

The predeclared missing-carrier probability is **15%**, within K17b's approved
10–20% range. One carrier is selected across both feeds. A sole co carrier is
excluded so that a carrier-under-carrier event always has an active victim.
Inactive CuC victims are rejected in a separate bounded event-parameter loop;
the C/I draw stays fixed. This conditioning is recorded. A diagnostic
`missing_carrier=True/False` override is available for physics checks, but the
dataset writer always uses the shared group draw.

Physical carrier absence is distinct from the later training-only plan-shift
augmentation. Here `plan_consistency` is a separate binary target; active masks,
true IBO/XPD and event parameters are not additional observed model channels.

## Storage and reproduction

The stored arrays are float16 `spec[N,2,128,512]`, float16 `mask[N,2,512]`,
integer `label`, `seed` and `plan_consistency`. Separate JSONL carries simulator
truth and provenance. The base stage stores no raw IQ or placeholder fifth
channel. Independent synthetic instrument pilots fit one calibration bound to
the request. Shards and metadata have checksums and are validated on reuse;
completed historical artifacts are checked without replaying a newer sampler.
`iter_b2_shards` supports bounded-memory reading.

```bash
source /workspace/.venvs/geosim/bin/activate
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m geosim.b2_dataset --config configs/b2_base.json --out data/b2-base-pilot --limit-groups 2 --groups-per-shard 1
python -m geosim.b2_dataset --config configs/b2_base.json --out data/b2-base-pilot --limit-groups 2 --groups-per-shard 1
python scripts/check_b2_base.py --data data/b2-base-pilot --out runs/b2-base-pilot/physics.json --check-missing
python -m pytest -q
```

The second command verifies resume. Use a fresh directory after source or
configuration changes. Generated data stay outside Git. Full B2 production
will follow cancellation/feature validation and resource measurements; this
physical-stage pilot does not train a classifier or establish recognition quality.

## Validation evidence

The final complete suite passed **707 tests**. New coverage includes explicit
activity masks and legacy identity, frozen B2 role boundaries, shared eight-class
scenes, active CuC victims, bounded feasibility errors, independent calibration,
power/placement consistency, corruption, historical reads and verified resume.
A natural missing-carrier group (`3000008`) round-trips all eight auxiliary
targets through shard generation and both lazy/eager reading.

The [physical pilot](../results/b2_base_pilot.md) generated **64 observations**,
two groups per role, and verified completed resume. Those fixed pilot groups
drew no natural missing carriers. Eight additional forced diagnostic twins
cover all known classes and remain outside the dataset. Their full operator
plans and nominal gain are unchanged; active power falls and clean actual IBO
increases. Both 36 MHz/no-phase-noise and 72 MHz/phase-noise comparisons against
the prior `1ef8e9d` engine preserve default IQ/PSD/masks and metadata exactly.

Production took 109.55 seconds wall time, with a 545.52 MiB peak producer RSS
and 16.49 MiB of stored artifacts. The test suite ran concurrently for part of
the pilot; full-run cost and final feature-stage cost still require measurement.
No classification, unknown-rejection or cancellation-quality result is claimed.

Next: implement cancellation from observed IQ and operator information, add
the fifth input channel and independent plan-consistency head, then connect
center loss and final test-only families. The center-loss weight referenced by
P18 must be specified in the training configuration before training begins;
P6 does not currently give its numeric value.
