# Windows one-click GEO workbench — test report

Scope: the implementation of [docs/plan/WINDOWS_ONE_CLICK_COMPLETION.md](../plan/WINDOWS_ONE_CLICK_COMPLETION.md)
on branch `claude/windows-one-click-workbench`, PR
[#64](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/64),
base `main` `2d9f5a0bf3d5c9885651dc674ddf55a26acc00a5`. Dated 2026-11-05.

This is software evidence. A bounded pilot proves the functional generate → train → calibrate →
freeze → backup flow on CPU for the three development roles; it is not a recognition-performance
result and not the 21,350-observation benchmark. `benchmark_complete=false`. No production, GPU,
LOKO or held-out path was added or run.

## 1. Evidence classes used below

| Label | Meaning |
|---|---|
| **WIN-CI** | Executed on a real GitHub `windows-latest` runner (Windows Server, PS 5.1 and 7). |
| **LINUX-REAL** | Genuine execution of the WSL-side backend on Linux (the same userland WSL2 Ubuntu runs): real RF generation, training, calibration and freeze, no mocks. |
| **UNIT** | Automated tests with injected processes or fakes. |
| **NOT RUN** | Not executed yet; the reason is stated. |
| **EXTERNAL** | Requires a physical Windows 10/11 PC (or qualified VM) with WSL2 virtualization. GitHub-hosted runners cannot run WSL2. |

## 2. Genuine bounded pilot runs (LINUX-REAL)

All runs: `real-exercise`, one group per role (train, val-select, val-calib), CPU only, started
through `dashboard/geo_pilot.py run` (the supervisor the desktop shortcut uses), run folder outside
the checkout.

| Job | Source | Result | Notes |
|---|---|---|---|
| `20261105T080108-d9a906` | Git checkout at `3a14021` | **succeeded**, exit 0, 150 s | A second `run` while it ran exited **10** and printed the running `JOB_ID` (W-04). |
| `20261105T080447-c09612` | Git checkout at `3a14021` | **cancelled** at ~45 s by `geo_pilot.py cancel`; supervisor exit 31 | journal, anchors, generator log, `job.json`, `log.txt`, `pilot.json` all preserved (W-05). |
| `20261105T080537-a840e9` | verified package snapshot (manifest) at `3a14021` | **failed**, exit 1 | RF generation succeeded; training stopped at `src/geoml/experiment.py:103` (`git rev-parse HEAD` for checkpoint provenance). Root cause of the switch to a Git bundle (§4). |
| `20261105T090036-6d7822` | Git checkout cloned from the package's `geo-source.bundle` at `dc1774a` | **succeeded**, exit 0, 154 s | 24 observations, generator 143.6 s, peak RSS 0.57 GiB; `pilot.json` verified, observed boundary: `heldout_reads=0`, `gpu_exercised=false`, `production_authorized=false`, `benchmark_complete=false`. |

Tampering one governed file in an installed tree made preflight refuse with **20** (W-06).

## 3. Acceptance matrix (W-01 … W-12)

| ID | Evidence | Status |
|---|---|---|
| W-01 installer, two venvs, shortcuts | WIN-CI run 41992475401 (`91f3589`): non-interactive `install.ps1` created `.venv-dashboard` and `.venv-rfml` with CPU torch and the exact shortcut set with Turkish names (after the IShellLinkW fix, `cdbaec1`). | **PASS on `91f3589`** |
| W-02 no WSL2 | WIN-CI run 41992475401: pilot action exits fail-closed with *GEO WSL Kurulumu* guidance; native inspection dashboard healthy. | **PASS on `91f3589`** |
| W-03 genuine pilot in WSL2 | LINUX-REAL job `20261105T090036-6d7822` (bundle clone, groups=1, CPU, dev roles). | **PASS on Linux; EXTERNAL on WSL2** |
| W-04 double click | LINUX-REAL (exit 10 + `JOB_ID`); UNIT; fake-WSL launcher test (Windows only). | **PASS (Linux)**; Windows launcher path NOT RUN (§5) |
| W-05 cancel | LINUX-REAL job `20261105T080447-c09612`; UNIT (ownership tokens, SIGTERM/SIGHUP). | **PASS (Linux)** |
| W-06 missing WSL / mismatch / wrong revision / disk | LINUX-REAL tamper → 20; UNIT 20/23/25; WIN-CI no-backend exit. | **PASS (partial)**; mismatch launcher path NOT RUN (§5) |
| W-07 browser closed during pilot | UNIT: the supervisor owns the job independently of the UI; serve keeps the WSL instance alive while a pilot runs. | **UNIT only**; EXTERNAL on WSL2 |
| W-08 restart, corrupt output | UNIT: unreadable `job.json` → `record_unreadable` and blocks new starts (19); corrupt `exercise.json` → failed; dead owner → `finished_unrecorded`/failed. | **PASS (UNIT)** |
| W-09 forbidden argv | UNIT through the real registry and argv guard. | **PASS** |
| W-10 Track B | WIN-CI run 41992475401: Track B launcher healthy and stopped; `launch_rfml.bat` pinned by sha256. | **PASS on `91f3589`** |
| W-11 package provenance | Builder self-verify on `dc1774a` (manifest, bundle sha256, `list-heads`); CI artifact for `dc1774a` NOT RUN (§5). | **PASS locally**; CI NOT RUN |
| W-12 BLOCKED inventory | UNIT (`preflight-gates`/`host-inventory` exit 4 = closed gates, authorizes nothing). | **PASS** |

## 4. Defects found and fixed during this work

1. Shortcut names lost Turkish letters on a cp1252 system: WScript.Shell maps the .lnk path through
   the ANSI code page (WIN-CI run 41991245483). Fixed with IShellLinkW (`windows/geo_shortcut.ps1`)
   plus a non-ASCII round-trip test.
2. A pilot cannot run from a manifest snapshot (training needs Git provenance). Fixed by shipping a
   full-history `git bundle` and installing a genuine checkout (`install-git`); a bundle from a
   shallow repository clones into a repository with a missing parent commit, so the builder
   refuses shallow sources. Preflight reports a verified non-Git source as 25.
3. Twenty-eight adversarial-review findings (five lenses) were triaged; the real ones were fixed
   (identity pinning on every start path, any running job blocks a start, SIGHUP-safe cancel,
   deadline enforcement with an unreadable record, localized WSL state parsing, consented
   `git`/`python3-venv` installs, root-user refusal, `wsl --install` exit codes, and more).
4. Pre-existing on `main`: two PR #61 result documents were missing from the dashboard evidence map.

## 5. CI status and what is not yet verified

- `91f3589`: both Windows jobs green (run 41992475401). Readiness: 5,120 passed, 1 failed — the
  helper harness's COM shortcut test ran under Linux `pwsh`; fixed in `a14ff3e`.
- `dc1774a` (round-2 fixes): GitHub Actions assigned **no runner** to any job (`runner_id: 0`,
  no steps, no log; the one allowed re-run behaved the same). The round-2 PowerShell changes
  (bundle setup, mismatch fallback, fake-WSL launcher tests, CI from the extracted package under
  a path with a space and Turkish letters) have therefore **not run on Windows yet**. Restoring
  Actions capacity (account billing/spending limit) and re-running is the required next step.
- Local on `dc1774a`: 627 passed, 14 skipped (Windows/PowerShell-only), E18 workflow lint clean.

## 6. External physical-PC validation (required, not done)

On Windows 10 22H2+/11 with virtualization enabled, from the extracted package:
1. `KURULUM.bat`; confirm the five GEO shortcuts plus *RF-ML Ogrenme Uygulamasi*.
2. *GEO WSL Kurulumu*: consent prompts, Ubuntu user creation, `install-git`, venv, final preflight.
3. *GEO Workbench*: header shows *WSL2 Ubuntu*, the package commit (verified), Benchmark INCOMPLETE.
4. *GEO Pilot Başlat*: job id shown; a second click shows the same job id; the run ends
   `succeeded` in a few minutes with `exercise.json` and `pilot.json` downloadable.
5. Start another pilot and use *GEO İşlem Durdur*: state `cancelled`, outputs preserved.
6. *GEO Workbench Kapat* with and without a running pilot; reopen and confirm status recovery.
7. Collect `windows\logs\*.log` and `%LOCALAPPDATA%\GEO-Workbench\wsl_backend.json`.
