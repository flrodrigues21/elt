param(
    [ValidateSet("start", "stop", "status", "health", "bootstrap")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EnvPath = Join-Path $RepoRoot ".env"
$ComposePath = Join-Path $RepoRoot "docker-compose.yml"

function Assert-Environment {
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        throw "Arquivo .env nao encontrado. Execute .\setup.ps1 primeiro."
    }
}

function Get-EnvValue([string]$Name, [string]$Default) {
    $line = Get-Content -LiteralPath $EnvPath | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $line) { return $Default }
    $value = ($line -split "=", 2)[1].Trim()
    if (-not $value) { return $Default }
    return $value
}

function Invoke-Compose([string[]]$Arguments) {
    $dockerArgs = @(
        "compose", "--project-name", "elt",
        "--env-file", $EnvPath,
        "--file", $ComposePath
    ) + $Arguments
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) { throw "docker compose falhou com codigo $LASTEXITCODE." }
}

function Get-ContainerState([string]$ContainerName) {
    $state = docker inspect $ContainerName --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}:{{.State.ExitCode}}' 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel inspecionar o container $ContainerName." }
    return $state
}

function Test-OpenMetadataHealth {
    $port = Get-EnvValue "OPENMETADATA_PORT" "8585"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$port/api/v1/system/version" -TimeoutSec 10
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

Set-Location $RepoRoot

switch ($Action) {
    "start" {
        Assert-Environment
        $port = Get-EnvValue "OPENMETADATA_PORT" "8585"
        Invoke-Compose @("up", "-d", "openmetadata-postgres", "openmetadata-elasticsearch", "openmetadata-migrate", "openmetadata-server", "openmetadata-security-init")
        for ($attempt = 1; $attempt -le 40; $attempt++) {
            $securityState = Get-ContainerState "elt-openmetadata-security-init"
            if ($securityState -match '^exited::(?!0)') {
                throw "Falha ao configurar a senha do OpenMetadata. Consulte elt-openmetadata-security-init."
            }
            if ((Test-OpenMetadataHealth) -and $securityState -eq "exited::0") {
                Write-Output "OpenMetadata disponivel em http://localhost:$port"
                exit 0
            }
            Start-Sleep -Seconds 5
        }
        throw "OpenMetadata nao ficou saudavel no tempo esperado. Execute .\scripts\openmetadata\manage.ps1 status."
    }
    "stop" {
        Assert-Environment
        Invoke-Compose @("stop", "openmetadata-security-init", "openmetadata-server", "openmetadata-migrate", "openmetadata-elasticsearch", "openmetadata-postgres")
    }
    "status" {
        Assert-Environment
        Invoke-Compose @("ps", "-a")
    }
    "health" {
        Assert-Environment
        if (Test-OpenMetadataHealth) { Write-Output "healthy"; exit 0 }
        Write-Output "unhealthy"
        exit 1
    }
    "bootstrap" {
        Assert-Environment
        if (-not (Test-OpenMetadataHealth)) { throw "OpenMetadata indisponivel. Execute a acao start primeiro." }
        if ((Get-ContainerState "elt-airflow-webserver") -notmatch '^running:healthy:') {
            throw "Airflow webserver nao esta saudavel. Execute .\setup.ps1 primeiro."
        }
        if ((Get-ContainerState "elt-postgres") -notmatch '^running:healthy:') {
            throw "PostgreSQL ELT nao esta saudavel. Execute .\setup.ps1 primeiro."
        }
        Invoke-Compose @("--profile", "tools", "run", "--rm", "--no-deps", "openmetadata-bootstrap")
    }
}
