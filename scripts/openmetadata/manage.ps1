param(
    [ValidateSet("start", "stop", "status", "health", "bootstrap")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EltEnvPath = Join-Path $RepoRoot ".env"
$OmEnvPath = Join-Path $RepoRoot ".env.openmetadata"
$ComposePath = Join-Path $RepoRoot "docker-compose.openmetadata.yml"

function Read-EnvFile([string]$Path) {
    $values = @{}
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $name, $value = $line -split '=', 2
        $values[$name.Trim()] = $value.Trim()
    }
    return $values
}

function New-RandomSecret([int]$Bytes = 32) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($buffer) -replace '[^A-Za-z0-9]', '').Substring(0, 32)
}

function Initialize-OpenMetadataEnv {
    if (Test-Path -LiteralPath $OmEnvPath) { return }
    if (-not (Test-Path -LiteralPath $EltEnvPath)) {
        throw "Arquivo .env do ELT nao encontrado. Execute .\setup.ps1 primeiro."
    }

    $elt = Read-EnvFile $EltEnvPath
    foreach ($required in @("POSTGRES_USER", "POSTGRES_PASSWORD", "AIRFLOW_ADMIN_USERNAME", "AIRFLOW_ADMIN_PASSWORD")) {
        if (-not $elt[$required]) { throw "Variavel $required ausente no .env do ELT." }
    }

    $network = docker inspect elt-postgres --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}'
    if ($LASTEXITCODE -ne 0 -or -not $network) {
        throw "Container elt-postgres indisponivel. Inicie o ELT antes do OpenMetadata."
    }

    $content = @(
        "OPENMETADATA_VERSION=2.0.2"
        "OPENMETADATA_PORT=8585"
        "OM_DB_PASSWORD=$(New-RandomSecret)"
        "OM_ADMIN_USERNAME=admin@open-metadata.org"
        "OM_ADMIN_PASSWORD=admin"
        "ELT_DOCKER_NETWORK=$network"
        "ELT_POSTGRES_USER=$($elt.POSTGRES_USER)"
        "ELT_POSTGRES_PASSWORD=$($elt.POSTGRES_PASSWORD)"
        "ELT_AIRFLOW_USERNAME=$($elt.AIRFLOW_ADMIN_USERNAME)"
        "ELT_AIRFLOW_PASSWORD=$($elt.AIRFLOW_ADMIN_PASSWORD)"
    )
    [System.IO.File]::WriteAllLines($OmEnvPath, $content, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-Compose([string[]]$Arguments) {
    $dockerArgs = @(
        "compose", "--project-name", "elt-openmetadata",
        "--env-file", $OmEnvPath,
        "--file", $ComposePath
    ) + $Arguments
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) { throw "docker compose falhou com codigo $LASTEXITCODE." }
}

function Test-OpenMetadataHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8585/api/v1/system/version" -TimeoutSec 10
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

Set-Location $RepoRoot

switch ($Action) {
    "start" {
        Initialize-OpenMetadataEnv
        Invoke-Compose @("up", "-d", "openmetadata-postgres", "openmetadata-elasticsearch", "openmetadata-migrate", "openmetadata-server")
        for ($attempt = 1; $attempt -le 40; $attempt++) {
            if (Test-OpenMetadataHealth) {
                Write-Output "OpenMetadata disponivel em http://localhost:8585"
                exit 0
            }
            Start-Sleep -Seconds 5
        }
        throw "OpenMetadata nao ficou saudavel no tempo esperado. Execute manage.ps1 status."
    }
    "stop" {
        if (-not (Test-Path -LiteralPath $OmEnvPath)) { throw ".env.openmetadata nao encontrado." }
        Invoke-Compose @("stop")
    }
    "status" {
        if (-not (Test-Path -LiteralPath $OmEnvPath)) { throw ".env.openmetadata nao encontrado. Execute a acao start." }
        Invoke-Compose @("ps", "-a")
    }
    "health" {
        if (Test-OpenMetadataHealth) { Write-Output "healthy"; exit 0 }
        Write-Output "unhealthy"
        exit 1
    }
    "bootstrap" {
        Initialize-OpenMetadataEnv
        if (-not (Test-OpenMetadataHealth)) { throw "OpenMetadata indisponivel. Execute a acao start primeiro." }
        Invoke-Compose @("--profile", "tools", "run", "--rm", "openmetadata-bootstrap")
    }
}
