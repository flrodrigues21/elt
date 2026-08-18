# Conector Oracle na Camada Bronze

## Visao Geral

O extrator `ORACLE` permite ler dados de bancos Oracle e carrega-los na camada bronze do ELT. A conexao e configurada via Airflow Connections, com o `connection_airflow` passado pela coluna `config` (JSONB) da tabela `global.schedule`. Os demais campos (`schema_source`, `table_source`, `query_source`) sao lidos diretamente das colunas da schedule.

## Arquitetura

```
Airflow Connection (conn_id)
        |
        v
AirflowConnector.get_connection(conn_id)
        |
        v
OracleConnector (SQLAlchemy + oracledb)
        |
        v
OracleExtractor.extract() --> pd.DataFrame
        |
        v
PostgresConnector.write_dataframe() --> bronze
```

## Configuracao no Airflow

### 1. Criar a Connection Oracle no Airflow

No Airflow UI: **Admin > Connections > Add Connection**

| Campo        | Valor                                  |
|--------------|----------------------------------------|
| Conn Id      | `meu_oracle` (ou nome identificador)   |
| Conn Type    | `oracle`                               |
| Host         | `oracle.example.com`                   |
| Port         | `1521`                                 |
| Schema       | `MY_SCHEMA` (service name do Oracle)   |
| Login        | `usuario_oracle`                       |
| Password     | `senha_oracle`                         |

### 2. Inserir na Tabela `global.schedule`

```sql
INSERT INTO global.schedule (
    type_source, layer, projeto, ordem, ativo,
    schema_source, table_source,
    schema_destiny, table_destiny,
    strategy_destiny, schedule_cron, config
) VALUES (
    'ORACLE',          -- type_source
    'bronze',          -- layer
    'meu_projeto',     -- projeto
    1,                 -- ordem
    true,              -- ativo
    'MY_SCHEMA',       -- schema_source (schema no Oracle)
    'TB_PACIENTE',     -- table_source (tabela no Oracle)
    'meu_projeto',     -- schema_destiny (schema no PostgreSQL bronze)
    'tb_paciente',     -- table_destiny (tabela no PostgreSQL bronze)
    'truncate',        -- strategy_destiny
    '0 3 * * *',       -- schedule_cron
    '{"connection_airflow": "meu_oracle"}'::jsonb  -- config
);
```

### 3. Usando Query Customizada

Em vez de `table_source`, e possivel passar uma `query_source` direta na coluna da schedule:

```sql
INSERT INTO global.schedule (
    type_source, layer, projeto, ordem, ativo,
    schema_destiny, table_destiny,
    query_source, strategy_destiny, schedule_cron, config
) VALUES (
    'ORACLE',
    'bronze',
    'meu_projeto',
    1,
    true,
    'meu_projeto',
    'vw_atendimentos',
    'SELECT cd_atendimento, dt_atendimento FROM my_schema.tb_atendimento WHERE dt_atendimento >= TRUNC(SYSDATE) - 30',
    'truncate',
    '0 3 * * *',
    '{"connection_airflow": "meu_oracle"}'::jsonb
);
```

## Colunas da Schedule Utilizadas

| Coluna           | Origem        | Descricao                                       |
|------------------|---------------|--------------------------------------------------|
| `config`         | JSONB         | `{"connection_airflow": "conn_id"}` (obrigatorio)|
| `schema_source`  | Schedule col  | Schema (owner) da tabela no Oracle               |
| `table_source`   | Schedule col  | Nome da tabela no Oracle                         |
| `query_source`   | Schedule col  | Query SQL customizada (Oracle syntax)            |

> A coluna `config` contem **apenas** o `connection_airflow`. Os demais campos sao lidos das colunas da schedule.

## Exemplos de Config

### Tabela simples

```json
{"connection_airflow": "meu_oracle"}
```

Neste caso, `schema_source` e `table_source` sao lidos das colunas da schedule.

### Query customizada

```json
{"connection_airflow": "meu_oracle"}
```

Neste caso, `query_source` e lido da coluna da schedule.

## Tratamento de Erros

- **ORA-01843 / ORA-01861** (formato de data invalido): o extrator refaz a query com casts automaticos para text.
- **connection_airflow ausente**: erro antes da extracao, registro marcado como `erro` na `controle_execucao`.
- **Tabela inexistente**: erro propagado do Oracle, registrado na `controle_execucao`.

## Dependencia

O extrator Oracle requer o driver `oracledb` (ou `cx_Oracle`) instalado no Airflow:

```bash
pip install oracledb
```

## Arquivos

| Arquivo                              | Descricao                        |
|--------------------------------------|----------------------------------|
| `src/connectors/oracle_connector.py` | Conector Oracle (SQLAlchemy)     |
| `src/extractors/oracle.py`           | Extrator Oracle (BaseExtractor)  |
| `src/extractors/__init__.py`         | Registro no EXTRACTOR_REGISTRY   |
| `models/bronze/extract.py`           | Branch ORACLE no pipeline bronze |
