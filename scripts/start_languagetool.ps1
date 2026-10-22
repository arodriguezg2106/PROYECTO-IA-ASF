param(
    [string]$JavaExe = "C:\Program Files\Eclipse Adoptium\jre-17.0.20.101-hotspot\bin\java.exe",
    [string]$LanguageToolDir = "D:\arodriguezg\Tools\LanguageTool",
    [int]$Port = 8081,
    [int]$MaxMemoryMb = 1536
)

$ErrorActionPreference = "Stop"
$serverJar = Join-Path $LanguageToolDir "languagetool-server.jar"
$runtimeDir = Join-Path $PSScriptRoot "..\results\languagetool"
$runtimeDir = [System.IO.Path]::GetFullPath($runtimeDir)
$pidFile = Join-Path $runtimeDir "server.pid"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

if (-not (Test-Path -LiteralPath $JavaExe -PathType Leaf)) {
    throw "No se encontró Java 17 en: $JavaExe"
}
if (-not (Test-Path -LiteralPath $serverJar -PathType Leaf)) {
    throw "No se encontró LanguageTool en: $serverJar"
}
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "El puerto $Port ya está ocupado por el proceso $($listener[0].OwningProcess)."
}

if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
    $registeredId = 0
    [void][int]::TryParse((Get-Content -Raw -LiteralPath $pidFile), [ref]$registeredId)
    $registered = if ($registeredId) {
        Get-CimInstance Win32_Process -Filter "ProcessId=$registeredId" -ErrorAction SilentlyContinue
    }
    if ($registered -and $registered.CommandLine -like "*languagetool-server.jar*") {
        throw "LanguageTool ya está registrado con PID $registeredId."
    }
    Remove-Item -LiteralPath $pidFile -Force
}
$arguments = @(
    "-Xms256m", "-Xmx${MaxMemoryMb}m", "-cp", $serverJar,
    "org.languagetool.server.HTTPServer", "--port", "$Port"
)
$process = Start-Process -FilePath $JavaExe -ArgumentList $arguments `
    -WorkingDirectory $LanguageToolDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir "server.out.log") `
    -RedirectStandardError (Join-Path $runtimeDir "server.err.log")
try {
    $process.Id | Set-Content -LiteralPath $pidFile -Encoding ascii -NoNewline
} catch {
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    throw
}
Write-Output "LanguageTool iniciado en http://127.0.0.1:$Port/v2 (PID $($process.Id))."
