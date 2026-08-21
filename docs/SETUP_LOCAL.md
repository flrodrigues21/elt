# Setup Local - ELT Lab

Guia completo para subir o ambiente de desenvolvimento local do framework ELT.

## Pre-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e rodando
- ~4GB de RAM livre para os containers
- Portas `5432` (PostgreSQL) e `8080` (Airflow) disponíveis

## Arquitetura Local

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Desktop                       │
│                                                          │
│  ┌──────────────────┐    ┌──────────────────────────┐   │
│  │   elt-postgres    │    │      elt-airflow          │   │
│  │   PostgreSQL 16   │    │   Airflow 2.9 + API      │   │
│  │                    │    │                          │   │
│  │  elt    (banco)    │◄───│  elt_schedule (conn)     │   │
│  │    └─ global.*     │    │    schedule + controle   │   │
│  │  bronze (banco)    │◄───│  elt_bronze  (conn)      │   │
│  │  silver (banco)    │◄───│  elt_silver  (conn)      │   │
│  │  gold   (banco)    │◄───│  elt_gold    (conn)      │   │
│  │    └─ global.*     │    │                          │   │
│  └──────────────────┘    └──────────────────────────┘   │
│         :5432                    :8080                    │
└─────────────────────────────────────────────────────────┘
```

## Inicio Rapido

### 1. Clonar e configurar

```powershell
# Se ainda nao clonou
git clone https://github.com/flrodrigues21/elt
cd elt

# Copiar .env (ja criado no setup)
# O .env ja deve existir com as credenciais padrao
```

### 2. Subir tudo

```powershell
.\setup.ps1
```

Isso vai:
- Baixar a imagem PostgreSQL 16
- Criar os 4 bancos: `elt`, `bronze`, `silver`, `gold`
- Criar schemas e tabelas de controle (`elt.global.schedule`, `elt.global.controle_execucao`)
- Inserir dados de exemplo na tabela schedule
- Subir Airflow com as connections configuradas

### 3. Verificar

```powershell
# Status dos containers
.\setup.ps1 -Status

# Logs do PostgreSQL
.\setup.ps1 -Logs

# Logs do Airflow
docker logs -f elt-airflow-webserver
```

## URLs e Credenciais

| Servico | URL | Usuario | Senha |
|---------|-----|---------|-------|
| PostgreSQL | `localhost:5432` | `elt` | `elt123` |
| Airflow | `http://localhost:8080` | `admin` | `admin` |

## Bancos de Dados

| Banco | Camada | Descricao |
|-------|--------|-----------|
| `bronze` | Bronze | Dados brutos extraidos das fontes |
| `silver` | Silver | Dados transformados e limpos |
| `gold` | Gold | Modelo dimensional + tabela de controle |

### Schemas

Cada banco possui o schema `global`:
- `elt.global.schedule` - Tabela de parametrizacao do ELT
- `elt.global.controle_execucao` - Log de execucoes

## Connections do Airflow

| Connection ID | Tipo | Host | Database | User |
|---------------|------|------|----------|------|
| `elt_bronze` | Postgres | elt-postgres | bronze | elt |
| `elt_silver` | Postgres | elt-postgres | silver | elt |
| `elt_gold` | Postgres | elt-postgres | gold | elt |

## Comandos Uteis

### Gerenciar containers

```powershell
# Subir
.\setup.ps1

# Parar (remove containers e volumes)
.\setup.ps1 -Down

# Status
.\setup.ps1 -Status

# Logs
.\setup.ps1 -Logs
```

### Acessar PostgreSQL

```powershell
# Shell do container
docker exec -it elt-postgres psql -U elt

# Listar bancos
docker exec elt-postgres psql -U elt -l

# Consultar schedule
docker exec elt-postgres psql -U elt -d gold -c "SELECT * FROM global.schedule;"

# Consultar execucoes
docker exec elt-postgres psql -U elt -d gold -c "SELECT * FROM global.controle_execucao ORDER BY id DESC LIMIT 10;"
```

### Acessar Airflow

```powershell
# Listar DAGs
docker exec elt-airflow-webserver airflow dags list

# Listar connections
docker exec elt-airflow-webserver airflow connections list

# Testar connection
docker exec elt-airflow-webserver airflow connections test elt_gold
```

## Pipeline ELT

### Fluxo dos dados

```
Fonte de dados (Google Sheets, CSV, FTP, etc.)
         │
         ▼
    ┌─────────┐
    │ BRONZE  │  Extracao crua -> bronze.global.*
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │ SILVER  │  Transformacao SQL -> silver.global.*
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │  GOLD   │  Modelo dimensional -> gold.global.*
    └─────────┘
```

### Como funciona

1. A tabela `global.schedule` define cada step do pipeline
2. Cada step indica: fonte, query, destino, estrategia (truncate/append)
3. O Airflow executa bronze → silver → gold para cada projeto
4. DAGs sao geradas dinamicamente baseadas no `schedule_cron`

### Inserir novo projeto

```sql
-- 1. Bronze: extracao de um CSV
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_source, table_destiny,
 schema_destiny, strategy_destiny)
VALUES
('CSV_URL', 'bronze', 'meu_projeto', 1, TRUE,
 '0 6 * * 1',
 'https://exemplo.com/dados.csv',
 'dados', 'tb_meus_dados',
 'global', 'truncate');

-- 2. Silver: transformacao
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'silver', 'meu_projeto', 1, TRUE,
 '0 6 * * 1',
 'bronze', 'global',
 'SELECT * FROM global.tb_meus_dados WHERE ativo = true',
 'tb_meus_dados_tratados', 'global', 'truncate');

-- 3. Gold: dimensional
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'gold', 'meu_projeto', 1, TRUE,
 '0 6 * * 1',
 'silver', 'global',
 'SELECT DISTINCT categoria FROM global.tb_meus_dados_tratados',
 'dm_categoria', 'global', 'append');
```

## Solucao de Problemas

### PostgreSQL nao inicia
- Verifique se a porta 5432 nao esta em uso: `netstat -ano | findstr :5432`
- Reinicie o Docker Desktop

### Airflow nao conecta ao banco
- Verifique se o container esta rodando: `docker ps`
- Verifique as connections: `docker exec elt-airflow-webserver airflow connections list`
- Teste a connection: `docker exec elt-airflow-webserver airflow connections test elt_gold`

### DAGs nao aparecem no Airflow
- Verifique se o codigo esta mapeado corretamente no container
- Verifique os logs: `docker logs elt-airflow-webserver`
- Force refresh: `docker exec elt-airflow-webserver airflow dags list`

### Resetar tudo
```powershell
.\setup.ps1 -Down
.\setup.ps1
```
