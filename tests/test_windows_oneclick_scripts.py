"""Static and (where PowerShell exists) executed checks of the one-click Windows workbench scripts.

Runs on Linux and Windows. Linux has no PowerShell, so the scripts are checked as text: CRLF .bat
wrappers, ASCII-only .ps1, forbidden constructs and labels, consent-gated elevation, WSL calls only
through ``--exec``, Track B isolation and the documented exit-code table. On a machine with
``powershell``/``pwsh`` the PowerShell parser and the dependency-free helper harness also run.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WIN = ROOT / "windows"
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import pilot as P  # noqa: E402

PS1_FILES = sorted(WIN.glob("*.ps1")) + sorted((WIN / "tests").glob("*.ps1"))
BAT_FILES = sorted(WIN.glob("*.bat"))
GEO_FILES = [WIN / "geo_common.ps1", WIN / "geo_workbench.ps1", WIN / "setup_wsl_backend.ps1",
             WIN / "tests" / "geo_common_tests.ps1"] + sorted(WIN.glob("GEO_*.bat"))
FAKE_WSL_CMD = WIN / "tests" / "fake_wsl.cmd"
FAKE_WSL_PY = WIN / "tests" / "fake_wsl.py"
# sha256 of windows/launch_rfml.bat as committed (Track B launcher, must stay byte-identical).
LAUNCH_RFML_SHA256 = "0ab4cd775038e50fbebb680d0b9f4b45ca651c00eec0c9731a4e456c0caa64df"

BAT_TARGETS = {
    "GEO_Workbench.bat": ("geo_workbench.ps1", "-Action open"),
    "GEO_Pilot_Baslat.bat": ("geo_workbench.ps1", "-Action pilot -Groups 1"),
    "GEO_Islem_Durdur.bat": ("geo_workbench.ps1", "-Action stop-pilot"),
    "GEO_Workbench_Kapat.bat": ("geo_workbench.ps1", "-Action close"),
    "GEO_WSL_Kurulumu.bat": ("setup_wsl_backend.ps1", ""),
}
SHORTCUT_NAMES = {
    "GEO Workbench",
    "GEO Pilot Ba\u015flat",
    "GEO \u0130\u015flem Durdur",
    "GEO Workbench Kapat",
    "GEO WSL Kurulumu",
    "RF-ML Ogrenme Uygulamasi",
    "Uygulamalari Durdur",
}
REQUIRED_CODES = {0, 2, 3, 5, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 30, 31, 32, 33, 34,
                  40, 41, 42}
FORBIDDEN_CONSTRUCTS = ("set-executionpolicy", "invoke-expression", " iex ", "downloadstring", "curl ", "wget ")
FORBIDDEN_LABELS = ("--production", "cuda", "loko", "test-matched", "--roles", "21,350", "full benchmark",
                    "complete research")
POWERSHELL_LINE = re.compile(r'^powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0([^"\\]+\.ps1)"(.*)$')


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def mask_powershell(text: str) -> str:
    """The code of a PowerShell script with comments and string literals blanked (newlines kept)."""
    out = list(text)
    n = len(text)

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        c = text[i]
        if text.startswith("<#", i):
            j = text.find("#>", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            blank(i, j + 1)
            i = j + 1
        elif c == '"':
            j, depth = i + 1, 0
            while j < n:
                ch = text[j]
                if ch == "`":
                    j += 2
                    continue
                if ch == "$" and text.startswith("$(", j):
                    depth += 1
                    j += 2
                    continue
                if depth and ch == "(":
                    depth += 1
                elif depth and ch == ")":
                    depth -= 1
                elif ch == '"' and depth == 0:
                    break
                j += 1
            blank(i, j + 1)
            i = j + 1
        elif c == "`":
            i += 2
        else:
            i += 1
    return "".join(out)


def _matching_brace(code: str, open_at: int) -> int:
    depth = 0
    for k in range(open_at, len(code)):
        if code[k] == "{":
            depth += 1
        elif code[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    raise AssertionError("unbalanced braces")


def functions(code: str) -> dict:
    """name -> (start, end) offsets of each function body in masked code."""
    spans = {}
    for match in re.finditer(r"(?im)^[ \t]*function\s+([\w-]+)", code):
        open_at = code.index("{", match.end())
        spans[match.group(1)] = (match.start(), _matching_brace(code, open_at))
    return spans


def enclosing_function(spans: dict, offset: int):
    inside = [(end - start, name) for name, (start, end) in spans.items() if start <= offset <= end]
    return min(inside)[1] if inside else None


def validate_set(code_text: str, param: str) -> list:
    match = re.search(r"\[ValidateSet\(([^)]*)\)\]\s*\[\w+\]\s*\$" + param + r"\b", code_text)
    assert match, f"no ValidateSet for -{param}"
    return re.findall(r"'([^']*)'", match.group(1))


def powershell_exes() -> list:
    return [exe for exe in (shutil.which("powershell"), shutil.which("pwsh")) if exe]


# ---- .bat wrappers --------------------------------------------------------------------------------

def test_expected_wrappers_exist():
    for name in BAT_TARGETS:
        assert (WIN / name).is_file(), name


@pytest.mark.parametrize("bat", BAT_FILES, ids=lambda p: p.name)
def test_bat_is_crlf_and_calls_powershell_safely(bat):
    raw = bat.read_bytes()
    assert raw.endswith(b"\r\n")
    assert raw.count(b"\n") == raw.count(b"\r\n"), "LF without CR"
    assert raw.count(b"\r") == raw.count(b"\r\n"), "CR without LF"
    raw.decode("ascii")
    calls = [line for line in raw.decode("ascii").split("\r\n") if "powershell" in line.lower()]
    assert calls, "wrapper does not call PowerShell"
    for line in calls:
        match = POWERSHELL_LINE.match(line)
        assert match, line
        assert (WIN / match.group(1)).is_file(), match.group(1)


@pytest.mark.parametrize("bat", BAT_FILES, ids=lambda p: p.name)
def test_bat_targets_valid_parameters(bat):
    workbench = mask_powershell(_text(WIN / "geo_workbench.ps1"))
    actions = validate_set(_text(WIN / "geo_workbench.ps1"), "Action")
    apps = validate_set(_text(WIN / "launch_app.ps1"), "App")
    assert workbench
    for line in bat.read_bytes().decode("ascii").split("\r\n"):
        match = POWERSHELL_LINE.match(line)
        if not match:
            continue
        target, rest = match.group(1), match.group(2)
        if target == "geo_workbench.ps1":
            action = re.search(r"-Action (\S+)", rest)
            assert action and action.group(1) in actions, line
            groups = re.search(r"-Groups (\S+)", rest)
            assert groups is None or groups.group(1) in ("1", "2"), line
        elif target == "launch_app.ps1":
            app = re.search(r"-App (\S+)", rest)
            assert app and app.group(1) in apps, line
        else:
            assert "-Action" not in rest, line
        if bat.name in BAT_TARGETS:
            assert (target, rest.strip()) == BAT_TARGETS[bat.name]


# ---- .ps1 hygiene ----------------------------------------------------------------------------------

@pytest.mark.parametrize("ps1", PS1_FILES, ids=lambda p: p.name)
def test_ps1_is_ascii_and_balanced(ps1):
    raw = ps1.read_bytes()
    assert all(b < 128 for b in raw), "non-ASCII byte (Windows PowerShell 5.1 reads BOM-less files as ANSI)"
    code = mask_powershell(raw.decode("ascii"))
    pairs = {"}": "{", ")": "(", "]": "["}
    stack = []
    for k, ch in enumerate(code):
        if ch in "{([":
            stack.append(ch)
        elif ch in pairs:
            assert stack and stack[-1] == pairs[ch], f"unbalanced {ch!r} at offset {k}"
            stack.pop()
    assert not stack, f"unclosed {stack}"


@pytest.mark.parametrize("path", PS1_FILES + BAT_FILES, ids=lambda p: p.name)
def test_no_forbidden_constructs_or_labels(path):
    lowered = _text(path).lower()
    for token in FORBIDDEN_CONSTRUCTS + FORBIDDEN_LABELS:
        assert token not in lowered, token


def test_elevation_only_in_consent_gated_wsl_install():
    hits = 0
    for ps1 in PS1_FILES:
        text = _text(ps1)
        code = mask_powershell(text)
        for match in re.finditer(r"(?i)-Verb\s+RunAs", code):
            hits += 1
            assert ps1.name == "setup_wsl_backend.ps1", ps1.name
            spans = functions(code)
            name = enclosing_function(spans, match.start())
            assert name is not None, "elevation outside a function"
            start, _ = spans[name]
            assert re.search(r"(?i)\bRead-Host\b", code[start:match.start()]), "no Read-Host consent before RunAs"
            assert "--install" in text[start:spans[name][1]]
    assert hits >= 1


def test_wsl_is_only_invoked_through_exec():
    allowed_call = {"Get-WslDistros", "Test-WslStatus", "Invoke-WslExec"}
    allowed_start = {"Start-WslHidden", "Install-WslWithConsent", "Install-AptPackageWithConsent"}
    common = mask_powershell(_text(WIN / "geo_common.ps1"))
    spans = functions(common)
    start, end = spans["New-WslArgv"]
    assert "'--exec'" in _text(WIN / "geo_common.ps1")[start:end]
    for name in ("Invoke-WslExec", "Start-WslHidden"):
        assert "New-WslArgv" in common[spans[name][0]:spans[name][1]], name
    for ps1 in PS1_FILES:
        text = _text(ps1)
        code = mask_powershell(text)
        if ps1 in GEO_FILES:
            assert "bash" not in text.lower(), ps1.name
        assert not re.search(r"(?i)(&|Start-Process)\s+(-FilePath\s+)?['\"]?wsl(\.exe)?\b", text), ps1.name
        fspans = functions(code)
        for match in re.finditer(r"&\s*\$(\w+)", code):
            if "wsl" in match.group(1).lower():
                assert enclosing_function(fspans, match.start()) in allowed_call, (ps1.name, match.group(0))
        for match in re.finditer(r"(?i)Start-Process\s+-FilePath\s+\$(\w+)", code):
            if "wsl" in match.group(1).lower():
                owner = enclosing_function(fspans, match.start())
                assert owner in allowed_start, (ps1.name, owner)
                if owner != "Install-WslWithConsent":
                    assert "New-WslArgv" in code[fspans[owner][0]:fspans[owner][1]], owner


def test_geo_actions_never_kill_processes_directly():
    for path in (WIN / "geo_workbench.ps1", WIN / "setup_wsl_backend.ps1", WIN / "geo_common.ps1"):
        code = mask_powershell(_text(path))
        assert "Stop-Process" not in code, path.name
        spans = functions(code)
        for match in re.finditer(r"(?i)taskkill", code):
            assert enclosing_function(spans, match.start()) == "Stop-NativeDashboard", path.name


def test_stop_apps_never_touches_the_geo_pilot():
    text = _text(WIN / "stop_apps.ps1").lower()
    for token in ("geo_ui.pid", "geo_pilot.pid", "wsl"):
        assert token not in text, token


def test_track_b_isolation():
    for path in GEO_FILES + [FAKE_WSL_CMD, FAKE_WSL_PY]:
        lowered = _text(path).lower()
        for token in ("rfml", "learning"):
            assert token not in lowered, (path.name, token)


def test_launch_rfml_is_byte_identical_to_the_pinned_track_b_launcher():
    assert hashlib.sha256((WIN / "launch_rfml.bat").read_bytes()).hexdigest() == LAUNCH_RFML_SHA256


# ---- parameters, shortcuts, installer ------------------------------------------------------------

def test_workbench_parameter_sets():
    text = _text(WIN / "geo_workbench.ps1")
    assert validate_set(text, "Action") == ["open", "pilot", "stop-pilot", "close", "status"]
    assert validate_set(text, "Groups") == ["1", "2"]
    assert re.search(r"\[switch\]\$NoBrowser", text)
    assert re.search(r"\[int\]\$Groups = 1\b", text)


def test_launch_app_no_browser_switch_keeps_default():
    text = _text(WIN / "launch_app.ps1")
    assert re.search(r"\[switch\]\$NoBrowser", text)
    opens = [line for line in text.splitlines() if 'Start-Process ("http://127.0.0.1:"' in line]
    assert len(opens) == 2
    assert all("if (-not $NoBrowser)" in line for line in opens)


def _shortcut_names(text: str) -> set:
    chars = {name: chr(int(code, 16)) for name, code in
             re.findall(r"\$(\w+)\s*=\s*\[char\]0x([0-9A-Fa-f]{4})", text)}
    names = set()
    for quote, value in re.findall(r"\bName\s*=\s*(['\"])(.*?)\1", text):
        if quote == '"':
            value = re.sub(r"\$\((?:\$)?(\w+)\)", lambda m: chars[m.group(1)], value)
        names.add(value)
    names.update(re.findall(r"New-Shortcut\s+-LnkPath\s+\(Join-Path\s+\$\w+\s+'([^']+)\.lnk'\)", text))
    return names


def test_installer_shortcut_names_match_contract():
    text = _text(WIN / "install.ps1")
    assert _shortcut_names(text) == SHORTCUT_NAMES
    for bat in re.findall(r"\bBat\s*=\s*'([^']+)'", text):
        assert (WIN / bat).is_file(), bat
    assert not re.search(r"New-Shortcut[^\n]*GEO Arastirma Panosu", text)
    assert "Remove-OldGeoShortcut -LnkPath (Join-Path $folder 'GEO Arastirma Panosu.lnk')" in text
    assert re.search(r"New-Shortcut[^\n]*'RF-ML Ogrenme Uygulamasi\.lnk'[^\n]*'launch_rfml\.bat'", text)


def test_installer_prompts_only_when_python_is_missing():
    code = mask_powershell(_text(WIN / "install.ps1"))
    block = code.index("if (-not $py) {")
    end = _matching_brace(code, code.index("{", block))
    prompts = [m.start() for m in re.finditer(r"(?i)\bRead-Host\b", code)]
    assert prompts
    assert all(block < offset < end for offset in prompts)


# ---- exit codes and messages ---------------------------------------------------------------------

def _message_codes() -> set:
    text = _text(WIN / "geo_common.ps1")
    code = mask_powershell(text)
    start, end = functions(code)["Get-PilotMessage"]
    return {int(c) for c in re.findall(r"(?m)^\s*(\d+)\s*\{", code[start:end])}


def test_message_table_covers_every_documented_code():
    codes = _message_codes()
    assert REQUIRED_CODES <= codes
    backend = {value for name, value in vars(P).items() if name.startswith("EXIT_") and isinstance(value, int)}
    assert backend | set(P.FINAL_EXIT.values()) | set(P.PREFLIGHT_CODES.values()) <= codes
    spec = importlib.util.spec_from_file_location("geo_wsl_setup_for_scripts", WIN / "wsl" / "geo_wsl_setup.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    assert set(setup.CODE_NAMES) <= codes


# ---- package / WSL identity, setup, pid files -----------------------------------------------------

def _function_text(path: Path, name: str) -> str:
    text = _text(path)
    start, end = functions(mask_powershell(text))[name]
    return text[start:end + 1]


def test_backend_expectation_gates_open_and_pilot_but_not_stop_or_close():
    get_backend = _function_text(WIN / "geo_workbench.ps1", "Get-Backend")
    assert "Resolve-BackendExpectation" in get_backend and "'mismatch'" in get_backend
    assert "Status -eq 'mismatch') { return 20 }" in _function_text(WIN / "geo_workbench.ps1", "Get-BackendProblemCode")
    for name in ("Invoke-OpenAction", "Invoke-PilotAction"):
        assert "$backend.Status -ne 'ok'" in _function_text(WIN / "geo_workbench.ps1", name), name
    for name in ("Invoke-StopPilotAction", "Invoke-CloseAction", "Invoke-StatusAction"):
        assert "Test-BackendUsable" in _function_text(WIN / "geo_workbench.ps1", name), name


def test_serve_preflight_and_run_carry_the_expected_commit():
    ui = _function_text(WIN / "geo_workbench.ps1", "Start-WorkbenchUi")
    assert re.search(r"'serve', '--port', \[string\]\$port\) \+ \(Get-ExpectArgs -Commit \$Backend\.ExpectCommit\)", ui)
    assert ui.count("Test-UiIdentity") == 2
    pilot = _function_text(WIN / "geo_workbench.ps1", "Invoke-PilotAction")
    assert "$expectArgs = Get-ExpectArgs -Commit $backend.ExpectCommit" in pilot
    assert "@('preflight', '--groups', [string]$Groups) + $expectArgs + @('--json')" in pilot
    assert "@($backend.Script, 'run', '--groups', [string]$Groups) + $expectArgs" in pilot
    assert "--expect-manifest-sha256" not in _text(WIN / "geo_workbench.ps1")


def test_job_id_is_printed_whenever_preflight_names_a_running_job():
    pilot = _function_text(WIN / "geo_workbench.ps1", "Invoke-PilotAction")
    assert pilot.index("Write-RunningJob $report") < pilot.index("if ($pre.ExitCode -eq 10)")
    assert "JOB_ID=" in _function_text(WIN / "geo_workbench.ps1", "Write-RunningJob")


def test_pid_file_writes_are_guarded():
    text = _text(WIN / "geo_workbench.ps1")
    code = mask_powershell(text)
    spans = functions(code)
    for pattern in (r"WriteAllText", r"Write-PidRecord\s"):
        for match in re.finditer(pattern, code):
            assert enclosing_function(spans, match.start()) in ("Write-UiPidRecord", "Write-PilotPidFile"), pattern
    for name in ("Write-UiPidRecord", "Write-PilotPidFile"):
        body = _function_text(WIN / "geo_workbench.ps1", name)
        assert "try {" in body and "catch {" in body, name


def test_wsl_list_parsing_keeps_multi_word_states():
    body = _function_text(WIN / "geo_common.ps1", "ConvertFrom-WslListText")
    assert "Name    = $tokens[0]" in body
    assert "($tokens[1..($tokens.Count - 2)]) -join ' '" in body


def test_setup_clones_the_git_bundle_and_never_copies_a_snapshot():
    text = _text(WIN / "setup_wsl_backend.ps1")
    assert "'install-git', '--bundle', $bundleWsl, '--commit', $version.Commit, '--to', $dest" in text
    assert "'install', '--from'" not in text
    assert "Get-FileHash -LiteralPath $bundleFile -Algorithm SHA256" in text
    assert "$version.SourceBundleHead -cne $version.Commit" in text
    assert "--expect-manifest-sha256" not in text


def test_setup_installs_git_only_with_consent_and_retries_once():
    setup = _function_text(WIN / "setup_wsl_backend.ps1", "Invoke-Setup")
    block = setup[setup.index("if ($install.ExitCode -eq 17)"):]
    block = block[:block.index("$result = ConvertFrom-PilotJson")]
    assert "Install-AptPackageWithConsent -WslPath $wsl -Name $name -Package 'git' -Code 17" in block
    assert block.count("Invoke-SetupPy") == 1
    apt = _function_text(WIN / "setup_wsl_backend.ps1", "Install-AptPackageWithConsent")
    assert apt.index("Read-Consent") < apt.index("Start-Process")
    assert "-WindowStyle Hidden" not in apt


def test_setup_refuses_root_and_records_the_linux_user():
    setup = _function_text(WIN / "setup_wsl_backend.ps1", "Invoke-Setup")
    assert "if ($linux.Uid -eq 0) {" in setup
    assert setup.index("if ($linux.Uid -eq 0) {") < setup.index("'install-git'")
    for key in ("linux_user      = $linux.User", "uid             = $linux.Uid", "source_mode     = 'git'"):
        assert key in setup, key
    state = _function_text(WIN / "geo_common.ps1", "Test-BackendState")
    assert "linux_user" in state and "$user -eq 'root'" in state and "'^[1-9][0-9]{0,9}$'" in state


def test_setup_stops_a_running_ui_with_consent_before_replacing():
    setup = _function_text(WIN / "setup_wsl_backend.ps1", "Invoke-Setup")
    assert setup.index("Stop-OldUiWithConsent") < setup.index("'--replace'")
    stop = _function_text(WIN / "setup_wsl_backend.ps1", "Stop-OldUiWithConsent")
    assert stop.index("Read-Consent") < stop.index("'ui-stop'")


def test_wsl_install_counts_only_0_and_3010_as_started():
    body = _function_text(WIN / "setup_wsl_backend.ps1", "Install-WslWithConsent")
    assert "($code -eq 0 -or $code -eq 3010)" in body
    assert "$null -ne $code" in body
    assert body.rstrip().endswith("return 1\n}") or body.rstrip().endswith("return 1\r\n}")
    assert body.index('"exit"') < body.index("Start-Process")


# ---- fake WSL harness (runs everywhere; the PowerShell side runs in test_windows_oneclick_fakewsl.py) --

def _fake_module():
    spec = importlib.util.spec_from_file_location("fake_wsl_for_scripts", FAKE_WSL_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fake_wsl_cmd_is_crlf_ascii_and_runs_the_python_fake():
    raw = FAKE_WSL_CMD.read_bytes()
    assert raw.endswith(b"\r\n") and raw.count(b"\n") == raw.count(b"\r\n")
    text = raw.decode("ascii")
    assert text.startswith("@echo off\r\n")
    assert '"%~dp0fake_wsl.py" %*' in text
    assert text.rstrip().endswith("exit /b %ERRORLEVEL%")


def test_fake_wsl_parses_every_emulated_form():
    fake = _fake_module()
    py = "/home/u/geo-workbench-src/.venv/bin/python"
    assert fake.parse(["-l", "-v"])["key"] == "list"
    for sub in ("preflight", "run", "status", "cancel", "serve", "ui-status", "ui-stop"):
        call = fake.parse(["-d", "Ubuntu", "--cd", "/home/u/geo-workbench-src", "--exec", py,
                           "/home/u/geo-workbench-src/dashboard/geo_pilot.py", sub, "--json"])
        assert call["key"] == sub and call["distro"] == "Ubuntu" and call["exec"] == py
    call = fake.parse(["-d", "Ubuntu", "--cd", "~", "--exec", "python3", "/mnt/c/p q/windows/wsl/geo_wsl_setup.py",
                       "install-git", "--json"])
    assert call["key"] == "setup:install-git"
    call = fake.parse(["-d", "Ubuntu", "-u", "root", "--exec", "id", "-u"])
    assert call["key"] == "exec:id -u" and call["fallback_key"] == "exec:id" and call["user"] == "root"
    assert fake.parse(["--install", "-d", "Ubuntu-24.04"])["key"] == "wsl:--install"


def test_fake_wsl_answers_from_the_scenario_and_logs_every_call(tmp_path):
    scenario = {"commands": {
        "status": {"exit": 3, "stdout": {"found": False}, "after_run": {"exit": 0, "stdout": {"found": True}}},
        "setup:install-git": {"sequence": [{"exit": 17, "stdout": "missing"}, {"exit": 0, "stdout": "ok"}]},
        "run": {"exit": 0}}}
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    log = tmp_path / "calls.log"
    env = {"GEO_FAKE_WSL_SCENARIO": str(path), "GEO_FAKE_WSL_LOG": str(log), "PATH": ""}
    pilot = ["-d", "U", "--cd", "/s", "--exec", "/s/.venv/bin/python", "/s/dashboard/geo_pilot.py"]
    setup = ["-d", "U", "--cd", "~", "--exec", "python3", "/p/windows/wsl/geo_wsl_setup.py", "install-git"]

    def fake(*argv):
        return subprocess.run([sys.executable, str(FAKE_WSL_PY), *argv], env=env, capture_output=True, text=True,
                              timeout=60)

    done = fake("-l", "-v")
    assert done.returncode == 0 and "Ubuntu-24.04" in done.stdout
    done = fake(*pilot, "status", "--json")
    assert done.returncode == 3 and json.loads(done.stdout) == {"found": False}
    assert fake(*pilot, "run", "--groups", "1").returncode == 0
    done = fake(*pilot, "status", "--json")
    assert done.returncode == 0 and json.loads(done.stdout) == {"found": True}
    assert [fake(*setup).returncode for _ in range(3)] == [17, 0, 0]
    assert fake(*pilot, "serve", "--port", "8531").returncode == 127
    keys = [json.loads(line)["key"] for line in log.read_text(encoding="utf-8").splitlines()]
    assert keys == ["list", "status", "run", "status", "setup:install-git", "setup:install-git",
                    "setup:install-git", "serve"]


# ---- documentation -------------------------------------------------------------------------------

def test_benioku_documents_the_workbench():
    text = _text(WIN / "BENIOKU.md")
    for name in SHORTCUT_NAMES:
        assert name in text, name
    for code in sorted(REQUIRED_CODES - {0}):
        assert re.search(rf"(?m)^\| [^|]*\b{code}\b[^|]*\|", text), f"exit code {code} missing from the table"
    for needle in ("WSL2", "GEO WSL Kurulumu", "inceleme modu", "geo_workbench.log", "windows\\logs",
                   "~/.local/share/geo-dashboard", "benchmark değildir", "wsl_backend.json", "geo-source.bundle",
                   "sudo apt-get install -y git", "linux_user", "3010"):
        assert needle in text, needle


# ---- executed checks (Windows, or any machine with PowerShell) -------------------------------------

PARSE_SCRIPT = r"""
$bad = 0
foreach ($p in $args) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tokens, [ref]$errors)
    foreach ($e in $errors) { Write-Output ($p + ': ' + $e.Message); $bad++ }
}
exit $bad
"""


@pytest.mark.skipif(not powershell_exes(), reason="no powershell/pwsh on this machine")
@pytest.mark.parametrize("exe", powershell_exes() or ["-"])
def test_powershell_parses_every_script(exe, tmp_path):
    script = tmp_path / "parse.ps1"
    script.write_text(PARSE_SCRIPT, encoding="ascii")
    done = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                           *[str(p) for p in PS1_FILES]], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(not powershell_exes(), reason="no powershell/pwsh on this machine")
@pytest.mark.parametrize("exe", powershell_exes() or ["-"])
def test_geo_common_harness(exe):
    done = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(WIN / "tests" / "geo_common_tests.ps1")], capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    assert re.search(r"geo_common_tests: \d+ passed, 0 failed", done.stdout), done.stdout
