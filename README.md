# ELT Lab

Ambiente local de ELT (Extract, Load, Transform) com **Apache Airflow**, **MinIO** e **PostgreSQL** via Docker.

Basta clonar e rodar `.\setup.ps1` para ter o lab completo funcionando.

---

## Credenciais & URLs

| Servico | URL | Usuario | Senha |
|---------|-----|---------|-------|
| **Airflow** | http://localhost:8080 | `admin` | `admin` |
| **MinIO Console** | http://localhost:9001 | `minioadmin` | `minioadmin` |
| **PostgreSQL** | `localhost:5432` | `elt` | `elt123` |

---

## Setup (3 passos)

```powershell
# 1. Clonar
git clone https://github.com/flrodrigues21/elt.git
cd elt

# 2. Subir tudo
.\setup.ps1

# 3. Rodar o pipeline
# Abra http://localhost:8080, ative e execute a DAG elt_municipios_ibge
```

**Prerequisitos:** Docker Desktop instalado e rodando, ~4GB RAM livre.

**O que sobe:**
- PostgreSQL (porta 5432) -- 5 bancos: `elt`, `bronze`, `silver`, `gold`, `airflow`
- Airflow webserver (porta 8080) + scheduler
- MinIO (porta 9000 API / 9001 Console) -- datalake em parquet

**Commands uteis:**
```powershell
.\setup.ps1          # Subir tudo
.\setup.ps1 -Down    # Parar tudo e limpar volumes
.\setup.ps1 -Status  # Ver status dos containers
.\setup.ps1 -Logs    # Ver logs (escolhe container)
```

---

## Arquitetura

```
                    elt.global.schedule (tabela de controle)
                                  |
            +---------------------+----------------------+
            |                     |                      |
       load_bronze          load_silver            load_gold
       (extratores)      (transformacoes SQL)   (modelo dimensional)
            |                     |                      |
       GOOGLE SHEETS           DW query               DW query
       XLSX                    -> silver               -> gold
       FTP / DATASUS
       S3 / CKAN / CSV_URL
       Oracle
       PostgreSQL
       MinIO
       API REST
```

### Camadas (Medallion Architecture)

| Camada | Descricao | Destino |
|--------|-----------|---------|
| **Bronze** | Extracao de dados brutos de fontes heterogeneas | PostgreSQL `bronze` ou MinIO (parquet) |
| **Silver** | Transformacao/limpeza via queries SQL | PostgreSQL `silver` ou MinIO (parquet) |
| **Gold** | Modelo dimensional (dimensoes e fatos) | PostgreSQL `gold` ou MinIO (parquet) |
| **Controle** | Tabela de schedule e log de execucoes | PostgreSQL `elt` |

> Cada camada pode gravar em **PostgreSQL** (padrao) ou **MinIO** (parquet), basta configurar via `config` na tabela `schedule`.

### Bancos de Dados

| Banco | Funcao | Schema |
|-------|--------|--------|
| `elt` | Controle do framework | `global.schedule`, `global.controle_execucao` |
| `bronze` | Dados brutos (extracao) | `global.*` |
| `silver` | Dados transformados | `global.*` |
| `gold` | Modelo dimensional | `global.*` |
| `airflow` | Metadados do Airflow | `airflow_*` |

## Inicio Rapido (Docker)

### Pre-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e rodando
- ~4GB de RAM livre
- Portas `5432` (PostgreSQL), `8080` (Airflow), `9000`/`9001` (MinIO) disponiveis

### 1. Subir tudo

```powershell
.\setup.ps1
```

Ou manualmente:

```powershell
docker compose up -d --build
```

Isso vai:
- Criar os 4 bancos: `elt`, `bronze`, `silver`, `gold`
- Criar schemas e tabelas de controle no banco `elt`
- Inserir dados de exemplo (Municipios Brasileiros IBGE)
- Subir Airflow com as connections configuradas
- Criar usuario `admin` / `admin`

### 2. Acessar

- **Airflow:** http://localhost:8080 (admin / admin)
- **MinIO Console:** http://localhost:9001 (minioadmin / minioadmin)
- **PostgreSQL:** localhost:5432 (user: `elt`, password: `elt123`)

### 3. Rodar o pipeline

No Airflow, ative e execute a DAG `elt_municipios_ibge`.

## Estrutura do Projeto

```
elt/
├ main.py                     # DAG Airflow (geracao dinamica)
├ controller/                 # Orquestracao
│  ├── load_bronze.py
│  ├── load_silver.py
│  ├── load_gold.py
│  └── dags.py                # Notificacao por email
├ models/
│  ├── bronze/extract.py      # Extrator generico
│  ├── silver/transform.py    # Transformacao generica
│  └── gold/transform.py      # Modelo dimensional generico
├ src/
│  ├── schedule/              # Leitura da tabela de controle
│  ├── connectors/            # Conectores de banco e servicos
│  │   ├── postgres_connector.py
│  │   ├── oracle_connector.py
│  │   ├── minio_connector.py
│  │   └── airflow_connections.py
│  ├── extractors/            # Extratores registraveis
│  │   ├── base.py
│  │   ├── google_sheets.py
│  │   ├── xlsx.py
│  │   ├── oracle.py
│  │   ├── postgres.py
│  │   ├── minio.py
│  │   ├── ftp.py
│  │   ├── s3.py
│  │   └── api.py
│  └── historics/             # SCD Tipo 2
├ sql/init/                   # Scripts de inicializacao do banco
├ docker/
│  ├── Dockerfile.airflow
│  ├── airflow_init.sh
│  └── requirements-airflow.txt
├ docker-compose.yml
├ .env
└ utils/
```

## Como Usar

### 1. Tabela de schedule

A tabela `elt.global.schedule` e o coracao do framework. Cada linha define um step de extracao ou transformacao.

```sql
SELECT id, type_source, layer, projeto, table_destiny, schedule_cron
FROM elt.global.schedule
WHERE ativo = TRUE
ORDER BY projeto, layer, ordem;
```

### 2. Connections no Airflow

| Connection ID | Banco | Descricao |
|---------------|-------|-----------|
| `elt_bronze` | bronze | Extracao de dados |
| `elt_silver` | silver | Transformacao |
| `elt_gold` | gold | Modelo dimensional |
| `elt_schedule` | elt | Schedule + controle_execucao |
| `google_sheets` | - | Service account (se necessario) |
| `minio` | - | Credenciais MinIO (se utilizado) |

### 3. Registrar novo projeto

Cada projeto precisa de ao menos um INSERT por camada (bronze, silver, gold):

```sql
-- Bronze: extracao de CSV
INSERT INTO elt.global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_source, table_destiny,
 schema_destiny, strategy_destiny,
 config)
VALUES
('CSV_URL', 'bronze', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'https://exemplo.com/dados.csv',
 'dados', 'minha_tabela',
 'global', 'truncate',
 '{"delimiter": ",", "encoding": "utf-8"}');

-- Silver: transformacao SQL
INSERT INTO elt.global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'silver', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'bronze', 'global',
 'SELECT * FROM global.minha_tabela WHERE coluna = valor',
 'minha_tabela_tratada', 'global', 'truncate');

-- Gold: modelo dimensional
INSERT INTO elt.global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'gold', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'silver', 'global',
 'SELECT categoria, COUNT(*) AS total FROM global.minha_tabela_tratada GROUP BY categoria',
 'dm_categoria', 'global', 'truncate');
```

### Usando MinIO em vez de PostgreSQL

Para gravar uma camada como **parquet no MinIO**, adicione `"minio"` no `config`:

```sql
-- Bronze: gravar no MinIO
INSERT INTO elt.global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_destiny, schema_destiny, strategy_destiny,
 config)
VALUES
('CSV_URL', 'bronze', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'https://exemplo.com/dados.csv',
 'minha_tabela', 'global', 'truncate',
 '{"minio": {"bucket": "elt-datalake", "format": "parquet", "object_name": "bronze/minha_tabela.parquet"}}');
```

Para **ler de MinIO** (em vez de SQL) no silver/gold, use `"minio_source"`:

```sql
-- Silver: ler do MinIO e gravar no PostgreSQL
INSERT INTO elt.global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 table_destiny, schema_destiny, strategy_destiny,
 config)
VALUES
('DW', 'silver', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'minha_tabela_tratada', 'global', 'truncate',
 '{"minio_source": {"bucket": "elt-datalake", "format": "parquet", "object_name": "bronze/minha_tabela.parquet"}}');
```

**Fluxo flexivel por camada:**

| Camada | Origem | Destino | Config |
|--------|--------|---------|--------|
| Bronze | Qualquer fonte | PostgreSQL (padrao) | Sem config |
| Bronze | Qualquer fonte | MinIO | `config.minio` |
| Silver | PostgreSQL (SQL) | PostgreSQL (padrao) | Sem config |
| Silver | MinIO (parquet) | PostgreSQL | `config.minio_source` |
| Silver | PostgreSQL | MinIO | `config.minio` |
| Gold | PostgreSQL (SQL) | PostgreSQL (padrao) | Sem config |
| Gold | MinIO (parquet) | PostgreSQL | `config.minio_source` |
| Gold | PostgreSQL | MinIO | `config.minio` |

### 4. DAGs geradas automaticamente

O Airflow cria automaticamente uma DAG para cada projeto com `schedule_cron` preenchido:

| Projeto | DAG gerada | Schedule |
|---------|-----------|----------|
| `municipios_ibge` | `elt_municipios_ibge` | `0 4 * * 1` (segundas 04:00) |

Alem disso, a DAG `elt_pipeline` (geral) executa todos os projetos.

### 5. Logs no Airflow

Cada camada gera logs descritivos no Airflow:

```
[BRONZE] Conectado a origem: https://raw.githubusercontent.com/...
[BRONZE] Lido 5571 registros da origem
[BRONZE] Enviado para MinIO: bronze/tb_municipios_ibge.parquet (5571 registros)

[SILVER] Lendo de MinIO: minio://elt-datalake/bronze/tb_municipios_ibge.parquet
[SILVER] Lido 5571 registros do MinIO
[SILVER] Tabela global.tb_municipios_nf criada/atualizada com 5571 registros

[GOLD] Conectado a origem: elt-postgres:5432 banco=silver
[GOLD] Executando query para dm_municipios_por_uf
[GOLD] Lido 27 registros da origem
[GOLD] Tabela global.dm_municipios_por_uf criada/atualizada com 27 registros
```

## Extratores Disponiveis

| type_source | Descricao | Parametros principais |
|-------------|-----------|----------------------|
| `GOOGLE_SHEETS` | Google Sheets via API | `url`, `conexao_origem_id`, `table_source`, `header_row_source` |
| `XLSX` | Arquivo Excel local | `table_source`, `header_row_source` |
| `DW` | Query SQL em banco PostgreSQL | `database_source`, `schema_source`, `query_source` |
| `ORACLE` | Extracao de banco Oracle | `config.connection_airflow`, `schema_source`, `table_source` |
| `POSTGRE` | Extracao de banco PostgreSQL | `config.connection_airflow`, `schema_source`, `table_source` |
| `MINIO` | Arquivos Parquet/CSV do MinIO | `config.endpoint`, `config.bucket`, `config.object_name` |
| `FTP` / `FTP_DATASUS` | Download de arquivos DBC/DBF | `config.theme`, `config.ano_mes`, `config.ufs` |
| `S3` / `CKAN` / `CSV_URL` | Download de CSV/Parquet via URL | `url`, `config.delimiter`, `config.encoding` |
| `API` | API REST generica | `config.connection_airflow`, `config.base_url`, `config.endpoint` |

## Referencia de Cron

A coluna `schedule_cron` usa o formato padrao do Airflow:

```
minuto hora dia_do_mes mes dia_da_semana
```

| Cron | Significado |
|------|-------------|
| `0 6 * * 1` | Toda segunda-feira as 06:00 |
| `0 7 * * 1-5` | Dias uteis (seg-sex) as 07:00 |
| `30 8 * * 1,3,5` | Segunda, quarta e sexta as 08:30 |
| `0 9 1 * *` | Dia 1 de cada mes as 09:00 |
| `0 */2 * * *` | A cada 2 horas |

> Para testar expressoes cron: [https://crontab.guru](https://crontab.guru)

## Licenca

MIT License
