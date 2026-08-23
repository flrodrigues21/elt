# ============================================================
# ELT Lab
# Sobe PostgreSQL + Airflow + MinIO via Docker
# ============================================================

param(
    [switch]$Down,
    [switch]$PurgeVolumes,
    [switch]$Force,
    [switch]$Logs,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

function Write-Header($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function New-SecureString($length) {
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#^&*()-_=+'
    $bytes = New-Object byte[] $length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $s = ''
    for ($i = 0; $i -lt $length; $i++) {
        $s += $chars[$bytes[$i] % $chars.Length]
    }
    return $s
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
    exit 0
}

# ---------- LOGS ----------
if ($Logs) {
    Write-Host "1) postgres  2) webserver  3) scheduler  4) minio  5) init  6) jupyter" -ForegroundColor Yellow
    $choice = Read-Host "Escolha"
    switch ($choice) {
        "1" { docker logs -f elt-postgres }
        "2" { docker logs -f elt-airflow-webserver }
        "3" { docker logs -f elt-airflow-scheduler }
        "4" { docker logs -f elt-minio }
        "5" { docker logs -f elt-airflow-init }
        "6" { docker logs -f elt-jupyter }
        default { docker logs -f elt-postgres }
    }
    exit 0
}

# ---------- PURGE VOLUMES ----------
if ($PurgeVolumes) {
    Write-Header "ATENCAO: Remover volumes"
    Write-Host "Isso ira apagar TODOS os dados dos containers:" -ForegroundColor Red
    Write-Host "  - elt-pgdata (PostgreSQL)" -ForegroundColor Yellow
    Write-Host "  - elt-miniodata (MinIO)" -ForegroundColor Yellow
    Write-Host ""

    docker volume ls --filter "name=elt-" --format "  - {{.Name}} ({{.Driver}})"

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
    Write-Host "Containers parados e volumes removidos." -ForegroundColor Green
    exit 0
}

# ---------- DOWN ----------
if ($Down) {
    Write-Header "Parando containers"
    docker compose down
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
        $minioUser = New-SecureString 16
        $minioPass = New-SecureString 24
        $fernetKey = New-FernetKey
        $jupyterUser = "jovyan"
        $jupyterPass = New-SecureString 20

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
        }
        $lines | Set-Content $envFile

        Write-Host ".env criado em: $envFile" -ForegroundColor Green
        Write-Host "  POSTGRES_PASSWORD: gerado (24 caracteres)" -ForegroundColor DarkGray
        Write-Host "  AIRFLOW_ADMIN_PASSWORD: gerado (20 caracteres)" -ForegroundColor DarkGray
        Write-Host "  MINIO_ROOT_USER/ACCESS_KEY: gerado (16 caracteres)" -ForegroundColor DarkGray
        Write-Host "  MINIO_ROOT_PASSWORD/SECRET_KEY: gerado (24 caracteres)" -ForegroundColor DarkGray
        Write-Host "  AIRFLOW_FERNET_KEY: gerado" -ForegroundColor DarkGray
        Write-Host "  JUPYTER_USERNAME: $jupyterUser (identificador do usuario)" -ForegroundColor DarkGray
        Write-Host "  JUPYTER_PASSWORD: gerado (20 caracteres)" -ForegroundColor DarkGray
        Write-Host "  (valores completos nao exibidos por seguranca)" -ForegroundColor DarkGray
    } else {
        Write-Host "ERRO: .env.example nao encontrado. Crie manualmente." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host ".env ja existe, preservando valores existentes." -ForegroundColor DarkGray
}

Write-Header "Subindo PostgreSQL + Airflow + MinIO via Docker"
$ErrorActionPreferenceOld = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose up -d --build postgres minio
$ErrorActionPreference = $ErrorActionPreferenceOld

Write-Header "Aguardando PostgreSQL ficar pronto"
$maxRetries = 30
$retry = 0
while ($retry -lt $maxRetries) {
    $ready = docker exec elt-postgres pg_isready -U elt 2>$null
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

Write-Header "Subindo Airflow (init, webserver, scheduler)"
$ErrorActionPreferenceOld = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose up -d --no-build
$ErrorActionPreference = $ErrorActionPreferenceOld

Write-Header "Aguardando Airflow init completar"
$maxRetries = 60
$retry = 0
while ($retry -lt $maxRetries) {
    $logs = docker logs elt-airflow-init 2>&1
    if ($logs -match "Init completo") {
        Write-Host "Airflow init pronto!" -ForegroundColor Green
        break
    }
    $retry++
    Write-Host "  Aguardando... ($retry/$maxRetries)"
    Start-Sleep -Seconds 3
}

if ($retry -eq $maxRetries) {
    Write-Host "AVISO: Airflow init pode ainda estar rodando. Verifique com .\setup.ps1 -Logs" -ForegroundColor Yellow
}

Write-Header "Status final"
docker ps --filter "name=elt-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`nSetup concluido!" -ForegroundColor Green
Write-Host ""
Write-Host "  Airflow:     http://localhost:8080" -ForegroundColor Cyan
Write-Host "  MinIO:       http://localhost:9001" -ForegroundColor Cyan
Write-Host "  PostgreSQL:  localhost:5432" -ForegroundColor Cyan
Write-Host "  JupyterLab:  http://localhost:8888  (senha no .env)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Credenciais estao no arquivo .env" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Commands uteis:" -ForegroundColor Yellow
Write-Host "  .\setup.ps1                # Subir tudo"
Write-Host "  .\setup.ps1 -Down          # Parar (volumes preservados)"
Write-Host "  .\setup.ps1 -PurgeVolumes  # Parar e apagar dados"
Write-Host "  .\setup.ps1 -Status        # Ver status"
Write-Host "  .\setup.ps1 -Logs          # Ver logs"
