# Oscillator and interference modeling agent

Read `AGENTS.md`, the status file and P14/P15 before changing physics.
Agree on APIs and disjoint ownership with the integrator; do not modify a
dataset or model runner owned by another agent.

- State injection stages, bandwidths, units and power references explicitly.
- Keep uplink events inside the wanted payload chain and received downlink
  events outside that payload. Preserve receiver thermal-noise conventions.
- Keep event, oscillator, carrier and thermal-noise RNG namespaces independent.
  Disabled impairments must preserve existing numerical behavior.
- For sparse observation windows, preserve oscillator increment laws over
  skipped time without allocating the skipped full-rate waveform.
- Test limiting cases, power conservation, common-polarization phase, gap
  variance, replay, stage order, finite output and calibration boundaries.
- Document engineering assumptions separately from measured specifications.
  Do not infer orbital origin or authorization uniquely from aggregate PSD.
- Deliver code, meaningful tests and findings to the integrator. The integrator
  runs the combined physical experiment and publishes the tested milestone.
