# ============================================================
# ELT Lab
# Sobe PostgreSQL, Airflow, MinIO, Jupyter e OpenMetadata via Docker
# ============================================================

param(
    [switch]$Down,
    [switch]$PurgeVolumes,
    [switch]$Force,
    [switch]$Logs,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Header($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function Assert-ExitCode([int]$ExitCode, [string]$Operation) {
    if ($ExitCode -ne 0) {
        throw "$Operation falhou com codigo $ExitCode."
    }
}

function Get-EnvValue([string]$Path, [string]$Name, [string]$Default) {
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $line) { return $Default }
    $value = ($line -split "=", 2)[1].Trim()
    if (-not $value) { return $Default }
    return $value
}

function Wait-HealthyContainer([string]$ContainerName, [int]$MaxRetries = 40) {
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        $health = docker inspect $ContainerName --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>$null
        if ($LASTEXITCODE -eq 0 -and $health -eq "healthy") { return }
        if ($health -eq "unhealthy" -or $health -eq "exited") {
            throw "$ContainerName entrou no estado $health."
        }
        Start-Sleep -Seconds 3
    }
    throw "$ContainerName nao ficou saudavel no tempo esperado."
}

function New-SecureString($length) {
    $lower = 'abcdefghijklmnopqrstuvwxyz'
    $upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    $digits = '0123456789'
    $special = '!'
    $chars = $lower + $upper + $digits + $special
    $bytes = New-Object byte[] $length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        $result = @($lower[$bytes[0] % $lower.Length], $upper[$bytes[1] % $upper.Length], $digits[$bytes[2] % $digits.Length], $special[0])
        for ($i = 4; $i -lt $length; $i++) {
            $result += $chars[$bytes[$i] % $chars.Length]
        }
        for ($i = $result.Count - 1; $i -gt 0; $i--) {
            $swapBytes = New-Object byte[] 1
            $rng.GetBytes($swapBytes)
            $j = $swapBytes[0] % ($i + 1)
            $tmp = $result[$i]
            $result[$i] = $result[$j]
            $result[$j] = $tmp
        }
        return -join $result
    } finally {
        $rng.Dispose()
    }
}

function New-SecureIdentifier($length) {
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    $bytes = New-Object byte[] $length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        $result = ''
        for ($i = 0; $i -lt $length; $i++) {
            $result += $chars[$bytes[$i] % $chars.Length]
        }
        return $result
    } finally {
        $rng.Dispose()
    }
}

function New-FernetKey {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    return [Convert]::ToBase64String($bytes)
}

# ---------- STATUS ----------
if ($Status) {
    Write-Header "Status dos containers"
    docker ps --filter "name=elt-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    Assert-ExitCode $LASTEXITCODE "docker ps"
    exit 0
}

# ---------- LOGS ----------
if ($Logs) {
    Write-Host "1) postgres  2) webserver  3) scheduler  4) minio  5) init  6) jupyter  7) openmetadata" -ForegroundColor Yellow
    $choice = Read-Host "Escolha"
    switch ($choice) {
        "1" { docker logs -f elt-postgres }
        "2" { docker logs -f elt-airflow-webserver }
        "3" { docker logs -f elt-airflow-scheduler }
        "4" { docker logs -f elt-minio }
        "5" { docker logs -f elt-airflow-init }
        "6" { docker logs -f elt-jupyter }
        "7" { docker logs -f elt-openmetadata-server }
        default { docker logs -f elt-postgres }
    }
    Assert-ExitCode $LASTEXITCODE "docker logs"
    exit 0
}

# ---------- PURGE VOLUMES ----------
if ($PurgeVolumes) {
    Write-Header "ATENCAO: Remover volumes"
    Write-Host "Isso ira apagar TODOS os dados dos containers:" -ForegroundColor Red
    Write-Host "  - elt-pgdata (PostgreSQL)" -ForegroundColor Yellow
    Write-Host "  - elt-miniodata (MinIO)" -ForegroundColor Yellow
    Write-Host "  - OpenMetadata PostgreSQL e Elasticsearch" -ForegroundColor Yellow
    Write-Host ""

    docker volume ls --filter "name=elt" --format "  - {{.Name}} ({{.Driver}})"
    Assert-ExitCode $LASTEXITCODE "docker volume ls"

    Write-Host ""
    if (-not $Force) {
        $confirm = Read-Host "Digite SIM para confirmar (qualquer outro valor cancela)"
        if ($confirm -ne "SIM") {
            Write-Host "Cancelado." -ForegroundColor Green
            exit 0
        }
    }

    Write-Header "Removendo containers e volumes"
    docker compose down -v
    Assert-ExitCode $LASTEXITCODE "docker compose down -v"
    Write-Host "Containers parados e volumes removidos." -ForegroundColor Green
    exit 0
}

# ---------- DOWN ----------
if ($Down) {
    Write-Header "Parando containers"
    docker compose down
    Assert-ExitCode $LASTEXITCODE "docker compose down"
    Write-Host "Containers parados (volumes preservados)." -ForegroundColor Green
    exit 0
}

# ---------- UP ----------

# Gerar .env se nao existir
$envFile = Join-Path $PSScriptRoot ".env"
$envExample = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Write-Header "Gerando .env com valores seguros"
        Copy-Item $envExample $envFile

        $pgPass = New-SecureString 24
        $airflowPass = New-SecureString 20
        $minioUser = New-SecureIdentifier 16
        $minioPass = New-SecureString 24
        $fernetKey = New-FernetKey
        $jupyterUser = "jovyan"
        $jupyterPass = New-SecureString 20
        $omDbPass = New-SecureString 32
        $omAdminPass = New-SecureString 24

        $lines = Get-Content $envFile
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '^POSTGRES_PASSWORD=')           { $lines[$i] = "POSTGRES_PASSWORD=$pgPass" }
            elseif ($lines[$i] -match '^AIRFLOW_ADMIN_PASSWORD=')  { $lines[$i] = "AIRFLOW_ADMIN_PASSWORD=$airflowPass" }
            elseif ($lines[$i] -match '^AIRFLOW_FERNET_KEY=')      { $lines[$i] = "AIRFLOW_FERNET_KEY=$fernetKey" }
            elseif ($lines[$i] -match '^MINIO_ROOT_USER=')         { $lines[$i] = "MINIO_ROOT_USER=$minioUser" }
            elseif ($lines[$i] -match '^MINIO_ROOT_PASSWORD=')     { $lines[$i] = "MINIO_ROOT_PASSWORD=$minioPass" }
            elseif ($lines[$i] -match '^MINIO_ACCESS_KEY=')        { $lines[$i] = "MINIO_ACCESS_KEY=$minioUser" }
            elseif ($lines[$i] -match '^MINIO_SECRET_KEY=')        { $lines[$i] = "MINIO_SECRET_KEY=$minioPass" }
            elseif ($lines[$i] -match '^JUPYTER_USERNAME=')        { $lines[$i] = "JUPYTER_USERNAME=$jupyterUser" }
            elseif ($lines[$i] -match '^JUPYTER_PASSWORD=')        { $lines[$i] = "JUPYTER_PASSWORD=$jupyterPass" }
            elseif ($lines[$i] -match '^OM_DB_PASSWORD=')          { $lines[$i] = "OM_DB_PASSWORD=$omDbPass" }
            elseif ($lines[$i] -match '^OM_ADMIN_PASSWORD=')       { $lines[$i] = "OM_ADMIN_PASSWORD=$omAdminPass" }
        }
        [System.IO.File]::WriteAllLines($envFile, $lines, [System.Text.UTF8Encoding]::new($false))

        Write-Host ".env criado em: $envFile" -ForegroundColor Green
        Write-Host "  POSTGRES_PASSWORD: gerado (24 caracteres)" -ForegroundColor DarkGray
        Write-Host "  AIRFLOW_ADMIN_PASSWORD: gerado (20 caracteres)" -ForegroundColor DarkGray
        Write-Host "  MINIO_ROOT_USER/ACCESS_KEY: gerado (16 caracteres)" -ForegroundColor DarkGray
        Write-Host "  MINIO_ROOT_PASSWORD/SECRET_KEY: gerado (24 caracteres)" -ForegroundColor DarkGray
        Write-Host "  AIRFLOW_FERNET_KEY: gerado" -ForegroundColor DarkGray
        Write-Host "  JUPYTER_USERNAME: $jupyterUser (identificador do usuario)" -ForegroundColor DarkGray
        Write-Host "  JUPYTER_PASSWORD: gerado (20 caracteres)" -ForegroundColor DarkGray
        Write-Host "  OM_DB_PASSWORD: gerado (32 caracteres)" -ForegroundColor DarkGray
        Write-Host "  OM_ADMIN_PASSWORD: gerado (24 caracteres)" -ForegroundColor DarkGray
        Write-Host "  (valores completos nao exibidos por seguranca)" -ForegroundColor DarkGray
    } else {
        Write-Host "ERRO: .env.example nao encontrado. Crie manualmente." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Header ".env ja existe - atualizando credenciais ausentes/vazias (idempotente)"
    $lines = Get-Content $envFile
    $changed = $false

    # Idempotente: acrescenta/atualiza somente o que esta ausente ou vazio.
    # Nunca substitui credenciais existentes.

    # JUPYTER_PORT: default 8888 quando ausente ou vazio
    $hasPortLine = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^JUPYTER_PORT=') {
            $hasPortLine = $true
            if ($lines[$i] -match '^JUPYTER_PORT=\s*$') {
                $lines[$i] = "JUPYTER_PORT=8888"
                $changed = $true
                Write-Host "  JUPYTER_PORT: preenchido com 8888 (estava vazio)" -ForegroundColor Yellow
            }
        }
    }
    if (-not $hasPortLine) {
        $lines += "JUPYTER_PORT=8888"
        $changed = $true
        Write-Host "  JUPYTER_PORT: adicionado (ausente no .env)" -ForegroundColor Yellow
    }

    # JUPYTER_USERNAME: default jovyan quando ausente ou vazio
    $hasUsernameLine = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^JUPYTER_USERNAME=') {
            $hasUsernameLine = $true
            if ($lines[$i] -match '^JUPYTER_USERNAME=\s*$') {
                $lines[$i] = "JUPYTER_USERNAME=jovyan"
                $changed = $true
                Write-Host "  JUPYTER_USERNAME: preenchido com jovyan (estava vazio)" -ForegroundColor Yellow
            }
        }
    }
    if (-not $hasUsernameLine) {
        $lines += "JUPYTER_USERNAME=jovyan"
        $changed = $true
        Write-Host "  JUPYTER_USERNAME: adicionado como jovyan (ausente no .env)" -ForegroundColor Yellow
    }

    # JUPYTER_PASSWORD: gera quando ausente ou vazia; nunca sobrescreve valor definido
    $hasPasswordLine = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^JUPYTER_PASSWORD=') {
            $hasPasswordLine = $true
            if ($lines[$i] -match '^JUPYTER_PASSWORD=\s*$') {
                $newPass = New-SecureString 20
                $lines[$i] = "JUPYTER_PASSWORD=$newPass"
                $changed = $true
                Write-Host "  JUPYTER_PASSWORD: gerado (20 caracteres, estava vazio)" -ForegroundColor Yellow
            } else {
                Write-Host "  JUPYTER_PASSWORD: preservado (ja definido)" -ForegroundColor DarkGray
            }
        }
    }
    if (-not $hasPasswordLine) {
        $newPass = New-SecureString 20
        $lines += "JUPYTER_PASSWORD=$newPass"
        $changed = $true
        Write-Host "  JUPYTER_PASSWORD: gerado (20 caracteres, estava ausente)" -ForegroundColor Yellow
    }

    $openMetadataValues = @{
        "OPENMETADATA_PORT" = "8585"
        "OM_DB_PASSWORD" = (New-SecureString 32)
        "OM_ADMIN_PASSWORD" = (New-SecureString 24)
    }
    foreach ($name in $openMetadataValues.Keys) {
        $found = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^$name=") {
                $found = $true
                if ($lines[$i] -match "^$name=\s*$") {
                    $lines[$i] = "$name=$($openMetadataValues[$name])"
                    $changed = $true
                    Write-Host "  ${name}: preenchido (estava vazio)" -ForegroundColor Yellow
                }
            }
        }
        if (-not $found) {
            $lines += "$name=$($openMetadataValues[$name])"
            $changed = $true
            Write-Host "  ${name}: adicionado" -ForegroundColor Yellow
        }
    }

    if ($changed) {
        [System.IO.File]::WriteAllLines($envFile, $lines, [System.Text.UTF8Encoding]::new($false))
        Write-Host ".env atualizado (valores completos nao exibidos por seguranca)." -ForegroundColor Green
    } else {
        Write-Host ".env preservado sem alteracoes." -ForegroundColor Green
    }
}

$legacyContainers = docker ps -a --filter "label=com.docker.compose.project=elt-openmetadata" --format "{{.Names}}"
Assert-ExitCode $LASTEXITCODE "deteccao da stack OpenMetadata legada"
if ($legacyContainers) {
    throw "Stack legada elt-openmetadata detectada. Consulte a secao de upgrade do README; os volumes nao foram alterados."
}

Write-Header "Subindo PostgreSQL + MinIO no projeto Docker elt"
$ErrorActionPreferenceOld = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose up -d --build postgres minio
$composeExitCode = $LASTEXITCODE
$ErrorActionPreference = $ErrorActionPreferenceOld
Assert-ExitCode $composeExitCode "docker compose up (PostgreSQL e MinIO)"

Write-Header "Aguardando PostgreSQL ficar pronto"
$maxRetries = 30
$retry = 0
while ($retry -lt $maxRetries) {
    $postgresUser = Get-EnvValue $envFile "POSTGRES_USER" "elt"
    $ready = docker exec elt-postgres pg_isready -U $postgresUser 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PostgreSQL pronto!" -ForegroundColor Green
        break
    }
    $retry++
    Write-Host "  Aguardando... ($retry/$maxRetries)"
    Start-Sleep -Seconds 2
}

if ($retry -eq $maxRetries) {
    Write-Host "ERRO: PostgreSQL nao ficou pronto a tempo." -ForegroundColor Red
    exit 1
}

Write-Header "Atualizando configuracao reproduzivel do pipeline demonstrativo"
$municipiosUrl = "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/975a51d6f2e7a9ee22a734a42ebd624263812f0c/csv/municipios.csv"
docker exec elt-postgres psql -U $postgresUser -d elt -v ON_ERROR_STOP=1 -c "UPDATE global.schedule SET url='$municipiosUrl' WHERE projeto='municipios_ibge' AND layer='bronze';"
Assert-ExitCode $LASTEXITCODE "atualizacao da fonte do pipeline demonstrativo"

Write-Header "Construindo imagens do Airflow e Jupyter"
docker compose build airflow-init airflow-webserver airflow-scheduler jupyter
Assert-ExitCode $LASTEXITCODE "docker compose build"

Write-Header "Subindo Airflow + Jupyter + OpenMetadata"
$ErrorActionPreferenceOld = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose up -d --no-build
$composeExitCode = $LASTEXITCODE
$ErrorActionPreference = $ErrorActionPreferenceOld
Assert-ExitCode $composeExitCode "docker compose up"

Write-Header "Aguardando Airflow init completar"
$maxRetries = 60
$retry = 0
while ($retry -lt $maxRetries) {
    $state = docker inspect elt-airflow-init --format '{{.State.Status}}:{{.State.ExitCode}}' 2>$null
    if ($state -eq "exited:0") {
        Write-Host "Airflow init pronto!" -ForegroundColor Green
        break
    }
    if ($state -match '^exited:(?!0)') {
        $ErrorActionPreferenceOld = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        docker logs elt-airflow-init
        $ErrorActionPreference = $ErrorActionPreferenceOld
        Write-Host "ERRO: Airflow init falhou." -ForegroundColor Red
        exit 1
    }
    $retry++
    Write-Host "  Aguardando... ($retry/$maxRetries)"
    Start-Sleep -Seconds 3
}

if ($retry -eq $maxRetries) {
    Write-Host "ERRO: Airflow init nao concluiu no tempo esperado." -ForegroundColor Red
    exit 1
}

Write-Header "Aguardando OpenMetadata e rotacao da senha administrativa"
$maxRetries = 80
$retry = 0
while ($retry -lt $maxRetries) {
    $state = docker inspect elt-openmetadata-security-init --format '{{.State.Status}}:{{.State.ExitCode}}' 2>$null
    if ($state -eq "exited:0") {
        Write-Host "OpenMetadata pronto com senha segura!" -ForegroundColor Green
        break
    }
    if ($state -match '^exited:(?!0)') {
        docker logs elt-openmetadata-security-init
        Write-Host "ERRO: falha ao configurar a senha do OpenMetadata." -ForegroundColor Red
        exit 1
    }
    $retry++
    Write-Host "  Aguardando... ($retry/$maxRetries)"
    Start-Sleep -Seconds 5
}

if ($retry -eq $maxRetries) {
    Write-Host "ERRO: OpenMetadata nao ficou pronto a tempo." -ForegroundColor Red
    exit 1
}

Write-Header "Aguardando interfaces ficarem saudaveis"
Wait-HealthyContainer "elt-airflow-webserver"
Wait-HealthyContainer "elt-jupyter"
Write-Host "Airflow e Jupyter prontos!" -ForegroundColor Green

Write-Header "Status final"
docker ps --filter "name=elt-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
Assert-ExitCode $LASTEXITCODE "docker ps"

$openMetadataPort = Get-EnvValue $envFile "OPENMETADATA_PORT" "8585"
$airflowPort = Get-EnvValue $envFile "AIRFLOW_PORT" "8080"
$minioConsolePort = Get-EnvValue $envFile "MINIO_CONSOLE_PORT" "9001"
$postgresPort = Get-EnvValue $envFile "POSTGRES_PORT" "5432"
$jupyterPort = Get-EnvValue $envFile "JUPYTER_PORT" "8888"

Write-Host "`nSetup concluido!" -ForegroundColor Green
Write-Host ""
Write-Host "  Airflow:     http://localhost:$airflowPort" -ForegroundColor Cyan
Write-Host "  MinIO:       http://localhost:$minioConsolePort" -ForegroundColor Cyan
Write-Host "  PostgreSQL:  localhost:$postgresPort" -ForegroundColor Cyan
Write-Host "  JupyterLab:  http://localhost:$jupyterPort  (senha no .env)" -ForegroundColor Cyan
Write-Host "  OpenMetadata: http://localhost:$openMetadataPort  (senha no .env)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Credenciais estao no arquivo .env" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Commands uteis:" -ForegroundColor Yellow
Write-Host "  .\setup.ps1                # Subir tudo"
Write-Host "  .\setup.ps1 -Down          # Parar (volumes preservados)"
Write-Host "  .\setup.ps1 -PurgeVolumes  # Parar e apagar dados"
Write-Host "  .\setup.ps1 -Status        # Ver status"
Write-Host "  .\setup.ps1 -Logs          # Ver logs"
