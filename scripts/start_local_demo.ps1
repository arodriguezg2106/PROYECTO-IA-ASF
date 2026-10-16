param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000,
    [switch]$Editorial,
    [switch]$LanguageTool,
    [string]$LanguageToolProfile
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
$previousEditorial = $env:REVISOR_WEB_EDITORIAL_ENABLED
$previousLanguageTool = $env:REVISOR_WEB_LANGUAGETOOL_ENABLED
$previousLanguageToolProfile = $env:REVISOR_WEB_LANGUAGETOOL_PROFILE
$previousConcurrency = $env:REVISOR_WEB_MAX_CONCURRENT_JOBS
$locationPushed = $false

try {
    if ($LanguageTool -and -not $Editorial) {
        throw "-LanguageTool requiere -Editorial."
    }
    if ($LanguageTool -and -not $LanguageToolProfile) {
        throw "-LanguageTool requiere -LanguageToolProfile con un perfil aprobado."
    }
    $env:PYTHONPATH = Join-Path $projectRoot "src"
    $env:REVISOR_WEB_EDITORIAL_ENABLED = if ($Editorial) { "1" } else { "0" }
    $env:REVISOR_WEB_LANGUAGETOOL_ENABLED = if ($LanguageTool) { "1" } else { "0" }
    if ($LanguageTool) {
        $resolvedProfile = (Resolve-Path -LiteralPath $LanguageToolProfile).Path
        $env:REVISOR_WEB_LANGUAGETOOL_PROFILE = $resolvedProfile
        $env:REVISOR_WEB_MAX_CONCURRENT_JOBS = "1"
    }
    Push-Location $projectRoot
    $locationPushed = $true
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
    if ($locationPushed) {
        Pop-Location
    }
    $env:PYTHONPATH = $previousPythonPath
    $env:REVISOR_WEB_EDITORIAL_ENABLED = $previousEditorial
    $env:REVISOR_WEB_LANGUAGETOOL_ENABLED = $previousLanguageTool
    $env:REVISOR_WEB_LANGUAGETOOL_PROFILE = $previousLanguageToolProfile
    $env:REVISOR_WEB_MAX_CONCURRENT_JOBS = $previousConcurrency
}
