# stop_apps.ps1 - stop the running Workbench apps using windows\logs\<app>.pid.
# Kills the whole process tree (taskkill /T /F), removes the pid file, and
# handles stale or corrupt pid files gracefully. ASCII-transliterated Turkish.

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir 'logs'

$apps = [ordered]@{
    dashboard = 'GEO Arastirma Panosu'
    rfml      = 'RF-ML Ogrenme Uygulamasi'
}

$stopped = 0
foreach ($app in $apps.Keys) {
    $name = $apps[$app]
    $pidFile = Join-Path $LogDir ($app + '.pid')
    if (-not (Test-Path $pidFile)) {
        Write-Host ("[OK]    " + $name + ": calisan kayit yok.")
        continue
    }
    $content = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($content -match '^(\d+);(\d+)$') {
        $procId = [int]$Matches[1]
        $alive = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($alive) {
            taskkill /PID $procId /T /F | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host ("[OK]    " + $name + " durduruldu (PID " + $procId + ").")
                $stopped++
            } else {
                Write-Host ("[UYARI] " + $name + ": PID " + $procId + " durdurulamadi (taskkill hata kodu " + $LASTEXITCODE + ").")
            }
        } else {
            Write-Host ("[UYARI] " + $name + ": PID " + $procId + " zaten calismiyordu; eski kayit temizlendi.")
        }
    } else {
        Write-Host ("[UYARI] " + $name + ": pid dosyasi bozuktu; temizlendi.")
    }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

if ($stopped -eq 0) {
    Write-Host 'Durdurulacak calisan uygulama bulunamadi.'
} else {
    Write-Host ("Toplam " + $stopped + " uygulama durduruldu.")
}
exit 0
