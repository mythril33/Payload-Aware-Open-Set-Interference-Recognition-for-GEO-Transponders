# install.ps1 - Payload-Aware GEO Workbench Windows installer (no admin rights).
#
# Creates the two SEPARATE virtual environments at the repository root
# (.venv-dashboard for Track A, .venv-rfml for Track B), installs each track's
# dependencies, runs import smoke tests and creates Desktop / Start Menu
# shortcuts. Console output is ASCII-transliterated Turkish so it survives any
# Windows codepage. Exit code: 0 on success, nonzero on hard failure.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$LogDir    = Join-Path $ScriptDir 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$Stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogPath = Join-Path $LogDir ("install-{0}.log" -f $Stamp)
Start-Transcript -Path $LogPath | Out-Null

function Write-Ok    ($m) { Write-Host ("[OK]    " + $m) -ForegroundColor Green }
function Write-Uyari ($m) { Write-Host ("[UYARI] " + $m) -ForegroundColor Yellow }
function Write-Hata  ($m) { Write-Host ("[HATA]  " + $m) -ForegroundColor Red }
function Write-Bilgi ($m) { Write-Host ("        " + $m) }

function Fail ($m) {
    Write-Hata $m
    Write-Hata ("Kurulum durduruldu. Ayrintili gunluk: " + $LogPath)
    Stop-Transcript | Out-Null
    exit 1
}

Write-Host '====================================================='
Write-Host ' Payload-Aware GEO Workbench - Windows kurulumu'
Write-Host ' Iki AYRI uygulama kurulur (asla birlestirilmez):'
Write-Host '   Iz A: GEO Arastirma Panosu   (.venv-dashboard)'
Write-Host '   Iz B: RF-ML Ogrenme Uygulamasi (.venv-rfml)'
Write-Host '====================================================='
Write-Bilgi ("Depo koku      : " + $RepoRoot)
Write-Bilgi ("Gunluk dosyasi : " + $LogPath)
Write-Host ''

# ---------------------------------------------------------------- Preflight
Write-Host '--- On kontrol ---'

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

function Find-Python {
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
        $r = Test-PythonVersion -Exe $c.Exe -ExtraArgs $c.ExtraArgs
        if ($r) { return $r }
    }
    return $null
}

# Disk space (hard floor 5 GB, warn below 10 GB)
try {
    $driveRoot = [System.IO.Path]::GetPathRoot($RepoRoot)
    $drive = New-Object System.IO.DriveInfo($driveRoot)
    $freeGB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    if ($freeGB -lt 5) {
        Fail ("Bos disk alani cok dusuk: " + $freeGB + " GB (" + $driveRoot + "). En az 5 GB gerekir; 10 GB onerilir.")
    } elseif ($freeGB -lt 10) {
        Write-Uyari ("Bos disk alani sinirli: " + $freeGB + " GB. 10 GB ve uzeri onerilir (PyTorch indirmesi buyuktur).")
    } else {
        Write-Ok ("Bos disk alani: " + $freeGB + " GB (" + $driveRoot + ")")
    }
} catch {
    Write-Uyari 'Bos disk alani okunamadi; devam ediliyor.'
}

# RAM (warn below 8 GB)
try {
    $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    if ($ramGB -lt 8) {
        Write-Uyari ("RAM: " + $ramGB + " GB. 8 GB altinda uygulamalar yavas calisabilir.")
    } else {
        Write-Ok ("RAM: " + $ramGB + " GB")
    }
} catch {
    Write-Uyari 'RAM miktari okunamadi; devam ediliyor.'
}

# Internet reachability (pip needs PyPI)
$internetOk = $false
try {
    $resp = Invoke-WebRequest -Uri 'https://pypi.org/simple/' -Method Head -TimeoutSec 15 -UseBasicParsing
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { $internetOk = $true }
} catch { }
if ($internetOk) {
    Write-Ok 'Internet erisimi dogrulandi (pypi.org).'
} else {
    Fail 'pypi.org adresine ulasilamadi. Internet baglantinizi ve varsa vekil sunucu (proxy) / SSL ayarlarinizi kontrol edin. Kurulum icin paket indirme erisimi sarttir.'
}

# Python detection (3.10 - 3.13; 3.12 preferred). Never installs silently.
$py = Find-Python
if (-not $py) {
    Write-Hata 'Uygun Python bulunamadi. Gerekli surum: 3.10, 3.11, 3.12 veya 3.13 (3.12 tercih edilir).'
    Write-Bilgi 'Secenek 1: https://www.python.org/downloads/ adresinden Python 3.12 indirin ve kurarken'
    Write-Bilgi '           "Add python.exe to PATH" kutusunu isaretleyin.'
    Write-Bilgi 'Secenek 2: Komut satirinda su komutu calistirin:'
    Write-Bilgi '           winget install --id Python.Python.3.12 --scope user'
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        $answer = Read-Host 'Python 3.12 simdi winget ile kurulsun mu? [E/H]'
        if ($answer -match '^[Ee]') {
            Write-Bilgi 'winget ile Python 3.12 kuruluyor (kullanici kapsami, yonetici gerekmez)...'
            & winget install --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { Fail 'winget ile Python kurulumu basarisiz oldu. Python 3.12 kurulumunu elle yapip KURULUM.bat dosyasini yeniden calistirin.' }
            # Refresh PATH for this session, then re-detect.
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
            $py = Find-Python
            if (-not $py) { Fail 'Python kuruldu ancak bu oturumda henuz bulunamadi. Bu pencereyi kapatip KURULUM.bat dosyasini yeniden calistirin.' }
        } else {
            Fail 'winget kurulumu onaylanmadi. Python 3.12 kurduktan sonra KURULUM.bat dosyasini yeniden calistirin.'
        }
    } else {
        Fail 'winget bulunamadi. Yukaridaki Secenek 1 ile Python 3.12 kurduktan sonra KURULUM.bat dosyasini yeniden calistirin.'
    }
}
$PythonExe  = $py.Exe
$PythonArgs = $py.ExtraArgs
Write-Ok ("Python bulundu: " + $PythonExe + " " + ($PythonArgs -join ' ') + " (surum " + $py.Version + ")")
if ($py.Version -ne '3.12') {
    Write-Uyari ("Tercih edilen surum 3.12; bulunan " + $py.Version + " de desteklenir.")
}

# ------------------------------------------------------------- Venv helpers
function Invoke-Pip {
    param([string]$VenvPython, [string[]]$PipArgs, [string]$Aciklama)
    Write-Bilgi ("pip: " + $Aciklama)
    & $VenvPython -m pip @PipArgs
    if ($LASTEXITCODE -ne 0) { return $false }
    return $true
}

function New-Venv {
    param([string]$Path, [string]$Ad)
    $vpy = Join-Path $Path 'Scripts\python.exe'
    if (Test-Path $vpy) {
        Write-Uyari ($Ad + ' zaten var; mevcut ortam yeniden kullanilacak.')
    } else {
        & $PythonExe @PythonArgs -m venv $Path
        if ($LASTEXITCODE -ne 0) { Fail ($Ad + ' sanal ortami olusturulamadi.') }
        Write-Ok ($Ad + ' sanal ortami olusturuldu.')
    }
    if (-not (Invoke-Pip -VenvPython $vpy -PipArgs @('install', '--upgrade', 'pip') -Aciklama ($Ad + ' icinde pip guncelleniyor'))) {
        Fail ($Ad + ': pip guncellenemedi.')
    }
    return $vpy
}

function Install-TorchCpu {
    param([string]$VenvPython, [string]$Ad)
    Write-Bilgi ($Ad + ': PyTorch (CPU) kuruluyor. Bu indirme buyuktur (yuzlerce MB) ve uzun surebilir.')
    if (Invoke-Pip -VenvPython $VenvPython -PipArgs @('install', 'torch==2.14.1+cpu', '--index-url', 'https://download.pytorch.org/whl/cpu') -Aciklama 'torch==2.14.1+cpu (PyTorch CPU dizini)') {
        Write-Ok ($Ad + ': torch 2.14.1+cpu kuruldu.')
        return
    }
    Write-Uyari 'PyTorch CPU dizininden kurulum basarisiz oldu; PyPI uzerinden torch>=2.2 deneniyor.'
    if (-not (Invoke-Pip -VenvPython $VenvPython -PipArgs @('install', 'torch>=2.2') -Aciklama 'torch>=2.2 (PyPI yedegi)')) {
        Fail ($Ad + ': torch hicbir kaynaktan kurulamadi.')
    }
    Write-Ok ($Ad + ': torch (PyPI yedegi) kuruldu.')
}

# --------------------------------------------- Track A: dashboard environment
Write-Host ''
Write-Host '--- Iz A: GEO Arastirma Panosu ortami (.venv-dashboard) ---'
$DashVenv = Join-Path $RepoRoot '.venv-dashboard'
$DashPy   = New-Venv -Path $DashVenv -Ad '.venv-dashboard'
Install-TorchCpu -VenvPython $DashPy -Ad '.venv-dashboard'
Push-Location $RepoRoot
$okRepoPkg = Invoke-Pip -VenvPython $DashPy -PipArgs @('install', '-e', '.[dev,ml]') -Aciklama 'depo paketi (.[dev,ml], duzenlenebilir kurulum)'
Pop-Location
if (-not $okRepoPkg) { Fail '.venv-dashboard: depo paketi (.[dev,ml]) kurulamadi.' }
if (-not (Invoke-Pip -VenvPython $DashPy -PipArgs @('install', '-r', (Join-Path $RepoRoot 'dashboard\requirements.txt')) -Aciklama 'dashboard/requirements.txt')) {
    Fail '.venv-dashboard: dashboard gereksinimleri kurulamadi.'
}
Write-Ok 'Iz A ortami hazir.'

# ----------------------------------------------- Track B: rfml environment
Write-Host ''
Write-Host '--- Iz B: RF-ML Ogrenme Uygulamasi ortami (.venv-rfml) ---'
$RfmlVenv = Join-Path $RepoRoot '.venv-rfml'
$RfmlPy   = New-Venv -Path $RfmlVenv -Ad '.venv-rfml'
Install-TorchCpu -VenvPython $RfmlPy -Ad '.venv-rfml'
if (-not (Invoke-Pip -VenvPython $RfmlPy -PipArgs @('install', '-r', (Join-Path $RepoRoot 'learning\rfml-basics\requirements.txt')) -Aciklama 'learning/rfml-basics/requirements.txt')) {
    Fail '.venv-rfml: gereksinimler kurulamadi.'
}
Write-Ok 'Iz B ortami hazir.'

# ------------------------------------------------------- Import smoke tests
Write-Host ''
Write-Host '--- Kurulum dogrulamasi (import testleri) ---'
& $DashPy -c "import numpy, scipy, streamlit, torch"
if ($LASTEXITCODE -ne 0) { Fail ('.venv-dashboard import testi basarisiz (numpy, scipy, streamlit, torch). Gunluk: ' + $LogPath) }
Write-Ok '.venv-dashboard: numpy, scipy, streamlit, torch iceri aktarildi.'
& $RfmlPy -c "import numpy, torch, matplotlib, streamlit"
if ($LASTEXITCODE -ne 0) { Fail ('.venv-rfml import testi basarisiz (numpy, torch, matplotlib, streamlit). Gunluk: ' + $LogPath) }
Write-Ok '.venv-rfml: numpy, torch, matplotlib, streamlit iceri aktarildi.'

# ----------------------------------------------------------------- Shortcuts
Write-Host ''
Write-Host '--- Kisayollar ---'
function New-Shortcut {
    param([string]$LnkPath, [string]$Target, [string]$Aciklama)
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($LnkPath)
    $sc.TargetPath = $Target
    $sc.WorkingDirectory = $ScriptDir
    $sc.Description = $Aciklama
    $sc.Save()
}
try {
    $desktop = [Environment]::GetFolderPath('Desktop')
    New-Shortcut -LnkPath (Join-Path $desktop 'GEO Arastirma Panosu.lnk') -Target (Join-Path $ScriptDir 'launch_dashboard.bat') -Aciklama 'Iz A: GEO arastirma panosu (Streamlit, yerel)'
    New-Shortcut -LnkPath (Join-Path $desktop 'RF-ML Ogrenme Uygulamasi.lnk') -Target (Join-Path $ScriptDir 'launch_rfml.bat') -Aciklama 'Iz B: RF-ML ogrenme uygulamasi (Streamlit, yerel)'
    $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Payload-Aware GEO Workbench'
    if (-not (Test-Path $startMenu)) { New-Item -ItemType Directory -Path $startMenu -Force | Out-Null }
    New-Shortcut -LnkPath (Join-Path $startMenu 'GEO Arastirma Panosu.lnk') -Target (Join-Path $ScriptDir 'launch_dashboard.bat') -Aciklama 'Iz A: GEO arastirma panosu (Streamlit, yerel)'
    New-Shortcut -LnkPath (Join-Path $startMenu 'RF-ML Ogrenme Uygulamasi.lnk') -Target (Join-Path $ScriptDir 'launch_rfml.bat') -Aciklama 'Iz B: RF-ML ogrenme uygulamasi (Streamlit, yerel)'
    New-Shortcut -LnkPath (Join-Path $startMenu 'Uygulamalari Durdur.lnk') -Target (Join-Path $ScriptDir 'stop_apps.bat') -Aciklama 'Calisan Workbench uygulamalarini durdurur'
    Write-Ok 'Masaustu ve Baslat menusu kisayollari olusturuldu.'
} catch {
    Write-Uyari ('Kisayollar olusturulamadi: ' + $_.Exception.Message)
    Write-Uyari 'Uygulamalari windows klasorundeki launch_dashboard.bat / launch_rfml.bat ile baslatabilirsiniz.'
}

# ------------------------------------------------------------------- Summary
Write-Host ''
Write-Host '====================================================='
Write-Ok 'Kurulum tamamlandi.'
Write-Bilgi 'Baslatma: Masaustunde "GEO Arastirma Panosu" ve "RF-ML Ogrenme Uygulamasi" kisayollari.'
Write-Bilgi 'Durdurma: Baslat menusunde "Uygulamalari Durdur" (veya windows\stop_apps.bat).'
Write-Bilgi 'Iki uygulama birbirinden tamamen ayridir; veri, model veya sonuc paylasmazlar.'
Write-Bilgi ("Kurulum gunlugu: " + $LogPath)
Write-Host '====================================================='
Stop-Transcript | Out-Null
exit 0
