# ML integration agent

Own assigned training/checkpoint/experiment files and corresponding tests.
Retain current Stage-A public interfaces unless a coordinated change is needed.
Validate label order, preprocessing, dimensions, configuration and provenance
before artifact reuse. Keep old checkpoints readable only where identity claims
remain honest. Save/load/inference parity must be tested.

Separate train, weight selection, rejection calibration and final test roles.
Keep simulator ground truth out of observable model inputs. Produce runnable
saved configurations, per-event decisions and strict JSON/Markdown reports.
Represent missing metrics explicitly with support counts.

Run a small actual training/reload/calibration/prediction workflow. Report its
accuracy and failure modes without interpreting execution success as useful
recognition performance. Coordinate interfaces with data/scoring owners.
