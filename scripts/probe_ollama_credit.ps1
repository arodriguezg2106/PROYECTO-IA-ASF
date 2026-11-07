[CmdletBinding()]
param(
    [switch]$SmokeTest,
    [ValidateSet('selection', 'validation-a', 'validation-b')]
    [string]$ConsistencyPhase
)

$ErrorActionPreference = 'Stop'
if ($SmokeTest -and $ConsistencyPhase) {
    throw 'SmokeTest y ConsistencyPhase son excluyentes.'
}
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'No se encontro el Python del entorno .venv del proyecto.'
}

$taskPreviousKey = [Environment]::GetEnvironmentVariable('OLLAMA_API_KEY', 'Process')
$taskPreviousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$taskSecret = $null
$taskCredential = $null
$taskExitCode = 1
Push-Location -LiteralPath $taskProjectRoot
try {
    $env:PYTHONPATH = 'src;scripts'
    if ($ConsistencyPhase) {
        & $taskPython scripts/evaluate_ollama_cloud.py --protocol consistency-v1 --preflight
        if ($LASTEXITCODE -ne 0) { throw 'Fallo el preflight; no se solicito la clave.' }
        $taskPreflight = Get-Content -LiteralPath results/ollama_cloud/consistency-v1/preflight.json -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($taskPreflight.status -ne 'ready') {
            throw 'Falta revisar y congelar el banco. Consulta docs/evaluacion_consistencia_gemma4.md. No se envio ninguna solicitud.'
        }
    }
    $taskSecret = Read-Host 'Pega tu API key de Ollama y presiona Enter (no se mostrara)' -AsSecureString
    $taskCredential = [System.Net.NetworkCredential]::new('', $taskSecret)
    if ([string]::IsNullOrWhiteSpace($taskCredential.Password)) {
        throw 'La clave esta vacia; no se envio ninguna solicitud.'
    }
    $env:OLLAMA_API_KEY = $taskCredential.Password
    $env:PYTHONPATH = 'src;scripts'
    if ($ConsistencyPhase) {
        Write-Host ('Ejecutando consistency-v1, fase ' + $ConsistencyPhase + ': hasta 60 intentos nuevos, 180 por experimento.')
        & $taskPython scripts/evaluate_ollama_cloud.py --protocol consistency-v1 --phase $ConsistencyPhase
    }
    elseif ($SmokeTest) {
        Write-Host 'Evaluando dos casos sinteticos, tres veces cada uno: maximo seis solicitudes, sin reintentos.'
        & $taskPython scripts/evaluate_ollama_cloud.py --models gemma4:31b --max-requests 6 --output results/ollama_cloud/gemma4_smoke.json
    }
    else {
        Write-Host 'Ejecutando un solo caso sintetico con Gemma 4 31B, sin reintentos.'
        & $taskPython scripts/evaluate_ollama_cloud.py --probe --models gemma4:31b --max-requests 1 --output results/ollama_cloud/credit_probe.json
    }
    $taskExitCode = $LASTEXITCODE
    if ($taskExitCode -eq 0) {
        Write-Host 'Operacion completada. Consulta el reporte y revisa Usage antes de otra etapa.'
    }
    elseif ($taskExitCode -eq 2) {
        Write-Host 'Evaluacion completada, pero no supero los criterios de calidad. Consulta el reporte.'
    }
    else {
        Write-Host 'Ejecucion detenida: consulta el motivo anterior. Esto no significa que la evaluacion se haya completado.'
    }
}
catch {
    Write-Host $_.Exception.Message
    $taskExitCode = 1
}
finally {
    [Environment]::SetEnvironmentVariable('OLLAMA_API_KEY', $taskPreviousKey, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $taskPreviousPythonPath, 'Process')
    if ($null -ne $taskSecret) { $taskSecret.Dispose() }
    $taskCredential = $null
    $taskPreviousKey = $null
    Pop-Location
}
exit $taskExitCode
