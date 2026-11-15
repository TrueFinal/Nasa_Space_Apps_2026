param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Crie o ambiente primeiro: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements-infrared.txt'
    }
    $calibrationPath = Join-Path $PSScriptRoot 'data/infrared/calibrations'
    $missingCalibration = @(1..6 | Where-Object { -not (Test-Path -LiteralPath (Join-Path $calibrationPath "calibration_D$_.fits")) })
    if ($missingCalibration.Count -gt 0) {
        & $pythonPath scripts/infrared_lab.py calibration --detector all --output $calibrationPath
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar as calibracoes D1-D6.' }
    }
    Write-Host "Zephyr IR Lab: http://127.0.0.1:$Port/"
    & $pythonPath scripts/infrared_lab.py serve --calibration $calibrationPath --coordinates sky --port $Port
} finally {
    Pop-Location
}
