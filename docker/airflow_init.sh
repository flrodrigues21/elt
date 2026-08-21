#!/bin/bash
set -e

echo "=== Configurando Connections do Airflow ==="

# Deletar connections existentes (idempotente)
airflow connections get elt_bronze > /dev/null 2>&1 && airflow connections delete elt_bronze || true
airflow connections get elt_silver > /dev/null 2>&1 && airflow connections delete elt_silver || true
airflow connections get elt_gold > /dev/null 2>&1 && airflow connections delete elt_gold || true
airflow connections get elt_schedule > /dev/null 2>&1 && airflow connections delete elt_schedule || true

# elt_bronze
airflow connections add elt_bronze \
    --conn-type postgres \
    --conn-host elt-postgres \
    --conn-schema bronze \
    --conn-login elt \
    --conn-password elt123 \
    --conn-port 5432 \
    --conn-description "PostgreSQL Bronze - dados brutos"

# elt_silver
airflow connections add elt_silver \
    --conn-type postgres \
    --conn-host elt-postgres \
    --conn-schema silver \
    --conn-login elt \
    --conn-password elt123 \
    --conn-port 5432 \
    --conn-description "PostgreSQL Silver - transformacao"

# elt_gold
airflow connections add elt_gold \
    --conn-type postgres \
    --conn-host elt-postgres \
    --conn-schema gold \
    --conn-login elt \
    --conn-password elt123 \
    --conn-port 5432 \
    --conn-description "PostgreSQL Gold - dimensional"

# elt_schedule (controle: schedule + controle_execucao)
airflow connections add elt_schedule \
    --conn-type postgres \
    --conn-host elt-postgres \
    --conn-schema elt \
    --conn-login elt \
    --conn-password elt123 \
    --conn-port 5432 \
    --conn-description "PostgreSQL ELT - schedule e controle_execucao"

echo "=== Connections configuradas com sucesso ==="
airflow connections list

echo "=== Criando usuario admin ==="
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com || true

echo "=== Setup completo ==="
