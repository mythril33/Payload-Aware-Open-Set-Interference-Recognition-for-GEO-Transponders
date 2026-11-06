"""Scripted stand-in for wsl.exe, used by tests/test_windows_oneclick_fakewsl.py (stdlib only).

geo_workbench.ps1 and setup_wsl_backend.ps1 take ``-WslExe windows\\tests\\fake_wsl.cmd``; that wrapper
runs this file. Nothing here starts a real WSL distribution or any program: every call is answered from
the scenario JSON named by ``GEO_FAKE_WSL_SCENARIO`` and appended as one JSON line to the log file
(``GEO_FAKE_WSL_LOG``, else ``"log"`` in the scenario, else ``<scenario>.log``).

Emulated forms:

* ``-l -v`` -> ``scenario["list"]`` (text) with exit ``scenario.get("list_exit", 0)``;
* ``--status`` -> exit ``scenario.get("status_exit", 0)``;
* ``-d D [-u U] [--cd X] --exec PROG ARGS...`` -> the response keyed by
  ``<subcommand>`` for ``.../dashboard/geo_pilot.py <subcommand>`` (preflight, run, status, cancel,
  serve, ui-status, ui-stop), ``setup:<subcommand>`` for ``.../geo_wsl_setup.py <subcommand>``, and
  otherwise ``exec:<prog basename> <args...>`` falling back to ``exec:<prog basename>``;
* anything else (``--install ...``) -> key ``wsl:<first argument>``.

A response is ``{"exit": int, "stdout": str | object, "stderr": str, "sleep": seconds}``; an object
``stdout`` is printed as one JSON line. ``"after_run"`` replaces the response once a ``run`` call has
been logged; ``"sequence"`` (a list of responses) picks the n-th by the number of earlier calls with the
same key (the last one repeats). An unknown key exits 127.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PILOT_SCRIPT = "geo_pilot.py"
SETUP_SCRIPT = "geo_wsl_setup.py"
DEFAULT_LIST = "  NAME            STATE           VERSION\n* Ubuntu-24.04    Running         2\n"


def _basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def parse(argv: list[str]) -> dict:
    call: dict = {"argv": argv, "distro": None, "user": None, "cd": None, "exec": None, "args": []}
    if argv in (["-l", "-v"], ["--list", "--verbose"]):
        call["key"] = "list"
        return call
    if argv == ["--status"]:
        call["key"] = "status-wsl"
        return call
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "-d" and i + 1 < len(argv):
            call["distro"] = argv[i + 1]
            i += 2
        elif token == "-u" and i + 1 < len(argv):
            call["user"] = argv[i + 1]
            i += 2
        elif token == "--cd" and i + 1 < len(argv):
            call["cd"] = argv[i + 1]
            i += 2
        elif token == "--exec" and i + 1 < len(argv):
            call["exec"] = argv[i + 1]
            call["args"] = argv[i + 2:]
            break
        else:
            break
    if call["exec"] is None:
        call["key"] = "wsl:" + (argv[0] if argv else "")
        return call
    args = call["args"]
    names = [_basename(a) for a in args]
    if PILOT_SCRIPT in names:
        at = names.index(PILOT_SCRIPT)
        call["key"] = args[at + 1] if at + 1 < len(args) else "pilot:"
    elif SETUP_SCRIPT in names:
        at = names.index(SETUP_SCRIPT)
        call["key"] = "setup:" + (args[at + 1] if at + 1 < len(args) else "")
    else:
        call["key"] = "exec:" + " ".join([_basename(call["exec"]), *args])
        call["fallback_key"] = "exec:" + _basename(call["exec"])
    return call


def _read_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    calls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            calls.append(json.loads(line))
        except ValueError:
            continue
    return calls


def respond(call: dict, scenario: dict, earlier: list[dict]) -> dict:
    if call["key"] == "list":
        return {"exit": scenario.get("list_exit", 0), "stdout": scenario.get("list", DEFAULT_LIST)}
    if call["key"] == "status-wsl":
        return {"exit": scenario.get("status_exit", 0)}
    commands = scenario.get("commands", {})
    key = call["key"]
    if key not in commands and call.get("fallback_key") in commands:
        key = call["fallback_key"]
    if key not in commands:
        return {"exit": 127, "stderr": f"fake wsl: no scenario response for {call['key']!r}"}
    response = commands[key]
    if "after_run" in response and any(c.get("key") == "run" for c in earlier):
        response = response["after_run"]
    if "sequence" in response:
        sequence = response["sequence"]
        seen = sum(1 for c in earlier if c.get("key") == call["key"])
        response = sequence[min(seen, len(sequence) - 1)]
    return response


def main(argv: list[str]) -> int:
    scenario_path = os.environ.get("GEO_FAKE_WSL_SCENARIO")
    if not scenario_path:
        print("fake wsl: GEO_FAKE_WSL_SCENARIO is not set", file=sys.stderr)
        return 126
    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    log = Path(os.environ.get("GEO_FAKE_WSL_LOG") or scenario.get("log") or scenario_path + ".log")
    call = parse(argv)
    earlier = _read_log(log)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({k: v for k, v in call.items() if k != "fallback_key"}, ensure_ascii=True) + "\n")
    response = respond(call, scenario, earlier)
    if response.get("sleep"):
        time.sleep(float(response["sleep"]))
    stdout = response.get("stdout")
    if stdout is not None:
        text = stdout if isinstance(stdout, str) else json.dumps(stdout, ensure_ascii=True, allow_nan=False)
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        sys.stdout.flush()
    if response.get("stderr"):
        sys.stderr.write(str(response["stderr"]) + "\n")
    return int(response.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
