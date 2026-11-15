"""Command-line backend of the one-click GEO workbench (run inside WSL2 or Linux; importable on Windows).

    python dashboard/geo_pilot.py preflight [--groups N] [--expect-commit SHA] [--expect-manifest-sha256 HEX] [--json]
    python dashboard/geo_pilot.py run [--groups N] [--expect-commit SHA] [--expect-manifest-sha256 HEX]
    python dashboard/geo_pilot.py status [--job ID] [--json]
    python dashboard/geo_pilot.py cancel [--job ID]
    python dashboard/geo_pilot.py serve --port P [--expect-commit SHA] [--expect-manifest-sha256 HEX]
    python dashboard/geo_pilot.py ui-stop
    python dashboard/geo_pilot.py ui-status [--json]

JSON goes to stdout as one strict ASCII line. Exit codes are listed in geodash/pilot.py. Whenever a job is
running, the text output of preflight and run names it as ``JOB_ID=<id>``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from geodash import jobs as J  # noqa: E402
from geodash import pilot as P  # noqa: E402
from geodash.paths import ensure_import_paths  # noqa: E402


def _print(line: str) -> None:
    print(line, flush=True)


def _expect_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expect-commit", default=None)
    parser.add_argument("--expect-manifest-sha256", default=None)


def _identity_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--groups", type=int, default=1)
    _expect_args(parser)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="geo_pilot.py", description="Bounded one-click GEO pilot backend.")
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight", help="check engine, source, dependencies, disk and running jobs")
    _identity_args(preflight)
    preflight.add_argument("--json", action="store_true")
    run = sub.add_parser("run", help="start the bounded pilot and supervise it until it ends")
    _identity_args(run)
    status = sub.add_parser("status", help="state of the latest (or the named) pilot")
    status.add_argument("--job", default=None)
    status.add_argument("--json", action="store_true")
    cancel = sub.add_parser("cancel", help="cancel the running pilot")
    cancel.add_argument("--job", default=None)
    serve = sub.add_parser("serve", help="serve the dashboard on 127.0.0.1")
    serve.add_argument("--port", type=int, required=True)
    _expect_args(serve)
    sub.add_parser("ui-stop", help="stop the dashboard started by serve")
    ui_status = sub.add_parser("ui-status", help="whether serve is running")
    ui_status.add_argument("--json", action="store_true")
    return parser


def _preflight(args) -> int:
    report = P.preflight(args.groups, args.expect_commit, args.expect_manifest_sha256)
    if args.json:
        _print(P.dumps(report))
    else:
        source = report["source"]
        if report["running_job"] is not None:
            _print(f"JOB_ID={report['running_job']}")
        _print(f"engine: {report['engine']['label']}")
        _print(f"source: {source['mode']} {source['commit'] or '-'} verified={source['verified']}")
        for code, reason in zip(report["codes"], report["reasons"]):
            _print(f"{code}: {reason}")
        _print(f"exit {report['exit_code']}")
    return report["exit_code"]


def _status(args) -> int:
    manager = J.JobManager(P.run_home())
    if args.job is not None:
        try:
            status = manager.status(args.job)
        except J.UnknownJobError:
            status = None
        if status is not None and status.key not in (P.PILOT_KEY, ""):
            status = None
    else:
        status = P.latest_pilot(manager)
    if status is None:
        if args.json:
            _print(P.dumps({"found": False, "job_id": args.job, "state": None}))
        else:
            _print("NO_PILOT")
        return P.EXIT_NONE
    report = {"found": True, **P.pilot_status_dict(status)}
    if args.json:
        _print(P.dumps(report))
    else:
        _print(f"JOB_ID={report['job_id']} state={report['state']} stage={report['stage'] or '-'} "
               f"verified={report['verified']}")
        _print(f"reason: {report['reason']}")
        _print(f"folder: {report['job_dir']}")
    return P.EXIT_OK


def _ui_status(args) -> int:
    report = P.ui_status()
    _print(P.dumps(report) if args.json else f"{report['state']} port={report['port']}")
    return P.EXIT_OK if report["running"] else P.EXIT_NONE


def main(argv: list[str] | None = None) -> int:
    ensure_import_paths()
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        return _preflight(args)
    if args.command == "run":
        return P.run_pilot(args.groups, args.expect_commit, args.expect_manifest_sha256, out=_print)
    if args.command == "status":
        return _status(args)
    if args.command == "cancel":
        return P.cancel_pilot(args.job, out=_print)
    if args.command == "serve":
        return P.serve(args.port, out=_print, expect_commit=args.expect_commit,
                       expect_manifest_sha256=args.expect_manifest_sha256)
    if args.command == "ui-stop":
        return P.ui_stop(out=_print)
    return _ui_status(args)


if __name__ == "__main__":
    sys.exit(main())
