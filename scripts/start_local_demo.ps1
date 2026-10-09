param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$demoDocument = Join-Path $projectRoot "data\demo_crf_sintetico.docx"
$previousPythonPath = $env:PYTHONPATH

try {
    $env:PYTHONPATH = Join-Path $projectRoot "src"
    Push-Location $projectRoot
    & $pythonExe -c "import fastapi, uvicorn, multipart"
    if ($LASTEXITCODE -ne 0) {
        throw "Faltan dependencias web. Ejecute: python -m pip install -r requirements-web.txt"
    }
    & $pythonExe -m revisor_crf.sample $demoDocument --with-discrepancy
    if ($LASTEXITCODE -ne 0) {
        throw "No fue posible crear el documento sintético de demostración."
    }
    Write-Host "Documento sintético: $demoDocument"
    Write-Host "Abra http://127.0.0.1:$Port y cargue ese archivo."
    Write-Host "Para detener la demostración presione Ctrl+C."
    & $pythonExe -m revisor_web --demo --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
