param([int]$Port = 8081)

$ErrorActionPreference = "Stop"
$runtimeDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\results\languagetool"))
$pidFile = Join-Path $runtimeDir "server.pid"
if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    Write-Output "No existe un PID registrado para LanguageTool."
    exit 0
}
$processId = [int](Get-Content -Raw -LiteralPath $pidFile)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
if (-not $process) {
    Write-Output "El proceso registrado ya no existe."
    exit 0
}
if ($process.CommandLine -notlike "*languagetool-server.jar*") {
    throw "El PID $processId no corresponde a LanguageTool; no se detuvo ningún proceso."
}
Stop-Process -Id $processId
Write-Output "LanguageTool detenido (PID $processId, puerto $Port)."
