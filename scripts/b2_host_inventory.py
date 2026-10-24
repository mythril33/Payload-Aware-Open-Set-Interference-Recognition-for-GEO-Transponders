"""Read-only hardware/environment inventory for the B2/1 production hosts (E8, P32).

    python scripts/b2_host_inventory.py --role generation --path /data/b2 --backup-path /mnt/backup
    python scripts/b2_host_inventory.py --role training --path /data/b2 --out host_inventory.json

Describes only the machine it runs on and compares it with the PROPOSED, unapproved resource figures of the E5
plan (``b2_production_preflight.PROPOSED_CEILINGS``). It writes nothing but the optional ``--out`` report (created
exclusively), creates no scratch file, imports neither torch nor CUDA, starts no GPU kernel and runs at most one
fixed ``nvidia-smi --query-gpu`` driver query. A missing GPU is BLOCKED (a host or hardware decision), a measured
shortfall is FAIL, and PASS only means "this machine meets the proposed figure". It designates no host, authorizes
nothing and never reports ``benchmark_complete=true``. Each disk row also names the filesystem type of its mount, and the
report carries the node name and the collection time (E13), so a later reader can tell a volatile or foreign report from a
real one; all of it is still the reporting process's own claim. It lives in ``scripts/`` because every ``src/**/*.py`` is
hashed into checkpoint provenance and the production lock.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b2_production_preflight as pre  # noqa: E402

SCHEMA = "B2-host-inventory/1"
PASS, FAIL, BLOCKED, NOT_RUN = pre.PASS, pre.FAIL, pre.BLOCKED, pre.NOT_RUN
ROLES = ("generation", "training")
LIBRARIES = ("torch", "numpy", "scipy", "xgboost-cpu")
THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "CUDA_VISIBLE_DEVICES", "PYTHONHASHSEED")
GPU_QUERY = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"]
GPU_QUERY_TIMEOUT_S = 10
# Proposed (UNAPPROVED) per-role figures: the E5 plan numbers, plus the E5 "comparable 4-CPU host" for generation.
REQUIREMENTS = {
    "generation": {"logical_cpus": 4, "ram_gib": pre.PROPOSED_CEILINGS["host_ram_gib_generation"],
                   "working_disk_gib": pre.PROPOSED_CEILINGS["working_disk_gib"],
                   "backup_disk_gb": pre.PROPOSED_CEILINGS["backup_disk_gb"]},
    "training": {"logical_cpus": 2, "ram_gib": pre.PROPOSED_CEILINGS["host_ram_gib_training"],
                 "working_disk_gib": pre.PROPOSED_CEILINGS["working_disk_gib"],
                 "gpu_vram_gib_minimum": pre.PROPOSED_CEILINGS["gpu_vram_gib_minimum"],
                 "gpu_vram_gib_preferred": pre.PROPOSED_CEILINGS["gpu_vram_gib_preferred"]},
}


def _read(path):
    try:
        return Path(path).read_text()
    except (OSError, UnicodeDecodeError):
        return None


def cpu_facts(read=_read, cpu_count=os.cpu_count):
    affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    model = next((line.split(":", 1)[1].strip() for line in (read("/proc/cpuinfo") or "").splitlines()
                  if line.startswith("model name")), None)
    quota = None
    fields = (read("/sys/fs/cgroup/cpu.max") or "").split()
    if len(fields) == 2 and fields[0] != "max":
        try:
            quota = round(int(fields[0]) / int(fields[1]), 2)
        except (ValueError, ZeroDivisionError):
            quota = None
    return {"logical_cpus": cpu_count(), "schedulable_cpus": affinity, "model": model, "cgroup_cpu_quota": quota}


def memory_facts(read=_read):
    values = {}
    for line in (read("/proc/meminfo") or "").splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            values[key] = round(int(rest.split()[0]) / 2 ** 20, 2)
    limit = (read("/sys/fs/cgroup/memory.max") or "").strip()
    return {"total_gib": values.get("MemTotal"), "available_gib": values.get("MemAvailable"),
            "cgroup_limit_gib": round(int(limit) / 2 ** 30, 2) if limit.isdigit() else None}


def fstype_of(path, read=_read):
    """Filesystem type of the mount that holds ``path`` (longest mount-point prefix in /proc/self/mountinfo), or None."""
    try:
        real = os.path.realpath(path)
    except (OSError, ValueError):
        return None
    best = None
    for line in (read("/proc/self/mountinfo") or "").splitlines():
        left, _, right = line.partition(" - ")
        fields = left.split()
        if len(fields) < 5 or not right.split():
            continue
        mount = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), fields[4])
        if (mount == "/" or real == mount or real.startswith(mount.rstrip("/") + "/")) and (best is None or len(mount) >= len(best[0])):
            best = (mount, right.split()[0])
    return best[1].strip().lower() if best else None


def disk_facts(paths, disk_usage=shutil.disk_usage):
    """stat-only: an existing ancestor of each path is queried; nothing is created."""
    rows = []
    for raw in paths:
        target = Path(raw)
        while not target.exists() and target != target.parent:
            target = target.parent
        usage = disk_usage(target)
        rows.append({"path": str(raw), "queried": str(target), "device": os.stat(target).st_dev,
                     "fstype": fstype_of(target), "total_gib": round(usage.total / 2 ** 30, 2),
                     "free_gib": round(usage.free / 2 ** 30, 2)})
    return rows


def gpu_facts(which=shutil.which, run=subprocess.run, glob=lambda: sorted(p.name for p in Path("/dev").glob("nvidia*"))):
    """Driver query only. No CUDA runtime, no torch, no kernel."""
    devices, note = [], None
    tool = which(GPU_QUERY[0])
    if tool is None:
        note = "nvidia-smi is not installed or not on PATH"
    else:
        try:
            done = run([tool, *GPU_QUERY[1:]], capture_output=True, text=True, timeout=GPU_QUERY_TIMEOUT_S, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            done, note = None, f"nvidia-smi could not be run: {type(error).__name__}"
        if done is not None and done.returncode != 0:
            note = f"nvidia-smi exited {done.returncode}"
        elif done is not None:
            for line in done.stdout.strip().splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) == 4:
                    try:
                        devices.append({"name": parts[0], "memory_gib": round(float(parts[1]) / 1024, 2),
                                        "driver": parts[2], "compute_capability": parts[3]})
                    except ValueError:
                        note = "unparseable nvidia-smi line"
    return {"devices": devices, "device_nodes": glob(), "note": note}


def library_facts(version=metadata.version, distributions=metadata.distributions):
    """Package metadata only (no import). pip's torch version drops the local ``+cuXXX`` tag, so CUDA support is judged by
    the NVIDIA runtime wheels that a CUDA torch build pulls in; whether the build can reach a GPU is the probe's question."""
    out = {}
    for name in LIBRARIES:
        try:
            out[name] = version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    names = {str(item.metadata["Name"]).lower() for item in distributions() if item.metadata["Name"]}
    out["nvidia_runtime_wheels"] = sorted(name for name in names if name.startswith("nvidia-"))
    return out


def collect(paths, backup_path=None, *, facts=None):
    facts = facts or {}
    return {"platform": platform.platform(), "python": platform.python_version(), "node": platform.node(),
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cpu": facts.get("cpu") or cpu_facts(), "memory": facts.get("memory") or memory_facts(),
            "disks": facts.get("disks") or disk_facts(paths + ([backup_path] if backup_path else [])),
            "gpu": facts.get("gpu") or gpu_facts(), "libraries": facts.get("libraries") or library_facts(),
            "environment": {name: os.environ.get(name) for name in THREAD_ENV}}


def evaluate(role, inventory, paths, backup_path=None):
    """Checks of one role against the proposed figures; every PASS is only 'meets the proposal'."""
    need = REQUIREMENTS[role]
    cpu, mem, disks, gpu = inventory["cpu"], inventory["memory"], inventory["disks"], inventory["gpu"]
    usable = min(value for value in (cpu["logical_cpus"], cpu["schedulable_cpus"], cpu["cgroup_cpu_quota"]) if value is not None)
    ram = min(value for value in (mem["available_gib"], mem["cgroup_limit_gib"]) if value is not None) \
        if mem["available_gib"] is not None else None
    checks = [pre.check("host.cpu", "CPU capacity", PASS if usable >= need["logical_cpus"] else FAIL,
                        f"{usable} usable CPUs (logical {cpu['logical_cpus']}, schedulable {cpu['schedulable_cpus']}, "
                        f"cgroup quota {cpu['cgroup_cpu_quota']}) versus the proposed {need['logical_cpus']}"),
              pre.check("host.ram", "Available RAM", NOT_RUN if ram is None else PASS if ram >= need["ram_gib"] else FAIL,
                        "MemAvailable unreadable" if ram is None else
                        f"{ram} GiB available (cgroup limit {mem['cgroup_limit_gib']}) versus the proposed {need['ram_gib']} GiB")]
    work = [row for row in disks if row["path"] in map(str, paths)]
    for row in work:
        checks.append(pre.check("host.working_disk", f"Free space for {row['path']}",
                                PASS if row["free_gib"] >= need["working_disk_gib"] else FAIL,
                                f"{row['free_gib']} GiB free (queried {row['queried']}) versus the proposed {need['working_disk_gib']} GiB"))
    if not work:
        checks.append(pre.check("host.working_disk", "Free space for the working root", BLOCKED, "no --path was given; the working root is undesignated"))
    if "backup_disk_gb" in need:
        backup = next((row for row in disks if backup_path and row["path"] == str(backup_path)), None)
        if backup is None:
            checks.append(pre.check("host.backup", "Separate verified backup target", BLOCKED,
                                    "no --backup-path was given; the backup target is undesignated"))
        else:
            same = any(row["device"] == backup["device"] for row in work)
            enough = backup["free_gib"] * 2 ** 30 / 1e9 >= need["backup_disk_gb"]
            checks.append(pre.check("host.backup", "Separate verified backup target", FAIL if same or not enough else PASS,
                                    f"{backup['free_gib']} GiB free; "
                                    + ("the same device as the working root" if same else "a different device")
                                    + f"; proposed {need['backup_disk_gb']} GB"))
    if role == "training":
        if not gpu["devices"]:
            checks.append(pre.check("host.gpu", "GPU for the bounded probe and the nine fits", BLOCKED,
                                    "no NVIDIA GPU is visible (" + (gpu["note"] or "no device reported") + "); training numbers stay assumptions"))
        else:
            best = max(device["memory_gib"] for device in gpu["devices"])
            checks.append(pre.check("host.gpu", "GPU memory", PASS if best >= need["gpu_vram_gib_minimum"] else FAIL,
                                    f"{best} GiB largest device versus the proposed {need['gpu_vram_gib_minimum']} GiB minimum "
                                    f"({need['gpu_vram_gib_preferred']} GiB preferred); VRAM here is hardware size, not a measured peak"))
        wheels = inventory["libraries"]["nvidia_runtime_wheels"]
        checks.append(pre.check("host.torch_cuda_runtime", "CUDA runtime wheels next to torch", PASS if wheels else BLOCKED,
                                f"torch {inventory['libraries']['torch']}; {len(wheels)} nvidia-* runtime wheels installed. Metadata only: "
                                "whether this build reaches a GPU is decided by the authorized probe, not here"))
    checks.append(pre.check("host.designation", "Host designated by the researcher", BLOCKED,
                            "no host is designated or authorized; this report describes the machine it ran on"))
    return checks


def build_report(role, paths, backup_path=None, *, facts=None):
    inventory = collect(paths, backup_path, facts=facts)
    checks = evaluate(role, inventory, paths, backup_path)
    return {"schema": SCHEMA, "role": role, "read_only": True, "gpu_computation_performed": False, "host_designated": False,
            "requirements_status": "PROPOSED_UNAPPROVED", "requirements": REQUIREMENTS[role], "inventory": inventory,
            "benchmark_complete": False, "production_authorized": False, **pre.verdict(checks), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--path", action="append", default=[], help="working root(s) to size (existing ancestor is queried)")
    parser.add_argument("--backup-path")
    parser.add_argument("--out", help="write the report here (exclusive creation)")
    parser.add_argument("--allow-blocked", action="store_true", help="exit 0 when the worst status is BLOCKED")
    args = parser.parse_args(argv)
    report = build_report(args.role, args.path, args.backup_path)
    text = json.dumps(report, indent=1, allow_nan=False) + "\n"
    if args.out:
        try:
            with open(args.out, "x") as stream:
                stream.write(text)
        except FileExistsError:
            print(f"{args.out} already exists; refusing to overwrite evidence", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(text)
    return pre._exit_code(report, args.allow_blocked)


if __name__ == "__main__":
    raise SystemExit(main())
