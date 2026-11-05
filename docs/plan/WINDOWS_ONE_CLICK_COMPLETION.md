# Windows One-Click GEO Workbench — Implementation and Completion Handoff

**Prepared:** 2026-11-05
**Source baseline:** `main` `3f26393e803e458872293692efc9e3166fb5baf2` (merged PR #61)
**Owner of implementation:** Claude (separate coding session), with independent test evidence and researcher review.
**Status:** IMPLEMENTATION SPECIFICATION ONLY; no code, installed app or scientific execution is delivered by this document.
**Primary objective:** A Windows desktop user can open the GEO research workbench with a double-click and start a **bounded, genuine RF development exercise** with one desktop action, with visible stages, logs, safe cancellation and durable results. The user must not need a terminal for routine sessions.
**Secondary objective:** preserve a disciplined path to final GEO benchmark completion. **Do not** present a successful pilot as an authorized 21,350-observation benchmark.

## 0. Source evidence / reuse rather than rebuilding

Read `AGENTS.md`, `CLAUDE.md`, `README.md`, `RESEARCH_ROADMAP.md`, `docs/plan/DURUM.md` and the frozen `docs/plan/P18_b2_protocol.md` before editing.

Existing, reused assets:

- `windows/KURULUM.bat` → `windows/install.ps1` already installs two separate environments, `.venv-dashboard` and `.venv-rfml`, without admin; creates Desktop and Start Menu shortcuts.
- `windows/launch_app.ps1`, `windows/launch_dashboard.bat`, `windows/launch_rfml.bat`, `windows/stop_apps.ps1`, `windows/preflight.ps1` already implement Python/Streamlit launch, loopback-only 127.0.0.1, port fallback, health check and logs.
- `dashboard/app.py`, `dashboard/ui/runner.py`, `dashboard/geodash/commands.py`, `dashboard/geodash/jobs.py`, `dashboard/geodash/portable.py`: existing allowlisted commands and single-job manager. `real-exercise` is the genuine bounded path, with `groups` in `{1,2}`, via `scripts/b2_real_execution.py --out ... --groups 1`. Runs **train/val-select/val-calib only**, CPU only; generates → trains tiny model → calibrates → freezes. It is marked `requires_posix=True`: do not try to bypass the `fcntl` boundary on native Windows.
- `dashboard/geodash/paths.py` forces job outputs outside the checkout; default `~/.local/share/geo-dashboard`; `GEO_DASHBOARD_HOME` may be set safely. `JobManager` writes `job.json`/`log.txt`, enforces one job and timeout, tracks process trees and verifies `exercise.json` fields.
- `windows/BENIOKU.md`, `dashboard/README.md`, `windows/SURUM_NOTLARI.md`: already state WSL2 is needed for the `real-exercise` path.
- `scripts/build_windows_package.py` and `.github/workflows/windows-package.yml`: existing ZIP builder and Windows-latest CI test/smoke/start/stop + artifact distribution. This is a **ZIP of sources and scripts** with `VERSION.json`, **not a self-contained .exe**; it excludes `.git` and generated data.
- Latest known actions on older `8aa6645`: B2 readiness 41414105903 PASS, Windows package 41414109964 PASS. The merged `3f26393` has no matching new CI evidence on current lookup; obtain exact-head evidence.

### The critical technical distinction

**Native Windows** currently opens the dashboard and runs read-only tests/diagnostics; **native Windows cannot run the governed `real-exercise`** because POSIX-only locks are used deeper in the execution chain. **WSL2 Ubuntu** is the preferred engine for the genuine, bounded RF exercise. A browser dashboard served from WSL2 is still accessed from Windows on `127.0.0.1`; do not build a new API bridge if the existing Streamlit app can serve the user correctly. Treat the Windows-native dashboard as a fallback for inspection only, never a disguised production runner.

## 1. User experience (must be tested on real Windows 10/11)

After **one-time** guided setup and private-repo authentication if a WSL checkout is required:

1. Desktop shortcut **GEO Workbench** → starts/reuses one instance of Track A dashboard; opens the Windows default browser to the local URL; displays *engine: WSL2 Ubuntu / native Windows*, source revision and gate state. A native fallback is acceptable for inspection when WSL2 is absent.
2. Desktop shortcut **GEO Pilot Baslat** → without typing terminal commands, performs a safe preflight and starts the existing bounded `real-exercise` with exactly **one group per allowed development role** on CPU in WSL2; opens its job page/logs. The shortcut may initiate the bounded job automatically only when WSL2 has been set up and all preflight and identity checks pass. No repeat start if a job is already running; show its job ID instead.
3. Within the UI: **GEO Pilot Baslat (1 group)** / optional **2-group bounded pilot** choice, **Durum**, **Iptal**, **Gunluk**, **Sonuc Klasorunu Ac**, **Raporu Indir**; show stage (generation, training/calibration, freeze, verification), elapsed time, and *inferred* progress only. Never label elapsed/timeout percentage as completed work.
4. Desktop shortcut **GEO Islem Durdur** stops only the workbench-owned bounded job (safe termination or documented interruption); **GEO Workbench Kapat** stops app/launcher services, does **not** silently kill a scientific job or delete evidence. Show a confirmation/warning when jobs are running.
5. Existing **RF-ML Ogrenme Uygulamasi** shortcut remains unchanged and isolated, with its own venv, data, results and claims.

Suggested main UI:

```text
GEO PAYLOAD AWARE — RESEARCH WORKBENCH
Engine: WSL2 Ubuntu  |  Source: <verified SHA>  |  Benchmark: INCOMPLETE
Research gates: CLOSED / NO PRODUCTION AUTHORITY

[ GEO PILOT BASLAT ]   [ DURUMU YENILE ]   [ GUVENLI IPTAL ]
Profile: 1-group development, CPU-only, no held-out access
Stage: RF generation → train → val-calib → freeze → report
Elapsed: ...  |  Last verified artifact: ...
Output: <external run folder>    [ LOGS ] [ REPORT ] [ FOLDER ]

Research results: PILOT ONLY (not 21,350-observation benchmark)
Production 21,350 / GPU / LOKO / held-out: LOCKED (reasons + approvals)
```

The pilot desktop shortcut must **not** be labelled `Full Benchmark`, `Production`, `21,350 Baslat` or `Complete Research`.

## 2. Recommended minimal architecture (avoid platform rewrites)

### A. Windows launcher and setup

- Keep `KURULUM.bat` and the two existing venvs functional; add optional WSL integration rather than replacing the installer.
- Add narrowly scoped launchers, e.g. `windows/start_geo_workbench.bat`, `windows/start_geo_pilot.bat`, `windows/stop_geo_pilot.bat`, `windows/wsl_backend.ps1`, `windows/setup_wsl_backend.ps1` (names may vary, but documents/tests must match them).
- Windows scripts must handle paths with spaces and non-ASCII usernames, correct exit codes, stalled launch, stale/recycled PIDs, port conflict and repeated double-click, plus log messages on failure. Use process-scoped execution policy only; do not globally weaken Windows security settings or create wide firewall listeners.
- On first use, detect `wsl.exe`, `wsl -l -v`, Ubuntu availability, `python3.12`, disk/RAM and `VERSION.json`. WSL2 installation requires **explicit user consent** and may need elevated Windows setup/reboot. **Never** install WSL, enable Windows features, download software or enter GitHub credentials silently.
- Put the governed WSL checkout and venv on WSL ext4 (e.g. `~/geo-workbench-src`), not under `/mnt/c`; keep outputs **outside** this checkout. When the GitHub source repository is private, use an explicit one-time authenticated clone/update step, or an independently verified, committed immutable snapshot whose provenance limitations are clearly stated. The CI ZIP has no `.git`; `VERSION.json` alone is **not** a substitute for Git source-integrity checks or a production lock. Never initialize a fake history to pass gates.
- Validate Windows package `VERSION.json` and WSL source commit/digest compatibility before starting the pilot; reject a mismatched or modified checkout with an actionable error. An intentional update is a separate, explicit, logged operation, not an implicit pull before each run.
- Use WSL2 localhost forwarding to serve the Track A Streamlit app to Windows; bind **127.0.0.1** only; verify health before browser launch. Do not add an unauthenticated HTTP command-execution endpoint. Keep the existing native dashboard as explicit inspection fallback.

### B. A safe one-click pilot controller

- Reuse `geodash.commands.REGISTRY` and `geodash.jobs.JobManager`. Prefer a small WSL-side orchestration/CLI wrapper that calls the **same** `real-exercise` command spec with `groups=1` and observes the real job records; do not invent a second privileged execution path or use `shell=True`.
- If a launcher creates a job in a short-lived process, be careful: `JobManager` distinguishes an exited owner from a verified job and may report `finished_unrecorded`, not `SUCCEEDED`. Either keep a persistent, single owner/supervisor until the subprocess exits or implement a tested durable completion record with actual exit code and artifact verification. Never convert `finished_unrecorded` to success by assumption.
- Persist logs and results in external, writable directories, with UUID/run ID, timestamp, source SHA, input scope, role names, groups=1/2, exact argv, Python/OS/dependency identity, return code and checksum/provenance of output. Respect the existing schemas; add a versioned metadata adapter rather than changing frozen scientific artifacts.
- Reuse current job lock / one-job-at-a-time guard; add idempotent launch, explicit cancellation and restart recovery tests. Process termination must validate ownership, not kill a potentially recycled arbitrary PID. Preserve partially generated data and journal for forensics; no destructive cleanup on error.
- Propagate code/refusal reasons to the dashboard in plain Turkish; record stdout/stderr. A closed gate is **not** a software crash; preflight `BLOCKED` may be an informational result, never permission.
- Keep `real-exercise` CPU-only, 1–2 group ceiling, no protected test/test-matched reads, no GPU, no LOKO, no production. Do not change its safety assertions, `requires_posix`, `SCRIPT_ALLOWLIST`, stop conditions or provenance boundaries.

### C. Dashboard changes

- Extend `dashboard/ui/home.py` and `dashboard/ui/runner.py` with one prominent **bounded pilot** action, persistent job history, stage-by-stage status, logs, JSON report download and output-location link. Prefer adapting existing `_active_panel`, `_show_outputs`, and `job_manager()`; do not fork the Streamlit codebase.
- The home page must clearly distinguish `APP_READY`, `PILOT_RUNNING`, `PILOT_COMPLETE`, `BENCHMARK_NOT_RUN`, `COMPUTE_GATES_CLOSED`, `HOST_NOT_QUALIFIED`.
- Explain that `exercise.json` proves bounded functional flow, not real recognition performance. A synthetic/pilot record must not populate GEO manuscript final results or set `benchmark_complete=true`.
- Do not auto-open restricted evaluation files when rendering the UI, reports, or files list.

## 3. Non-negotiable scientific and governance boundaries

Read the frozen protocol and existing E9/E12 approval records. Explicitly preserve:

- `docs/plan/P18_b2_protocol.md` and all frozen class/role/seed semantics; scenario groups never cross roles.
- `full_generation`, `full_gpu_training`, `full_loko_sweep` remain `NOT_AUTHORIZED`; final held-out test read separately restricted; `PRODUCTION_LAUNCH_ENABLED=False`, `PINNED_TRUST_ROOT=None` unless changed under separate explicit production authorization and independent review. `benchmark_complete=false`.
- The E9/E12 scientific choices are **not** compute rights; no button, CLI flag, env var, shortcut or startup default may bypass DR-04/DR-05, GPU probe/host qualification, E16/E17 custody or D-1 test exposure and D-8 metadata verification.
- No training/selection/calibration on held-out roles. When a future final 15-fit campaign is separately authorized, scorer selection and all 9 canonical freezes precede the first final test read, with mandatory 500/35/465 and exposure-excluded 498/148 sensitivity rows.
- Existing Track B is independent; do not reuse Track B data or models to claim GEO/B2 results.

For the eventual full-scale command, **do not** add a one-click `production --execute` shortcut in this sprint. A future authorized operator-only workflow must validate signed scope, exact head, host, independent backup, first-shard timing, resource ceilings, frozen model inventory, audit and explicit final-evaluation grants. If any missing, **NO-GO**.

## 4. Proposed implementation sequence: 3 delivery increments

### Increment 1 — reuse / one-click UI skeleton (software only)

1. Baseline `main` and exact tests; confirm `windows-package.yml` and B2 readiness status for the current revision.
2. Implement reusable Windows start/stop shell wrappers and Desktop/Start shortcuts; preserve existing installation. Open the dashboard once; double-click again only focuses/opens the existing instance.
3. Add UI status clarity and a pilot button whose native-Windows path gives a clear WSL2 setup explanation, never a Python traceback.
4. Add regression tests for paths, process ownership, duplicated launches, no WSL, package SHA mismatch and safe refusals.

**Done:** clean Windows installation on a real machine, one-click dashboard, clear disabled pilot when WSL missing, no gate changes.

### Increment 2 — WSL2 genuine bounded pilot

1. Opt-in WSL2 bootstrap and private-repo source acquisition. Pin exact revision, Python 3.12 runtime, packages, and WSL-only run directory. User need not type commands after setup.
2. Start existing Track A app from WSL and surface localhost URL on Windows, with clear engine/source identity.
3. Implement one-click `GEO Pilot Baslat` shortcut and same-button UI; invoke `real-exercise` through existing JobManager allowlist and persistent ownership.
4. Show generated stage logs, real exit code, verified `exercise.json`, PDF not required, downloadable JSON and safe cancellation.
5. Simulate interrupted/rebooted/duplicate starts and stale PID/port records; ensure no false success or destroyed evidence.

**Done:** one click from Windows desktop executes one bounded real-physics CPU pilot in WSL2, reports an actual verified completed/failed outcome and leaves durable outputs.

### Increment 3 — verify and ship a usable Windows artifact

1. Extend `tests/test_dashboard_*.py`, add `tests/test_windows_oneclick_*.py` or comparable focused tests, and update `.github/workflows/windows-package.yml` if needed. CI verifies package paths, encoded shortcuts, idempotent launch, command allowlist and mock WSL failure/blocked cases; **do not** claim GitHub `windows-latest` can validate real WSL2 virtualization by default.
2. Run existing dashboard and package test matrix on `windows-latest`; run true WSL2/Ubuntu end-to-end on a separate physical Windows PC or qualified VM and record environment, revision and evidence. Confirm clean uninstall/reinstall and existing Track B continues to work.
3. Build `Payload-Aware-GEO-Workbench-Windows.zip` through the repository builder from an exact committed reviewed SHA, verify `*.sha256`, `VERSION.json` and no excluded data/credentials/virtualenv paths; provide Turkish `windows/BENIOKU.md` instructions and updated release notes.
4. Send code in focused PR(s); wait for exact-head tests, review and merge. A GitHub Actions artifact is **not** automatically a signed installer or GitHub Release.

**Done:** a verifiable workbench release candidate that a Windows user can install and use without any terminal for routine bounded pilot work.

## 5. Tests that MUST pass

| ID | Scenario | Required result |
|---|---|---|
| W-01 | `KURULUM.bat` on clean Windows 11 + Python 3.12 | Non-admin install succeeds; two distinct environments and shortcuts |
| W-02 | Windows native, no WSL2 | Dashboard starts; pilot action is clearly blocked with setup guidance; no unsafe fallback |
| W-03 | WSL2 present, pinned source matches package | `GEO Pilot Baslat` runs exactly groups=1, CPU-only, train/val-select/val-calib; completes/validates `exercise.json` |
| W-04 | Double click pilot again during run | No second job; surfaces the existing job ID |
| W-05 | User cancels pilot | Only owned process tree is stopped; logs/artifacts preserved; state not `SUCCEEDED` |
| W-06 | WSL missing/mismatch/wrong revision/insufficient disk | Fail closed with actionable error, no generated production artifacts |
| W-07 | Close browser during active pilot | Job lifecycle managed explicitly; status recoverable; no spurious success |
| W-08 | Restart app after finished job, invalid/corrupt output | Status verified/recovered or marked `finished_unrecorded`; never fabricated success |
| W-09 | `--production`, GPU, LOKO, held-out or arbitrary argv attempts | Refused by the existing command-safety layers |
| W-10 | Click existing Track B desktop shortcut | RFML launches independently without Track A dependency |
| W-11 | GitHub CI package and physical Windows integration | Exact revision, clean ZIP checksum, source-version provenance, logs and test reports |
| W-12 | Gate inventory returns `BLOCKED` (exit 4) | Read-only command treated as successful inventory read but **no authority or launch granted** |

Track A `real-exercise` has a 5,400-second dashboard timeout by default. Preserve a finite bounded timeout; don't alter it to bypass caps. Never call time-elapsed / timeout a true percent-done progress metric.

## 6. Completion roadmap beyond this desktop integration

**Software completion / Release Candidate:** One-click launcher + bounded real-physics WSL2 pilot + success/cancellation/report lifecycle + Windows package + exact-head green tests and tested user install. This can be completed without a GPU or production gate changes.

**Scientific completion / GEO Benchmark:** Requires separately: designated host(s), independently verified persistent backup, qualified GPU and resources, explicit DR-04 data generation grant (21,350 observations, 739 shards), authorized bounded GPU probe and DR-05 training, 9 canonical + 6 matched fits, frozen scorer/calibrators, one separately permitted held-out evaluation with required sensitivity rows, and results integrated into the GEO manuscript only after measured evidence. Earlier 23.0–30.2h generation and width-16 9-fit 10–22h screening figures are extrapolations, **not a promise** for the user's Windows PC.

There is **no reliable basis** to claim all full-scale scientific work will finish within a three-day clock using the current single-process generator and unspecified Windows hardware. Separate software release completion from scientific validation.

## 7. Required Claude delivery artifacts and reporting format

- Implement the work, do not stop at another architectural plan. Reuse existing code first; add files only where necessary.
- Before edits, inventory repository, clean state, base SHA, relevant GitHub Actions and existing tests.
- Keep a concise dated implementation diary under `docs/plan/DURUM.md`; distinguish evidence from proposals.
- Submit focused PRs rather than unreviewed main commits. Save/push each *tested* milestone so work is resumable; no force-push, no overwriting main, no fabricated CI results.
- Provide in final handoff: exact commit(s), PR link(s), exact test commands and pass/fail/skips, real Windows/WSL evidence (or plainly say not tested on a physical PC), install/launch/stop steps, screenshot(s) if available, ZIP/artifact reference plus SHA256, which one-click workflow is genuinely working, and still-closed compute/scientific gates.
- Do not silently change the frozen science contract or promote `benchmark_complete`. The final criterion is a **working one-click bounded research workbench**, not a claimed completed production benchmark.

## 8. Short execution instruction for Claude

> Use this document as the acceptance contract. Work from the latest `main`, preserve the current user-installed Windows package and its two-track isolation, implement the smallest safe WSL2-backed one-click GEO pilot workflow, add end-to-end verification, update the installer/docs/CI, push tested milestones and open reviewable PR(s). No production/GPU/LOKO/held-out bypass; give concrete working output and exact evidence rather than another plan.
