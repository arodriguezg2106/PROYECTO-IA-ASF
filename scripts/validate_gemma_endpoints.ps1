[CmdletBinding()]
param([switch]$GeminiOnly, [switch]$IncludeImage, [switch]$GeminiMinimal, [switch]$GeminiStreaming, [switch]$GeminiStreamHighOnly)

$ErrorActionPreference = 'Stop'
if (($GeminiMinimal -or $GeminiStreaming -or $GeminiStreamHighOnly) -and $IncludeImage) { throw 'El diagnostico solo admite texto.' }
if (($GeminiMinimal -and ($GeminiStreaming -or $GeminiStreamHighOnly)) -or ($GeminiStreaming -and $GeminiStreamHighOnly)) { throw 'Elige un solo diagnostico.' }
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'No se encontro .venv\Scripts\python.exe.' }
$taskPriorGemini = [Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'Process')
$taskPriorOllama = [Environment]::GetEnvironmentVariable('OLLAMA_API_KEY', 'Process')
$taskGeminiSecret = $null
$taskOllamaSecret = $null
$taskGeminiCredential = $null
$taskOllamaCredential = $null
$taskExitCode = 1
Push-Location -LiteralPath $taskProjectRoot
try {
    if ($GeminiStreamHighOnly) {
        Write-Host 'Solo la variante HIGH pendiente: una solicitud nueva a Gemini. No se repite el caso minimo ni se consulta Ollama.'
    }
    elseif ($GeminiStreaming) {
        Write-Host 'Diagnostico streaming: dos configuraciones distintas, maximo dos solicitudes a Gemini. Sin Ollama, busqueda web ni audio.'
    }
    elseif ($GeminiMinimal) {
        Write-Host 'Diagnostico: una sola solicitud de texto a Gemini, sin parametros de generacion. Sin reintentos ni llamadas a Ollama.'
    }
    else {
        Write-Host 'Solo textos sinteticos. Maximo 4 solicitudes por proveedor (5 si se incluye imagen). Sin reintentos.'
    }
    if ([string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)) {
        $taskGeminiSecret = Read-Host 'Pega tu API key de Google AI Studio y presiona Enter (oculta)' -AsSecureString
        $taskGeminiCredential = [System.Net.NetworkCredential]::new('', $taskGeminiSecret)
        if ([string]::IsNullOrWhiteSpace($taskGeminiCredential.Password)) { throw 'Clave Gemini vacia. No se enviaron solicitudes.' }
        $env:GEMINI_API_KEY = $taskGeminiCredential.Password
    }
    $taskArgs = @('scripts/validate_gemma_endpoints.py')
    if ($GeminiStreamHighOnly) {
        $taskArgs += '--gemini-stream-high-only'
    }
    elseif ($GeminiStreaming) {
        $taskArgs += '--gemini-streaming'
    }
    elseif ($GeminiMinimal) {
        $taskArgs += '--gemini-minimal'
    }
    elseif ($GeminiOnly) {
        $taskArgs += @('--providers', 'gemini')
    }
    elseif ([string]::IsNullOrWhiteSpace($env:OLLAMA_API_KEY)) {
        $taskOllamaSecret = Read-Host 'Ollama opcional: pega su key; Enter vacio para omitir (no se compran creditos)' -AsSecureString
        $taskOllamaCredential = [System.Net.NetworkCredential]::new('', $taskOllamaSecret)
        if (-not [string]::IsNullOrWhiteSpace($taskOllamaCredential.Password)) {
            $env:OLLAMA_API_KEY = $taskOllamaCredential.Password
        }
    }
    if ($IncludeImage) { $taskArgs += '--include-image' }
    & $taskPython @taskArgs
    $taskExitCode = $LASTEXITCODE
    if ($GeminiStreaming -or $GeminiStreamHighOnly) { Write-Host 'Termino. Reporte: VALIDACION_GEMINI_STREAMING.md.' }
    elseif ($GeminiMinimal) { Write-Host 'Termino. Reporte: VALIDACION_GEMINI_DIAGNOSTICO.md.' }
    else { Write-Host 'Termino. Reporte: VALIDACION_GEMINI.md.' }
}
finally {
    [Environment]::SetEnvironmentVariable('GEMINI_API_KEY', $taskPriorGemini, 'Process')
    [Environment]::SetEnvironmentVariable('OLLAMA_API_KEY', $taskPriorOllama, 'Process')
    if ($null -ne $taskGeminiSecret) { $taskGeminiSecret.Dispose() }
    if ($null -ne $taskOllamaSecret) { $taskOllamaSecret.Dispose() }
    $taskGeminiCredential = $null
    $taskOllamaCredential = $null
    Pop-Location
}
exit $taskExitCode
