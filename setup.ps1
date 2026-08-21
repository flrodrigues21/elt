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
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+'
    $s = ''
    for ($i = 0; $i -lt $length; $i++) {
        $s += $chars[(Get-Random -Maximum $chars.Length)]
    }
    return $s
}

function New-FernetKey {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
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
    Write-Host "1) postgres  2) webserver  3) scheduler  4) minio  5) init" -ForegroundColor Yellow
    $choice = Read-Host "Escolha"
    switch ($choice) {
        "1" { docker logs -f elt-postgres }
        "2" { docker logs -f elt-airflow-webserver }
        "3" { docker logs -f elt-airflow-scheduler }
        "4" { docker logs -f elt-minio }
        "5" { docker logs -f elt-airflow-init }
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
        $fernetKey = New-FernetKey

        $content = Get-Content $envFile -Raw
        $content = $content -replace '(?m)^POSTGRES_PASSWORD=$', "POSTGRES_PASSWORD=$pgPass"
        $content = $content -replace '(?m)^AIRFLOW_ADMIN_PASSWORD=$', "AIRFLOW_ADMIN_PASSWORD=$airflowPass"
        $content = $content -replace '(?m)^AIRFLOW_FERNET_KEY=$', "AIRFLOW_FERNET_KEY=$fernetKey"
        Set-Content $envFile -Value $content -NoNewline

        Write-Host ".env criado em: $envFile" -ForegroundColor Green
        Write-Host "  POSTGRES_PASSWORD: gerado (24 caracteres)" -ForegroundColor DarkGray
        Write-Host "  AIRFLOW_ADMIN_PASSWORD: gerado (20 caracteres)" -ForegroundColor DarkGray
        Write-Host "  AIRFLOW_FERNET_KEY: gerado" -ForegroundColor DarkGray
        Write-Host "  (valores completos nao exibidos por seguranca)" -ForegroundColor DarkGray
    } else {
        Write-Host "ERRO: .env.example nao encontrado. Crie manualmente." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host ".env ja existe, preservando valores existentes." -ForegroundColor DarkGray
}

Write-Header "Subindo PostgreSQL + Airflow + MinIO via Docker"
docker compose up -d --build

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
Write-Host ""
Write-Host "Credenciais estao no arquivo .env" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Commands uteis:" -ForegroundColor Yellow
Write-Host "  .\setup.ps1                # Subir tudo"
Write-Host "  .\setup.ps1 -Down          # Parar (volumes preservados)"
Write-Host "  .\setup.ps1 -PurgeVolumes  # Parar e apagar dados"
Write-Host "  .\setup.ps1 -Status        # Ver status"
Write-Host "  .\setup.ps1 -Logs          # Ver logs"
