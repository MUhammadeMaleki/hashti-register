$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot 'backend\.env'
if (-not (Test-Path -LiteralPath $envPath)) {
    throw 'backend/.env is missing. Configure it or start project PostgreSQL first.'
}
$configuration = [IO.File]::ReadAllText($envPath)
if ($configuration -match '(?m)^HASHTI_AUTH_SECRET=([0-9a-fA-F]{64})\s*$') {
    Write-Output 'Authentication secret is configured.'
    exit
}
if ($configuration -match '(?m)^HASHTI_AUTH_SECRET=') {
    throw 'Existing HASHTI_AUTH_SECRET is invalid; fix it explicitly before continuing.'
}
$bytes = New-Object byte[] 32
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
$secret = [BitConverter]::ToString($bytes).Replace('-', '')
$separator = if ($configuration.EndsWith("`n")) { '' } else { "`n" }
[IO.File]::AppendAllText($envPath, "${separator}HASHTI_AUTH_SECRET=$secret`n", [Text.UTF8Encoding]::new($false))
Write-Output 'Authentication secret was added to the ignored backend/.env file.'
