param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [string]$PostgresBin = 'C:\Program Files\PostgreSQL\17\bin',
    [int]$Port = 55432
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $projectRoot '.local'
$dataPath = Join-Path $localRoot 'postgres-dev'
$envPath = Join-Path $projectRoot 'backend\.env'
$pgCtl = Join-Path $PostgresBin 'pg_ctl.exe'
$psql = Join-Path $PostgresBin 'psql.exe'
if (-not (Test-Path -LiteralPath $pgCtl)) { throw 'PostgreSQL binaries were not found. Pass -PostgresBin.' }

function Assert-CommandSucceeded([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE). No existing database was removed." }
}

function New-LocalPassword {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '')
}

if ($Action -eq 'status') {
    & $pgCtl status -D $dataPath
    exit $LASTEXITCODE
}
if ($Action -eq 'stop') {
    & $pgCtl stop -D $dataPath -m fast -w
    Assert-CommandSucceeded 'Stopping project PostgreSQL'
    exit
}

$newCluster = -not (Test-Path -LiteralPath (Join-Path $dataPath 'PG_VERSION'))
if ($newCluster) {
    if (Test-Path -LiteralPath $envPath) {
        throw 'backend/.env already exists. Configure that database, or move the file yourself before bootstrapping.'
    }
    $portCheck = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $portCheck.Start() } finally { $portCheck.Stop() }
    New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
    $adminPassword = New-LocalPassword
    $appPassword = New-LocalPassword
    $passwordFile = Join-Path $localRoot ('initdb-' + [Guid]::NewGuid().ToString('N') + '.secret')
    try {
        [IO.File]::WriteAllText($passwordFile, $adminPassword, [Text.UTF8Encoding]::new($false))
        & (Join-Path $PostgresBin 'initdb.exe') -D $dataPath -U hashti_local_admin --auth=scram-sha-256 --encoding=UTF8 --locale=C --pwfile=$passwordFile
        Assert-CommandSucceeded 'Initializing isolated project PostgreSQL'
    } finally {
        if (Test-Path -LiteralPath $passwordFile) { Remove-Item -LiteralPath $passwordFile }
    }
} elseif (-not (Test-Path -LiteralPath $envPath)) {
    throw 'Project PostgreSQL exists but backend/.env is missing; restore that configuration before continuing.'
}

& $pgCtl status -D $dataPath *> $null
if ($LASTEXITCODE -ne 0) {
    & $pgCtl start -D $dataPath -l (Join-Path $localRoot 'postgres.log') -o "-h 127.0.0.1 -p $Port" -w
    Assert-CommandSucceeded 'Starting isolated project PostgreSQL'
}

if ($newCluster) {
    $previousPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $adminPassword
        # Only newly created, isolated project databases are provisioned here.
        $sql = "CREATE ROLE hashti_app LOGIN PASSWORD '$appPassword' NOSUPERUSER NOCREATEDB NOCREATEROLE;"
        $sql | & $psql -X -q -w -h 127.0.0.1 -p $Port -U hashti_local_admin -d postgres -v ON_ERROR_STOP=1
        Assert-CommandSucceeded 'Creating restricted application role'
        & (Join-Path $PostgresBin 'createdb.exe') -w -h 127.0.0.1 -p $Port -U hashti_local_admin -O hashti_app hashti_dev
        Assert-CommandSucceeded 'Creating development database'
        & (Join-Path $PostgresBin 'createdb.exe') -w -h 127.0.0.1 -p $Port -U hashti_local_admin -O hashti_app hashti_test
        Assert-CommandSucceeded 'Creating test database'
        $configuration = @(
            'HASHTI_ENVIRONMENT=development',
            "HASHTI_DATABASE_URL=postgresql+psycopg://hashti_app:$appPassword@127.0.0.1:$Port/hashti_dev",
            "HASHTI_TEST_DATABASE_URL=postgresql+psycopg://hashti_app:$appPassword@127.0.0.1:$Port/hashti_test",
            "HASHTI_AUTH_SECRET=$(New-LocalPassword)",
            'HASHTI_PUBLIC_ORIGIN=http://127.0.0.1:3000'
        ) -join "`n"
        [IO.File]::WriteAllText($envPath, $configuration + "`n", [Text.UTF8Encoding]::new($false))
    } finally {
        $env:PGPASSWORD = $previousPassword
        $adminPassword = $null
        $appPassword = $null
    }
}
Write-Output "Project PostgreSQL is ready on 127.0.0.1:$Port. Existing services are unchanged."
