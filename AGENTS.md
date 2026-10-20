# Repository development instructions

Build the project incrementally using the existing checkout. Each cloud task is
isolated; do not create a Git worktree unless the user requests one.

- Read `README.md`, `docs/plan/DURUM.md` and the relevant protocol before editing.
- Preserve frozen A1 physical sampling, classes and split definitions. Introduce
  a separate version for changed experimental semantics.
- Keep model inputs separate from simulator truth. Never use final unknown test
  families to select weights, fit feature statistics or calibrate thresholds.
- Keep all variants of a scenario group in one train/validation/test role.
  Weight-selection validation and rejection calibration use distinct groups.
- Higher unknown scores mean more unknown-like. State metric positive classes,
  denominators, sample counts and uncertainty assumptions explicitly.
- Use the bundled DVB-S2 reference curves as the primary payload model; Saleh
  is an alternative. Do not claim complete DVB-S2 framing or dual polarization
  until those blocks exist and are tested.
- Never hide simulator failures as infeasible scenes. Validate reused data,
  checkpoints and calibrators against configuration and provenance.
- Use strict JSON: missing metrics are `null` with counts, not NaN.
- Keep raw/generated datasets, checkpoints, virtual environments and credentials
  outside Git. Commit configs, commands and small honest experiment summaries.
- Test changed behavior with meaningful checks and a representative integration
  run. Do not equate a tiny successful run with recognition quality.
- Record implementation status and remaining work in `docs/plan/DURUM.md`.
- The user has requested publishing completed work to this GitHub repository.
  Push tested milestones with normal fast-forward Git operations; never force
  push or overwrite remote changes.

When parallel agent work is useful, use the task briefs under `.agents/`. Give
each agent disjoint file ownership, agree on shared APIs first, and have the
integrator review the combined result. These briefs document project roles;
the execution platform supplies the agent runtime.
