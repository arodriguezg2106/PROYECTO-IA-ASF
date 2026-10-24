param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000,
    [switch]$Editorial,
    [switch]$LanguageTool,
    [string]$LanguageToolProfile,
    [switch]$Ollama,
    [string]$OllamaProfile,
    [switch]$ExperimentalAI,
    [switch]$ExperimentalAIAllDocuments,
    [switch]$LanDemo,
    [string]$LanAddress,
    [string]$OllamaUrl = "http://127.0.0.1:11434"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ollamaApiUrl = $OllamaUrl.TrimEnd("/")
if (-not $ollamaApiUrl.EndsWith("/api")) {
    $ollamaApiUrl += "/api"
}
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$demoDirectory = Join-Path $projectRoot "data\demo_direccion"
$previousPythonPath = $env:PYTHONPATH
$previousDemoMode = $env:REVISOR_WEB_DEMO_MODE
$previousLanDemoMode = $env:REVISOR_WEB_LAN_DEMO_MODE
$previousLanAccessCodeHash = $env:REVISOR_WEB_LAN_ACCESS_CODE_SHA256
$previousWebHost = $env:REVISOR_WEB_HOST
$previousWebPort = $env:REVISOR_WEB_PORT
$previousEditorial = $env:REVISOR_WEB_EDITORIAL_ENABLED
$previousLanguageTool = $env:REVISOR_WEB_LANGUAGETOOL_ENABLED
$previousLanguageToolProfile = $env:REVISOR_WEB_LANGUAGETOOL_PROFILE
$previousConcurrency = $env:REVISOR_WEB_MAX_CONCURRENT_JOBS
$previousOllama = $env:REVISOR_WEB_OLLAMA_ENABLED
$previousOllamaProfile = $env:REVISOR_WEB_OLLAMA_PROFILE
$previousOllamaUrl = $env:REVISOR_WEB_OLLAMA_URL
$previousOllamaResearch = $env:REVISOR_WEB_OLLAMA_RESEARCH_ENABLED
$previousOllamaResearchHashes = $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOWED_SHA256
$previousOllamaResearchAllDocuments = $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOW_ALL_DOCUMENTS
$locationPushed = $false

try {
    if ($LanguageTool -and -not $Editorial) {
        throw "-LanguageTool requiere -Editorial."
    }
    if ($LanguageTool -and -not $LanguageToolProfile) {
        throw "-LanguageTool requiere -LanguageToolProfile con un perfil aprobado."
    }
    if ($Ollama -and -not $Editorial) {
        throw "-Ollama requiere -Editorial."
    }
    if ($Ollama -and -not $OllamaProfile) {
        throw "-Ollama requiere -OllamaProfile generado desde una evaluaciÃ³n aprobatoria."
    }
    if ($LanguageTool -and $Ollama) {
        throw "LanguageTool y Ollama no pueden estar activos simultÃ¡neamente."
    }
    if ($ExperimentalAI -and -not $Editorial) {
        throw "-ExperimentalAI requiere -Editorial."
    }
    if ($ExperimentalAI -and ($LanguageTool -or $Ollama)) {
        throw "-ExperimentalAI no puede combinarse con LanguageTool ni con un perfil aprobado de Ollama."
    }
    if ($ExperimentalAIAllDocuments -and -not $ExperimentalAI) {
        throw "-ExperimentalAIAllDocuments requiere -ExperimentalAI."
    }
    if ($LanDemo -and -not $LanAddress) {
        $LanAddress = Get-NetIPConfiguration |
            Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } |
            ForEach-Object { $_.IPv4Address.IPAddress } |
            Where-Object { $_ -and $_ -notlike "169.254.*" } |
            Select-Object -First 1
        if (-not $LanAddress) {
            throw "No se detectó una IP LAN. Indíquela con -LanAddress, por ejemplo 192.168.1.25."
        }
    }
    $env:PYTHONPATH = Join-Path $projectRoot "src"
    $env:REVISOR_WEB_DEMO_MODE = if ($LanDemo) { "0" } else { "1" }
    $env:REVISOR_WEB_LAN_DEMO_MODE = if ($LanDemo) { "1" } else { "0" }
    $env:REVISOR_WEB_HOST = if ($LanDemo) { $LanAddress } else { "127.0.0.1" }
    $env:REVISOR_WEB_PORT = $Port.ToString()
    $lanAccessCode = $null
    $lanAccessCodeHash = $null
    if ($LanDemo) {
        $randomBytes = New-Object byte[] 6
        $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $randomGenerator.GetBytes($randomBytes)
        } finally {
            $randomGenerator.Dispose()
        }
        $lanAccessCode = ([BitConverter]::ToString($randomBytes)).Replace("-", "")
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $codeBytes = [System.Text.Encoding]::UTF8.GetBytes($lanAccessCode)
            $lanAccessCodeHash = ([BitConverter]::ToString($sha256.ComputeHash($codeBytes))).Replace("-", "").ToLowerInvariant()
        } finally {
            $sha256.Dispose()
        }
        $env:REVISOR_WEB_LAN_ACCESS_CODE_SHA256 = $lanAccessCodeHash
    }
    $env:REVISOR_WEB_EDITORIAL_ENABLED = if ($Editorial) { "1" } else { "0" }
    $env:REVISOR_WEB_LANGUAGETOOL_ENABLED = if ($LanguageTool) { "1" } else { "0" }
    $env:REVISOR_WEB_OLLAMA_ENABLED = if ($Ollama) { "1" } else { "0" }
    $env:REVISOR_WEB_OLLAMA_RESEARCH_ENABLED = "0"
    $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOW_ALL_DOCUMENTS = "0"
    if ($LanguageTool) {
        $resolvedProfile = (Resolve-Path -LiteralPath $LanguageToolProfile).Path
        $env:REVISOR_WEB_LANGUAGETOOL_PROFILE = $resolvedProfile
        $env:REVISOR_WEB_MAX_CONCURRENT_JOBS = "1"
    }
    if ($Ollama) {
        $resolvedOllamaProfile = (Resolve-Path -LiteralPath $OllamaProfile).Path
        $env:REVISOR_WEB_OLLAMA_PROFILE = $resolvedOllamaProfile
        $env:REVISOR_WEB_OLLAMA_URL = $ollamaApiUrl
        $env:REVISOR_WEB_MAX_CONCURRENT_JOBS = "1"
    }
    Push-Location $projectRoot
    $locationPushed = $true
    & $pythonExe -c "import fastapi, uvicorn, multipart"
    if ($LASTEXITCODE -ne 0) {
        throw "Faltan dependencias web. Ejecute: python -m pip install -r requirements-web.txt"
    }
    & $pythonExe scripts\verify_direction_demo.py
    if ($LASTEXITCODE -ne 0) {
        throw "No fue posible crear el documento sintético de demostración."
    }
    if ($ExperimentalAI) {
        $demoHashes = Get-ChildItem -LiteralPath $demoDirectory -Filter "*.docx" -File |
            Sort-Object Name |
            ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
        if ($demoHashes.Count -ne 4) {
            throw "No se encontraron los cuatro casos sintéticos autorizados para la IA experimental."
        }
        $env:REVISOR_WEB_OLLAMA_RESEARCH_ENABLED = "1"
        $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOWED_SHA256 = $demoHashes -join ","
        $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOW_ALL_DOCUMENTS = if ($ExperimentalAIAllDocuments) { "1" } else { "0" }
        $env:REVISOR_WEB_OLLAMA_URL = $ollamaApiUrl
        $env:REVISOR_WEB_MAX_CONCURRENT_JOBS = "1"
        Write-Host "IA experimental: Gemma 3 12B, alta cobertura, máximo 5 sugerencias."
        Write-Host "Advertencia: el modelo no está aprobado y puede producir falsos positivos."
        if ($ExperimentalAIAllDocuments) {
            Write-Host "ALCANCE DE PRUEBA: la IA revisará todos los DOCX cargados durante esta sesión."
            Write-Host "Use sólo documentos autorizados; el modelo sigue siendo experimental."
        }
    }
    Write-Host "Casos sintéticos listos en: $demoDirectory"
    Write-Host "Orden sugerido:"
    Write-Host "  1. 01_suma_incorrecta.docx"
    Write-Host "  2. 02_suma_correcta_compleja.docx"
    Write-Host "  3. 03_operacion_no_evaluable.docx"
    Write-Host "  4. 04_revision_editorial.docx"
    if ($LanDemo) {
        Write-Host ""
        Write-Host "Enlace para compartir sólo dentro de esta red: http://${LanAddress}:$Port"
        Write-Host "Código temporal de acceso: $lanAccessCode"
        Write-Host "No redirija este puerto en el router ni comparta el enlace fuera de la red local."
    } else {
        Write-Host "Abra http://127.0.0.1:$Port y cargue los archivos en ese orden."
    }
    Write-Host "Para detener la demostración presione Ctrl+C."
    if ($LanDemo) {
        & $pythonExe -m revisor_web --lan-demo --lan-access-code-sha256 $lanAccessCodeHash --host $LanAddress --port $Port
    } else {
        & $pythonExe -m revisor_web --demo --host 127.0.0.1 --port $Port
    }
} finally {
    if ($locationPushed) {
        Pop-Location
    }
    $env:PYTHONPATH = $previousPythonPath
    $env:REVISOR_WEB_DEMO_MODE = $previousDemoMode
    $env:REVISOR_WEB_LAN_DEMO_MODE = $previousLanDemoMode
    $env:REVISOR_WEB_LAN_ACCESS_CODE_SHA256 = $previousLanAccessCodeHash
    $env:REVISOR_WEB_HOST = $previousWebHost
    $env:REVISOR_WEB_PORT = $previousWebPort
    $env:REVISOR_WEB_EDITORIAL_ENABLED = $previousEditorial
    $env:REVISOR_WEB_LANGUAGETOOL_ENABLED = $previousLanguageTool
    $env:REVISOR_WEB_LANGUAGETOOL_PROFILE = $previousLanguageToolProfile
    $env:REVISOR_WEB_MAX_CONCURRENT_JOBS = $previousConcurrency
    $env:REVISOR_WEB_OLLAMA_ENABLED = $previousOllama
    $env:REVISOR_WEB_OLLAMA_PROFILE = $previousOllamaProfile
    $env:REVISOR_WEB_OLLAMA_URL = $previousOllamaUrl
    $env:REVISOR_WEB_OLLAMA_RESEARCH_ENABLED = $previousOllamaResearch
    $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOWED_SHA256 = $previousOllamaResearchHashes
    $env:REVISOR_WEB_OLLAMA_RESEARCH_ALLOW_ALL_DOCUMENTS = $previousOllamaResearchAllDocuments
}
