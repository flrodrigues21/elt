# ELT Lab

Ambiente local de ELT (Extract, Load, Transform) com **Apache Airflow**, **MinIO** e **PostgreSQL** via Docker.

Basta clonar e rodar `.\setup.ps1` para ter o lab completo funcionando.

---

## Setup (3 passos)

```powershell
# 1. Clonar
git clone https://github.com/flrodrigues21/elt.git
cd elt

# 2. Subir tudo (gera .env com senhas seguras automaticamente)
.\setup.ps1

# 3. Rodar o pipeline
# Abra http://localhost:8080, ative e execute a DAG elt_municipios_ibge
```

**Prerequisitos:** Docker Desktop instalado e rodando, ~4GB RAM livre.

---

## Componentes e Portas

| Componente | Imagem | Porta | Descricao |
|-----------|--------|-------|-----------|
| PostgreSQL | `postgres:16-alpine` | `127.0.0.1:5432` | 5 bancos: `elt`, `bronze`, `silver`, `gold`, `airflow` |
| Airflow Webserver | `apache/airflow:2.9.3-python3.11` | `127.0.0.1:8080` | Interface de gerenciamento de DAGs |
| Airflow Scheduler | `apache/airflow:2.9.3-python3.11` | - | Execucao agendada de DAGs |
| MinIO API | `minio/minio:RELEASE.2024-09-22T00-33-43Z` | `127.0.0.1:9000` | API S3-compativel |
| MinIO Console | `minio/minio:RELEASE.2024-09-22T00-33-43Z` | `127.0.0.1:9001` | Interface web MinIO |

> **Portas:** Todas as portas sao publicadas apenas em `127.0.0.1` por seguranca.
> **Atencao:** Alterar para `0.0.0.0` expoe os servicos a rede local/externa.
> Ao fazer isso, garanta: (1) firewall com whitelist de IPs, (2) credenciais fortes,
> (3) TLS/proxy reverso na frente, e (4) redes Docker dedicadas.

---

## O que e cada componente

| Componente | O que e | Papel no projeto | Onde e usado | Licenca | Links |
|-----------|---------|-----------------|-------------|---------|-------|
| **Python 3.12** | Linguagem de programacao interpretada | Linguagem dos extractors, conectores e controller | Todo o codigo-fonte do projeto | PSF License | [python.org](https://www.python.org/) \| [License](https://docs.python.org/3/license.html) |
| **PostgreSQL 16** | Sistema de gerenciamento de banco relacional | Banco para todas as camadas (bronze/silver/gold/elt/airflow) | `docker-compose.yml` (servico postgres) | PostgreSQL License | [postgresql.org](https://www.postgresql.org/) \| [License](https://www.postgresql.org/about/licence/) |
| **Apache Airflow 2.9.3** | Orquestrador de workflows (DAGs) | Executa, agenda e monitora pipelines ELT | `docker-compose.yml` (servicos airflow-*) | Apache 2.0 | [airflow.apache.org](https://airflow.apache.org/) \| [License](https://www.apache.org/licenses/LICENSE-2.0) |
| **Docker** | Plataforma de containerizacao | Empacota servicos em containers isolados | Infraestrutura base do lab | Apache 2.0 | [docker.com](https://www.docker.com/) \| [License](https://github.com/moby/moby/blob/master/LICENSE) |
| **Docker Compose** | Orquestrador multi-container | Define e gerencia todos os servicos com um comando | `docker-compose.yml` | Apache 2.0 | [docs.docker.com/compose](https://docs.docker.com/compose/) \| [License](https://github.com/docker/compose/blob/main/LICENSE) |
| **MinIO** | Object storage S3-compativel | Datalake em formato Parquet (camada bronze/silver/gold) | `docker-compose.yml` (servico minio), `src/extractors/minio.py` | AGPL-3.0 | [min.io](https://min.io/) \| [License](https://github.com/minio/minio/blob/master/LICENSE) |
| **MinIO SDK (minio-py)** | Cliente Python para API S3 do MinIO | Upload/download de objetos Parquet no datalake | `src/connectors/minio_connector.py` | Apache 2.0 | [min.io/docs/minio/python](https://min.io/docs/minio/linux/developers/python/API.html) \| [License](https://github.com/minio/minio-py/blob/master/LICENSE) |
| **SQLAlchemy** | Toolkit ORM e SQL para Python | Conexao com PostgreSQL/Oracle via pool de conexoes | `src/connectors/postgres_connector.py`, `src/connectors/oracle_connector.py` | MIT | [sqlalchemy.org](https://www.sqlalchemy.org/) \| [License](https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE) |
| **pandas** | Biblioteca de manipulacao de dados tabulares | Leitura, transformacao e escrita de DataFrames | `src/extractors/*.py`, `src/models/` | BSD-3-Clause | [pandas.pydata.org](https://pandas.pydata.org/) \| [License](https://github.com/pandas-dev/pandas/blob/main/LICENSE) |
| **PyArrow** | Implementacao Apache Arrow para Python | Suporte a formato Parquet e vetores columnares | `src/extractors/s3.py` (leitura parquet) | Apache 2.0 | [arrow.apache.org/docs/python](https://arrow.apache.org/docs/python/) \| [License](https://github.com/apache/arrow/blob/main/LICENSE.txt) |
| **OpenPyXL** | Leitura/escrita de arquivos Excel (.xlsx) | Extracao de dados de planilhas Excel | `src/extractors/xlsx.py` | MIT | [openpyxl.readthedocs.io](https://openpyxl.readthedocs.io/) \| [License](https://openpyxl.readthedocs.io/en/stable/license.html) |
| **Requests** | HTTP client para Python | Chamadas a APIs REST e downloads de CSV | `src/extractors/api.py`, `src/extractors/s3.py`, `src/extractors/_security.py` | Apache 2.0 | [requests.readthedocs.io](https://requests.readthedocs.io/) \| [License](https://github.com/psf/requests/blob/main/LICENSE) |
| **psycopg2** | Adaptador nativo PostgreSQL para Python | Conexao direta com PostgreSQL via libpq | `src/connectors/postgres_connector.py` | LGPL-2.1+ | [ycopg.org](https://www.psycopg.org/) \| [License](https://www.psycopg.org/docs/copyright.html) |
| **python-oracledb** | Driver Oracle para Python (modo Thin) | Conexao com Oracle sem Oracle Client | `src/connectors/oracle_connector.py` | Apache 2.0 | [oracle.github.io/python-oracledb](https://oracle.github.io/python-oracledb/) \| [License](https://github.com/oracle/python-oracledb/blob/main/LICENSE.txt) |
| **google-api-python-client** | Cliente Python para Google APIs | Acesso ao Google Sheets API v4 | `src/extractors/google_sheets.py` | Apache 2.0 | [github.com/googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client) \| [License](https://github.com/googleapis/google-api-python-client/blob/main/LICENSE) |
| **gspread** | Wrapper Python para Google Sheets | Abstracao simplificada do Sheets API | `src/extractors/google_sheets.py` | MIT | [github.com/burnash/gspread](https://github.com/burnash/gspread) \| [License](https://github.com/burnash/gspread/blob/master/LICENSE) |

---

## Credenciais

As credenciais sao geradas automaticamente pelo `.\setup.ps1` no arquivo `.env`.

Nunca commite o arquivo `.env` ao repositorio (protegido pelo `.gitignore`).

| Servico | Variavel no `.env` | Como acessar |
|---------|-------------------|--------------|
| **PostgreSQL** | `POSTGRES_USER`, `POSTGRES_PASSWORD` | `localhost:5432` com cliente SQL |
| **Airflow** | `AIRFLOW_ADMIN_USERNAME`, `AIRFLOW_ADMIN_PASSWORD` | http://localhost:8080 |
| **MinIO** | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | http://localhost:9001 |

Para ver as credenciais, abra o arquivo `.env` na raiz do projeto.

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
       S3 / CKAN / CSV_URL
       Oracle / PostgreSQL
       MinIO (parquet)
       API REST
       FTP
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

---

## Commands Uteis

```powershell
.\setup.ps1                # Subir tudo
.\setup.ps1 -Down          # Parar (volumes preservados)
.\setup.ps1 -PurgeVolumes  # Parar e apagar dados (pede confirmacao)
.\setup.ps1 -Status        # Ver status dos containers
.\setup.ps1 -Logs          # Ver logs (escolhe container)
```

Ou manualmente:

```powershell
docker compose up -d --build
```

---

## Extratores Disponiveis

| type_source | Descricao | Parametros principais |
|-------------|-----------|----------------------|
| `GOOGLE_SHEETS` | Google Sheets via API | `url`, `conexao_origem_id`, `table_source`, `header_row_source` |
| `XLSX` | Arquivo Excel local | `table_source`, `header_row_source` |
| `DW` | Query SQL em banco PostgreSQL | `database_source`, `schema_source`, `query_source` |
| `ORACLE` | Extracao de banco Oracle | `config.connection_airflow`, `schema_source`, `table_source` |
| `POSTGRE` | Extracao de banco PostgreSQL | `config.connection_airflow`, `schema_source`, `table_source` |
| `MINIO` | Arquivos Parquet/CSV do MinIO | `config.endpoint`, `config.bucket`, `config.object_name` |
| `FTP` | Download de arquivos via FTP | `config.ftp_host`, `config.ftp_base`, `config.file_pattern`, `config.file_format` |
| `S3` / `CKAN` / `CSV_URL` | Download de CSV/Parquet via URL | `url`, `config.delimiter`, `config.encoding` |
| `API` | API REST generica | `config.connection_airflow`, `config.base_url`, `config.endpoint` |

---

## Seguranca

- Senhas geradas automaticamente com caracteres aleatorios criptograficos
- Chave Fernet do Airflow gerada criptograficamente
- Portas publicadas apenas em `127.0.0.1` (localhost)
- Arquivos `.env` nao versionados (gitignore)
- Credenciais nao expostas no terminal durante setup
- Imagens Docker com versoes fixadas (nao `:latest`)
- Protecao contra path traversal em downloads
- Protecao contra SSRF (validacao de esquema e resolucao DNS)
- Limites de tamanho em downloads e extracao de ZIPs
- Validacao de identificadores SQL em queries
- Credenciais mascaradas em logs

---

## Aplicacao em Producao

Este repositorio e projetado para **desenvolvimento e testes locais**. Para uso em producao:

1. **Secrets:** Use Docker secrets, Vault, ou o gerenciamento de secrets do Airflow (nao arquivos `.env`)
2. **TLS:** Configure TLS/proxy reverso para todas as portas expostas
3. **Network:** Use redes Docker dedicadas; nunca exponha servicos diretamente
4. **Monitoring:** Adicione Prometheus/Grafana para metricas de Airflow e PostgreSQL
5. **Backup:** Configure backup automatico dos volumes `elt-pgdata` e `elt-miniodata`
6. **Logs:** Centralize logs com ELK/Fluentd/Loki
7. **Resource Limits:** Adicione `deploy.resources.limits` no `docker-compose.yml`

---

## Estrutura do Projeto

```
elt/
+-- main.py                     # DAG Airflow (geracao dinamica)
+-- controller/                 # Orquestracao
|   +-- load_bronze.py
|   +-- load_silver.py
|   +-- load_gold.py
|   +-- dags.py                 # Notificacao por email
+-- models/
|   +-- bronze/extract.py       # Extrator generico
|   +-- silver/transform.py     # Transformacao generica
|   +-- gold/transform.py       # Modelo dimensional generico
+-- src/
|   +-- schedule/               # Leitura da tabela de controle
|   +-- connectors/             # Conectores de banco e servicos
|   |   +-- postgres_connector.py
|   |   +-- oracle_connector.py
|   |   +-- minio_connector.py
|   |   +-- airflow_connections.py
|   +-- extractors/             # Extratores registraveis
|   |   +-- base.py
|   |   +-- _security.py        # Utilitarios de seguranca
|   |   +-- google_sheets.py
|   |   +-- xlsx.py
|   |   +-- oracle.py
|   |   +-- postgres.py
|   |   +-- minio.py
|   |   +-- ftp.py
|   |   +-- s3.py
|   |   +-- api.py
|   +-- utils/
|   |   +-- validation.py       # Validacao de identificadores SQL
|   +-- historics/              # SCD Tipo 2
+-- sql/init/                   # Scripts de inicializacao do banco
+-- docker/
|   +-- Dockerfile.airflow
|   +-- airflow_init.sh
|   +-- requirements-airflow.txt
+-- docker-compose.yml
+-- .env                        # Credenciais (nao versionado)
+-- .env.example                # Template de configuracao
+-- THIRD_PARTY_NOTICES.md      # Licencas de dependencias
+-- LICENSE                     # MIT License
```

---

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

### Fluxo flexivel por camada

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

### 5. Referencia de Cron

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

## Gerenciamento de Dependencias

- **Imagens Docker:** Todas fixadas com tag de versao. MinIO tambem fixado por digest SHA-256
- **Python (requirements-airflow.txt):** Versoes sem upper bound, resolvidas via constraints oficiais
- **Airflow constraints:** `Dockerfile.airflow` usa constraints oficiais da versao 2.9.3
  (`constraints-3.11.txt`), garantindo compatibilidade entre providers e SDKs
- **Dependabot:** Configurado em `.github/dependabot.yml` para monitorar atualizacoes
  semanais de pip e Docker
- **Security:** `src/extractors/_security.py` fornece protecao contra path traversal,
  SSRF, DNS rebinding (adapter IP-bound), e limits de download

### Pendencias registradas

- [ ] **pip-audit:** Adicionar etapa `pip-audit --desc` ao pipeline CI para varredura
  periodica de vulnerabilidades nas dependencias Python
- [ ] **SBOM CycloneDX:** Integrar geracao de SBOM (`cyclonedx-py`) no CI/CD para
  rastreabilidade completa de componentes de software

---

## Licenca

MIT License - veja [LICENSE](LICENSE) para detalhes.

Dependencias de terceiros: veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
