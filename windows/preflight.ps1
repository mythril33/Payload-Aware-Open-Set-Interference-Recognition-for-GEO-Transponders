# preflight.ps1 - standalone diagnostic for the Payload-Aware GEO Workbench.
# Checks Python, RAM, disk, internet and virtual environment presence without
# installing or changing anything. ASCII-transliterated Turkish output.
# Exit code: 0 when no hard problem was found, 1 otherwise.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$HardProblems = 0

function Write-Ok    ($m) { Write-Host ("[OK]    " + $m) -ForegroundColor Green }
function Write-Uyari ($m) { Write-Host ("[UYARI] " + $m) -ForegroundColor Yellow }
function Write-Hata  ($m) { Write-Host ("[HATA]  " + $m) -ForegroundColor Red }

Write-Host '--- Payload-Aware GEO Workbench on kontrol (preflight) ---'
Write-Host ("Depo koku: " + $RepoRoot)
Write-Host ''

# Python 3.10 - 3.13
function Test-PythonVersion {
    param([string]$Exe, [string[]]$ExtraArgs)
    try {
        $out = & $Exe @ExtraArgs -c "import sys; print('{0}.{1}'.format(sys.version_info[0], sys.version_info[1]))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $v = ("$out" -split "`n" | Select-Object -Last 1).Trim()
        $parts = $v.Split('.')
        if ($parts.Count -lt 2) { return $null }
        $maj = [int]$parts[0]; $min = [int]$parts[1]
        if ($maj -eq 3 -and $min -ge 10 -and $min -le 13) {
            return [pscustomobject]@{ Exe = $Exe; ExtraArgs = $ExtraArgs; Version = $v }
        }
        return $null
    } catch { return $null }
}

$py = $null
$candidates = @(
    @{ Exe = 'py';     ExtraArgs = @('-3.12') },
    @{ Exe = 'py';     ExtraArgs = @('-3.13') },
    @{ Exe = 'py';     ExtraArgs = @('-3.11') },
    @{ Exe = 'py';     ExtraArgs = @('-3.10') },
    @{ Exe = 'py';     ExtraArgs = @('-3') },
    @{ Exe = 'python'; ExtraArgs = @() }
)
foreach ($c in $candidates) {
    if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
    $py = Test-PythonVersion -Exe $c.Exe -ExtraArgs $c.ExtraArgs
    if ($py) { break }
}
if ($py) {
    Write-Ok ("Python: " + $py.Exe + " " + ($py.ExtraArgs -join ' ') + " (surum " + $py.Version + ")")
} else {
    Write-Hata 'Uygun Python yok (gerekli: 3.10 - 3.13). https://www.python.org/downloads/ veya: winget install --id Python.Python.3.12 --scope user'
    $HardProblems++
}

# RAM
try {
    $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    if ($ramGB -lt 8) { Write-Uyari ("RAM: " + $ramGB + " GB (8 GB onerilir).") }
    else { Write-Ok ("RAM: " + $ramGB + " GB") }
} catch { Write-Uyari 'RAM miktari okunamadi.' }

# Disk
try {
    $driveRoot = [System.IO.Path]::GetPathRoot($RepoRoot)
    $drive = New-Object System.IO.DriveInfo($driveRoot)
    $freeGB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    if ($freeGB -lt 5) { Write-Hata ("Bos disk: " + $freeGB + " GB (en az 5 GB gerekir)."); $HardProblems++ }
    elseif ($freeGB -lt 10) { Write-Uyari ("Bos disk: " + $freeGB + " GB (10 GB onerilir).") }
    else { Write-Ok ("Bos disk: " + $freeGB + " GB (" + $driveRoot + ")") }
} catch { Write-Uyari 'Disk alani okunamadi.' }

# Internet
$internetOk = $false
try {
    $resp = Invoke-WebRequest -Uri 'https://pypi.org/simple/' -Method Head -TimeoutSec 15 -UseBasicParsing
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { $internetOk = $true }
} catch { }
if ($internetOk) { Write-Ok 'Internet (pypi.org) erisilebilir.' }
else { Write-Uyari 'pypi.org erisilemedi. Kurulum icin internet gerekir; calistirmak icin gerekmez.' }

# Venv presence
foreach ($venv in @('.venv-dashboard', '.venv-rfml')) {
    $vpy = Join-Path $RepoRoot ($venv + '\Scripts\python.exe')
    if (Test-Path $vpy) { Write-Ok ($venv + ' mevcut.') }
    else { Write-Uyari ($venv + ' yok. KURULUM.bat ile kurulum yapin.') }
}

Write-Host ''
if ($HardProblems -eq 0) {
    Write-Ok 'On kontrol tamamlandi; engelleyici sorun bulunamadi.'
    exit 0
} else {
    Write-Hata ("On kontrol " + $HardProblems + " engelleyici sorun buldu (yukaridaki [HATA] satirlari).")
    exit 1
}
