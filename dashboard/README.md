# Local research dashboard

A local Streamlit application for understanding and inspecting this repository. It is for research use on your own computer.

**What it does**

- **Dashboard**: repository version, commit, environment readiness, execution gates, evidence counts.
- **RF Explorer**: simulator-generated spectra, co- and cross-polarization observations, carrier plans and cancellation residuals, with units on every plot. Development roles only.
- **Development runner**: starts a fixed list of bounded, CPU-only commands and shows progress, logs, errors and outputs.
- **Model analysis**: confusion matrices, ROC curves, FPR at 95 % TPR, AUROC, training history and calibration, when they are stored in a result record.
- **Experiment browser**: each record labelled as verified historical, development pilot, unexecuted, gate or approval, or restricted.
- **System diagnostics**: Python and package versions, CPU, memory, storage, GPU presence, test results and provenance checks.
- **Setup guide**: this page.

**What it does not do**

- It has **no production launch control**. No production, GPU, LOKO or held-out evaluation can be started from it.
- It does not change any committed result, gate or protocol. Generated files go outside the repository.
- It does not show held-out observation values. Restricted files are listed, and their values are never displayed.

## Native Windows

The dashboard runs natively on Windows 10/11 with Python 3.12, without WSL2 and without administrator rights. The "Windows package CI" workflow runs the test suite on `windows-latest`.

- **Runs natively**: every page (Dashboard, RF Explorer, Development runner, Model analysis, Experiment browser, System diagnostics, Setup guide), and the runner commands `preflight-gates`, `host-inventory`, `test-dashboard` and `test-cpu-execution`.
- **Does not run natively**: the runner command `real-exercise`. Its governed script chain uses POSIX-only file locks (`fcntl`), so on native Windows the runner shows it as unavailable, with that reason, and refuses to start it. To run it on a Windows machine, use the WSL2 guide below, which remains the full-functionality path.
- For a guided native-Windows install with launcher scripts, see the Turkish quick start `windows/BENIOKU.md`.

## 1. Requirements

- Windows 10 (version 2004 or later) or Windows 11. Administrator rights are needed only for the WSL2 route below (the first `wsl --install`); the native Windows route above does not need them.
- About 20 GB of free disk space and 16 GB of RAM. The memory and disk actually available are shown on the System diagnostics page.
- A 4-core CPU is enough. No GPU is needed or used.

## 2. Install WSL2 with Ubuntu (Windows)

1. Open **PowerShell as administrator** and run:

   ```powershell
   wsl --install -d Ubuntu-24.04
   ```

2. Restart Windows when asked. After the restart, Ubuntu opens and asks you for a Linux user name and password. Choose them and remember them.
3. Check that the distribution runs WSL 2:

   ```powershell
   wsl -l -v
   ```

   The Ubuntu line should show `VERSION 2`.

## 3. Prepare Ubuntu

Open the **Ubuntu** app from the Start menu and run:

```bash
sudo apt update
sudo apt install -y git python3.12 python3.12-venv
python3.12 --version
```

Python 3.12 is the version the repository's continuous integration uses.

**Keep the repository on the Linux file system** (your Ubuntu home folder, `~`), not under `/mnt/c`. Files under `/mnt/c` are much slower.

## 4. Get the repository and create a virtual environment

```bash
cd ~
git clone https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders.git
cd Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Your prompt now starts with `(.venv)`. Every later command assumes this environment is active. If you open a new Ubuntu window, run `source .venv/bin/activate` again.

## 5. Install the packages

Install the repository and its machine-learning extra. The development runner needs PyTorch from the `ml` extra:

```bash
python -m pip install -e ".[dev,ml]"
```

`scripts/setup_cloud.sh` installs PyTorch 2.14.1 for CPU first, from the PyTorch CPU index, and falls back to the PyPI build. If the install of `torch` is very large or slow, use the same approach as that script.

Then install the dashboard's own requirement (Streamlit, pinned in `dashboard/requirements.txt`):

```bash
python -m pip install -r dashboard/requirements.txt
```

The pin is Streamlit 1.65.0, which was released on 2026-10-02. The repository keeps its dependency pins at least two weeks old. Optional: `.[xgb]` needs Python 3.12 and is only needed for the XGBoost baseline scripts, not for the dashboard.

## 6. Start the dashboard

From the repository folder, with `(.venv)` active:

```bash
python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Open **http://localhost:8501** in your Windows browser. WSL 2 forwards `localhost` automatically. Keep the Ubuntu window open while you use the dashboard. Press `Ctrl+C` in that window to stop it.

Good first steps:

1. **Dashboard**: check that the gates say no compute or production gate is open.
2. **System diagnostics**: click **Run dashboard tests**. It should report that all dashboard tests passed.
3. **RF Explorer**: choose a development group and click **Simulate this scene**. The first run takes about 5 to 10 seconds.
4. **Development runner**: optional. Start **Bounded real RF to train to calibrate to freeze exercise** with 1 group. It runs on your CPU and writes its output outside the repository. Its duration depends on your machine, so the page shows the elapsed time and the stage it has reached.

## 7. Where outputs go

Outputs go to a **run folder outside the repository**:

- default: `~/.local/share/geo-dashboard`
- to change it, set the environment variable before launching: `export GEO_DASHBOARD_HOME=/path/to/a/folder`

Each job has its own folder with `log.txt`, `job.json` and its outputs. Nothing in the run folder is committed to Git. The dashboard refuses any location inside the repository.

## 8. Safety limits you should know about

- Only the commands listed in the Development runner can start. You cannot type a command, a path or a flag.
- One job runs at a time. The dashboard stops any job that exceeds its time limit, and it can cancel a job.
- Only the dashboard process that started a job can record its outcome. If that process stops before the job ends, the job keeps running; any dashboard started later shows it as running until the job's output or exit status settles it. If the owning process has gone and the job ended with its outputs verified, the dashboard reports it as `finished_unrecorded`, because the exit status was not recorded. It is never reported as a success with exit status zero, and it is never reported as a failure when its outputs are valid.
- The development runner uses only the `train`, `val-select` and `val-calib` roles. The RF Explorer refuses test and matched groups before any simulation runs.
- Progress shown by the runner is inferred from the files a job writes. The scripts print no progress bar, and the dashboard says so.

## 9. Troubleshooting

| Symptom | What to do |
|---|---|
| `ModuleNotFoundError: No module named 'scipy'` or `streamlit` | Run `source .venv/bin/activate`, then the install commands in section 5. |
| `Address already in use` | Use another port, for example `--server.port 8502`. |
| The runner is disabled or says `torch` is missing | Install the `ml` extra (section 5). The dashboard itself still works. |
| A simulation or job takes a long time | This is expected on CPU. Watch the elapsed time, and cancel with the button if needed. |
| Memory errors | Close other programs, and choose 1 group in the runner. |
| The browser page does not open | Check the Ubuntu window for the message `Local URL`, and open that address. |
| Diagnostics show a record as `STALE` | The record was generated from different source. Do not edit it. Re-derive it through its own script, or report it. |

## 10. Tests

The dashboard has its own tests (`tests/test_dashboard_*.py`). They use synthetic fixtures and the simulator, and they never open held-out values. Run them from the dashboard's **System diagnostics** page, or from the repository folder with:

```bash
python -m pytest -q tests/test_dashboard_commands.py tests/test_dashboard_jobs.py tests/test_dashboard_portable.py tests/test_dashboard_results.py tests/test_dashboard_evidence.py tests/test_dashboard_rf.py tests/test_dashboard_diagnostics.py tests/test_dashboard_app.py
```
