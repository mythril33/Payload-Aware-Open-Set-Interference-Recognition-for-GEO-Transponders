"""Assemble the complete results bundle: paper, figures, data, results, code.

Writes release/rfml-openset-benchmark.zip and release/MANIFEST.sha256. The zip
holds everything needed to read, check and rerun the study:

    paper/        paper.pdf, LaTeX source, bibliography, generated numbers, figures
    experiments/  the three analysis plans, runners, per-seed results, aggregates,
                  the raw per-frame scores of every seed, and the data of seed 0
    rfml/ tests/ lessons/ app.py setup.sh setup.ps1 requirements.txt   the code

Raw scores and the exported dataset are not in Git (the repository keeps
generated data out); this bundle is where they are delivered. The bundle is
refused if a campaign aggregate is missing or records a failure.

Usage:  .venv/bin/python experiments/make_bundle.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release"
NAME = "rfml-openset-benchmark"
CAMPAIGNS = ("campaign", "campaign_rep", "campaign2", "campaign2_rep", "campaign3")
FIXED_TIME = (2026, 11, 9, 0, 0, 0)  # constant timestamps: the same inputs give the same zip

INCLUDE_FILES = ("README.md", "requirements.txt", "setup.sh", "setup.ps1", "pytest.ini", "app.py")
INCLUDE_DIRS = ("rfml", "tests", "lessons", "paper", "experiments", "results")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "release"}
SKIP_SUFFIXES = {".pyc", ".aux", ".log", ".blg", ".out"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect() -> list[Path]:
    files = [ROOT / name for name in INCLUDE_FILES if (ROOT / name).exists()]
    for folder in INCLUDE_DIRS:
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file():
                continue
            if SKIP_PARTS & set(path.relative_to(ROOT).parts) or path.suffix in SKIP_SUFFIXES:
                continue
            files.append(path)
    return sorted(set(files))


def main() -> int:
    for name in CAMPAIGNS:
        aggregate = ROOT / "experiments" / name / "aggregate.json"
        if not aggregate.exists():
            sys.exit(f"missing {aggregate}: run the campaigns first")
        if json.loads(aggregate.read_text())["failures"]:
            sys.exit(f"{aggregate} records failures; refusing to bundle")
    for required in ("paper/paper.pdf", "experiments/dataset_seed0/MANIFEST.json"):
        if not (ROOT / required).exists():
            sys.exit(f"missing {required}: build the paper and export the dataset first")

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"

    files = collect()
    manifest_lines = []
    OUT.mkdir(exist_ok=True)
    zip_path = OUT / f"{NAME}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            manifest_lines.append(f"{sha256(data)}  {rel}")
            info = zipfile.ZipInfo(f"{NAME}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
        readme = (
            f"# {NAME}\n\n"
            f"Source commit: {commit}\n\n"
            "Contents: paper/ (paper.pdf, LaTeX source, figures, generated numbers), experiments/\n"
            "(analysis plans, runners, per-seed results, aggregates, raw per-frame scores under\n"
            "campaign*/raw/, the open-set data of seed 0 under dataset_seed0/), and the code.\n\n"
            "Check the files:   sha256sum -c MANIFEST.sha256   (run inside this folder)\n"
            "Rebuild the paper: sh paper/build.sh              (needs the .venv and LaTeX)\n"
            "Rerun a campaign:  see experiments/README.md\n\n"
            "All data are synthetic (rfml/signals.py). Nothing here was measured.\n"
        )
        manifest = "\n".join(manifest_lines) + "\n"
        for rel, text in (("BUNDLE_README.md", readme), ("MANIFEST.sha256", manifest)):
            info = zipfile.ZipInfo(f"{NAME}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, text)

    (OUT / "MANIFEST.sha256").write_text(manifest)
    digest = sha256(zip_path.read_bytes())
    (OUT / f"{NAME}.zip.sha256").write_text(f"{digest}  {NAME}.zip\n")
    size_mb = zip_path.stat().st_size / 1e6
    print(f"wrote {zip_path} ({len(files)} files, {size_mb:.1f} MB)\nsha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
