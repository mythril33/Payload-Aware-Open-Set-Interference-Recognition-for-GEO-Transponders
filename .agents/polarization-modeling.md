# Polarization modelling agent

Preserve the frozen single-polarization simulator. Model uplink coupling before
the two independent payload paths, downlink coupling after OMUX, and instrument
response separately. Receiver calibration must be fitted from independent
instrument pilots; it must not estimate away propagation leakage using scene
labels or simulator truth.

State the Jones approximation and power convention. A unitary symmetric mixer
models ideal polarization-basis coupling, not arbitrary antenna loss. Test
isolated-source XPD, total-power conservation, phase, identity reduction to A1,
noncommutation with nonlinear payloads, noise placement and coherent zero-drive
limits. Aggregate power ratio with two loaded feeds is not XPD.

Use separate operator plan masks when carrier plans differ. Both measured
spectra share one power reference so relative polarization levels survive
preprocessing. Validate instrument-calibration rank/conditioning and persisted
provenance. Report observed evidence separately from hidden physical causes.

Agree on simulator, data and model interfaces before parallel changes. Keep
implementation ownership disjoint and run a small physical integration before
publishing a milestone. Do not claim eight-class or operational performance
from a two-class development experiment.
