# ELT - Framework Generico de ETL

Framework generico de ELT (Extract, Load, Transform) orquestrado por **Apache Airflow** e controlado por uma **tabela de parametrizacao** (`global.schedule`).

Basta inserir registros na tabela de schedule para adicionar novos extratores, transformacoes e projetos, sem necessidade de criar novas DAGs ou copiar scripts para o servidor.

## Arquitetura

```
                      global.schedule (tabela de controle)
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
| **Bronze** | Extracao de dados brutos de fontes heterogeneas | PostgreSQL ou MinIO |
| **Silver** | Transformacao/limpeza via queries SQL | PostgreSQL |
| **Gold** | Modelo dimensional (dimensoes e fatos) | PostgreSQL |

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
│  │   ├── base.py            # Classe abstrata
│  │   ├── google_sheets.py
│  │   ├── xlsx.py
│  │   ├── oracle.py
│  │   ├── postgres.py
│  │   ├── minio.py
│  │   ├── ftp.py
│  │   ├── s3.py
│  │   └── api.py
│  └── historics/             # SCD Tipo 2
├ sql/
│  ├── schedule/              # DDL da tabela de controle
│  └── examples/              # Exemplos de inserts
└ utils/
```

## Como Usar

### 1. Criar a tabela de schedule

```sql
-- Executar uma vez no banco de dados gold
psql -h host -d gold -f sql/schedule/001_create_schedule_table.sql
psql -h host -d gold -f sql/schedule/002_create_controle_execucao.sql
```

### 2. Configurar as Connections no Airflow

| Connection ID | Tipo | Descricao |
|---------------|------|-----------|
| `elt_bronze` | Postgres | Banco bronze (extracao) |
| `elt_silver` | Postgres | Banco silver (transformacao) |
| `elt_gold` | Postgres | Banco gold + schedule table |
| `google_sheets` | Google Cloud / Generic | Service account para Google Sheets |
| `minio` | S3 | Credenciais MinIO (se utilizado) |

### 3. Registrar steps na tabela

Cada projeto precisa de ao menos um INSERT por camada (bronze, silver, gold).
A coluna `schedule_cron` define o agendamento da DAG no Airflow:

```sql
-- Bronze: extracao de Google Sheets
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_source, table_destiny, header_row_source,
 schema_destiny, strategy_destiny)
VALUES
('GOOGLE_SHEETS', 'bronze', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'https://docs.google.com/spreadsheets/d/ABC123/edit',
 'MinhaAba', 'minha_tabela', 2,
 'meu_schema', 'truncate');

-- Silver: transformacao SQL
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'silver', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'bronze', 'meu_schema',
 'SELECT * FROM meu_schema.minha_tabela WHERE ativo = true',
 'minha_tabela_tratada', 'meu_schema', 'truncate');

-- Gold: modelo dimensional
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'gold', 'meu_projeto', 1, TRUE,
 '0 7 * * 5',
 'silver', 'meu_schema',
 'SELECT DISTINCT categoria FROM meu_schema.minha_tabela_tratada',
 'dm_categoria', 'meu_schema', 'append');
```

### 4. DAGs geradas automaticamente

O Airflow cria automaticamente uma DAG para cada projeto com `schedule_cron` preenchido:

| Projeto | DAG gerada | Schedule |
|---------|-----------|----------|
| `meu_projeto` | `elt_meu_projeto` | `0 7 * * 5` (sextas 07:00) |

Alem disso, a DAG `elt_pipeline` (geral) continua disponivel para executar
todos os projetos manualmente ou via trigger config.

Para executar um projeto especifico manualmente:
```json
{"projeto": "meu_projeto"}
```

### 5. Adicionar novo extrator

1. Crie uma classe em `src/extractors/` que herde de `BaseExtractor`
2. Registre em `src/extractors/__init__.py`:
   ```python
   EXTRACTOR_REGISTRY['MEU_TIPO'] = MeuExtractor
   ```
3. Use `'MEU_TIPO'` no campo `type_source` da schedule

## Extratores Disponiveis

| type_source      | Descricao                        | Parametros principais |
|------------------|----------------------------------|----------------------|
| `GOOGLE_SHEETS`  | Google Sheets via API            | `url`, `conexao_origem_id`, `table_source`, `header_row_source` |
| `XLSX`           | Arquivo Excel local              | `table_source`, `header_row_source` |
| `DW`             | Query SQL em banco PostgreSQL    | `database_source`, `schema_source`, `query_source` |
| `ORACLE`         | Extracao de banco Oracle         | `config.connection_airflow`, `schema_source`, `table_source` |
| `POSTGRE`        | Extracao de banco PostgreSQL     | `config.connection_airflow`, `schema_source`, `table_source` |
| `MINIO`          | Arquivos Parquet/CSV do MinIO    | `config.endpoint`, `config.bucket`, `config.object_name` |
| `FTP` / `FTP_DATASUS` | Download de arquivos DBC/DBF | `config.theme`, `config.ano_mes`, `config.ufs` |
| `S3` / `CKAN` / `CSV_URL` | Download de CSV/Parquet via URL | `url`, `config.delimiter`, `config.encoding` |
| `API`            | API REST generica                | `config.connection_airflow`, `config.base_url`, `config.endpoint` |

## Referencia de Cron

A coluna `schedule_cron` usa o formato padrao do Airflow (expressao cron de 5 campos):

```
┌───── minuto (0 - 59)
│ ┌───── hora (0 - 23)
│ │ ┌───── dia do mes (1 - 31)
│ │ │ ┌───── mes (1 - 12)
│ │ │ │ ┌───── dia da semana (0 = domingo, 1 = segunda ... 6 = sabado)
│ │ │ │ │
* * * * *
```

| Cron | Significado |
|------|-------------|
| `0 6 * * 1` | Toda segunda-feira as 06:00 |
| `0 7 * * 1-5` | Dias uteis (seg-sex) as 07:00 |
| `30 8 * * 1,3,5` | Segunda, quarta e sexta as 08:30 |
| `0 9 1 * *` | Dia 1 de cada mes as 09:00 |
| `0 */2 * * *` | A cada 2 horas |

> Para testar expressoes cron: [https://crontab.guru](https://crontab.guru)

## Variaveis de Ambiente

Ver `.env.example` para todas as variaveis.

## Instalacao

```bash
pip install -e .
```

Ou instale as dependencias manualmente:

```bash
pip install -r requirements.txt
```

## Licenca

MIT License
