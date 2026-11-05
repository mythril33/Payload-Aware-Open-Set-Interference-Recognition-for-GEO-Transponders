"""Static and (where PowerShell exists) executed checks of the one-click Windows workbench scripts.

Runs on Linux and Windows. Linux has no PowerShell, so the scripts are checked as text: CRLF .bat
wrappers, ASCII-only .ps1, forbidden constructs and labels, consent-gated elevation, WSL calls only
through ``--exec``, Track B isolation and the documented exit-code table. On a machine with
``powershell``/``pwsh`` the PowerShell parser and the dependency-free helper harness also run.
"""
import importlib.util
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
REQUIRED_CODES = {0, 2, 3, 5, 10, 11, 12, 13, 14, 15, 16, 20, 21, 22, 23, 24, 30, 31, 32, 33, 34, 40, 41}
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
    allowed_start = {"Start-WslHidden", "Install-WslWithConsent", "Install-VenvPackageWithConsent"}
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
    for path in GEO_FILES:
        lowered = _text(path).lower()
        for token in ("rfml", "learning"):
            assert token not in lowered, (path.name, token)


def test_launch_rfml_unchanged_from_main():
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    done = subprocess.run(["git", "-C", str(ROOT), "show", "origin/main:windows/launch_rfml.bat"],
                          capture_output=True)
    if done.returncode != 0:
        pytest.skip("origin/main is not available in this checkout")
    assert (WIN / "launch_rfml.bat").read_bytes() == done.stdout


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


# ---- documentation -------------------------------------------------------------------------------

def test_benioku_documents_the_workbench():
    text = _text(WIN / "BENIOKU.md")
    for name in SHORTCUT_NAMES:
        assert name in text, name
    for needle in ("WSL2", "GEO WSL Kurulumu", "inceleme modu", "geo_workbench.log", "windows\\logs",
                   "~/.local/share/geo-dashboard", "benchmark değildir", "wsl_backend.json"):
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
