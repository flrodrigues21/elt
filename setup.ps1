# ============================================================
# ELT Lab
# Sobe PostgreSQL + Airflow + MinIO via Docker
# ============================================================

param(
    [switch]$Down,
    [switch]$Logs,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

function Write-Header($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
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

# ---------- DOWN ----------
if ($Down) {
    Write-Header "Parando containers"
    docker compose down -v
    Write-Host "Containers parados e volumes removidos." -ForegroundColor Green
    exit 0
}

# ---------- UP ----------
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
Write-Host "  Airflow:     http://localhost:8080  (admin / admin)" -ForegroundColor Cyan
Write-Host "  MinIO:       http://localhost:9001  (minioadmin / minioadmin)" -ForegroundColor Cyan
Write-Host "  PostgreSQL:  localhost:5432         (elt / elt123)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Bancos:" -ForegroundColor Yellow
Write-Host "  elt      -> controle (schedule + controle_execucao)"
Write-Host "  bronze   -> dados brutos (extracao)"
Write-Host "  silver   -> transformacao/limpeza"
Write-Host "  gold     -> modelo dimensional"
Write-Host ""
Write-Host "Commands uteis:" -ForegroundColor Yellow
Write-Host "  .\setup.ps1          # Subir tudo"
Write-Host "  .\setup.ps1 -Down    # Parar tudo"
Write-Host "  .\setup.ps1 -Status  # Ver status"
Write-Host "  .\setup.ps1 -Logs    # Ver logs"
