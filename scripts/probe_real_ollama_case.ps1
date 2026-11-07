[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskOldKey = [Environment]::GetEnvironmentVariable('OLLAMA_API_KEY', 'Process')
$taskOldPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$taskSecret = $null
$taskCredential = $null
$taskExitCode = 1
Push-Location -LiteralPath $taskRoot
try {
    $env:PYTHONPATH = 'src;scripts'
    & $taskPython scripts/probe_real_ollama_case.py --prepare
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el caso; no se solicito la clave.' }
    $taskExisting = 'results/ollama_cloud/real_case_sonora/result.json'
    if ((Test-Path -LiteralPath $taskExisting) -and
        @((Get-Content -LiteralPath $taskExisting -Raw -Encoding UTF8 | ConvertFrom-Json).attempts).Count -ge 6) {
        Write-Host 'El piloto ya registro sus seis intentos; no se repiten solicitudes.'
        $taskExitCode = 0
    }
    else {
        $taskSecret = Read-Host 'Pega tu API key de Ollama y presiona Enter (no se mostrara)' -AsSecureString
        $taskCredential = [System.Net.NetworkCredential]::new('', $taskSecret)
        if ([string]::IsNullOrWhiteSpace($taskCredential.Password)) { throw 'La clave esta vacia.' }
        $env:OLLAMA_API_KEY = $taskCredential.Password
        Write-Host 'Se enviaran dos parrafos del caso de Sonora por separado, tres veces cada uno: hasta seis solicitudes.'
        & $taskPython scripts/probe_real_ollama_case.py
        $taskExitCode = $LASTEXITCODE
        if ($taskExitCode -eq 0) { Write-Host 'Piloto completado. Consulta el reporte y el consumo en Ollama.' }
        else { Write-Host 'El piloto se detuvo o tuvo errores. Revisa el mensaje y el reporte; no implica una evaluacion aprobada.' }
    }
}
catch {
    Write-Host $_.Exception.Message
    $taskExitCode = 1
}
finally {
    [Environment]::SetEnvironmentVariable('OLLAMA_API_KEY', $taskOldKey, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $taskOldPythonPath, 'Process')
    if ($null -ne $taskSecret) { $taskSecret.Dispose() }
    $taskCredential = $null
    $taskOldKey = $null
    Pop-Location
}
exit $taskExitCode
