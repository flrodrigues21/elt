# ELT Lab — Análise Técnica e Plano de Melhorias

**Documento:** Melhorias de Banco de Dados, Performance, Tuning e Custos
**Base de análise:** repositório `elt` (branch `feature/jupyter-data-lab`, commit `1817e0e`)
**Público:** time de engenharia de dados / infraestrutura

---

## 1. Sumário Executivo

O ELT Lab é um framework ELT metadata-driven bem projetado (arquitetura medalhão, tabela de schedule única,
controle de execuções auditável). Esta análise identificou **gargalos e riscos concentrados em cinco frentes**:

| # | Frente | Situação atual | Impacto |
|---|--------|----------------|---------|
| 1 | Executor do Airflow | `LocalExecutor` configurado explicitamente nos serviços Airflow | Permite tasks independentes em paralelo no mesmo host; exige limites de concorrência |
| 2 | PostgreSQL | Instância única sem tuning, 5 bancos compartilhando o mesmo processo; superuser único para tudo | Contenção de recurso, blast radius total, sem isolamento de privilégios |
| 3 | Cargas | Estratégia padrão `truncate` (reload full a cada execução) | Custo cresce linearmente com volume; inviável acima de ~1–5M linhas por tabela |
| 4 | Backup/DR | Inexistente (volumes Docker locais, sem dump, sem WAL) | Perda total em falha de disco/host |
| 5 | Código no bind-mount Windows | DAGs e código Python montados via bind mount do filesystem Windows (9P) | Parsing de DAG e imports 5–20x mais lentos que filesystem nativo |

Nenhum dos pontos bloqueia o uso didático/lab atual. Todos se tornam críticos na medida em que a
plataforma assume cargas reais ou multiusuário.

---

## 2. Escopo do que foi analisado

| Artefato | Observações relevantes |
|----------|----------------------|
| `docker-compose.yml` | 1 container Postgres 16-alpine para 5 bancos (`elt`, `bronze`, `silver`, `gold`, `airflow`); MinIO single-node; Jupyter limitado (4G/2CPU); sem limits nos demais serviços |
| `docker-compose.yml`, `.env.example` | `AIRFLOW__CORE__EXECUTOR=LocalExecutor` aplicado ao init, webserver e scheduler |
| `sql/schedule/001_create_schedule_table.sql` | Tabela de parametrização com índices adequados para o volume atual; `config JSONB` |
| `sql/schedule/002_create_controle_execucao.sql` | Log de execuções sem particionamento nem política de retenção |
| `models/gold/transform.py`, `controller/*` | Loop sequencial por steps; conexões abertas por step (sem pool reaproveitado entre steps) |
| `src/extractors/*` | Boa cobertura de fontes; segurança sólida (SSRF, path traversal); downloads em memória |
| README "Aplicação em Produção" | Já reconhece gaps (secrets, TLS, monitoring, backup) — este documento detalha e prioriza |

---

## 3. Banco de Dados (PostgreSQL)

### 3.1 Arquitetura atual e riscos

```
            ┌──────────────────────────────┐
            │  postgres:16-alpine (único)  │
            │ elt │ bronze │ silver │ gold │──► mesmo shared_buffers,
            │          airflow             │    mesmos WAL, mesmo disco
            └──────────────────────────────┘
```

Riscos concretos:

1. **Contenção:** uma carga pesada em `bronze` compete por memória/WAL/IO com o scheduler do Airflow
   (que escreve metadados continuamente no banco `airflow`).
2. **Blast radius:** manutenção/restart derruba pipeline E metadados de orquestração juntos.
3. **Sem isolamento de roles:** todas as camadas usam o mesmo superuser (`elt`) — um erro de SQL em
   silver tem poder de dropar gold.

**Recomendações (ordem de custo/benefício):**

| Ação | Esforço | Ganho |
|------|---------|-------|
| Separar apenas o banco `airflow` para outra instância (ou aceitar risco em volumes pequenos) | Médio | Elimina contenção scheduler × carga; scheduler fica indisponível só para ele mesmo |
| Criar roles por camada: `rw_bronze`, `rw_silver`, `rw_gold`, `ro_bi` (somente leitura para BI) | Baixo | Least privilege imediato; prepara terreno para BI (doc de visão BI) |
| `default_transaction_isolation = 'read committed'` explícito + `statement_timeout` para role de BI | Baixo | Consultas mal escritas não derrubam janela de carga |

### 3.2 Tuning de configuração

A imagem oficial vem com defaults conservadores (ex.: `shared_buffers = 128MB`). Para um host dedicado
de 8–16 GB RAM, ponto de partida:

| Parâmetro | Default | Sugerido (host 8–16GB) | Por quê |
|-----------|---------|------------------------|---------|
| `shared_buffers` | 128MB | 25% da RAM (2–4 GB) | Cache de páginas quentes (gold/dims cabem em memória) |
| `effective_cache_size` | 4GB | 60–70% da RAM | Planejador passa a preferir index scan |
| `work_mem` | 4MB | 32–64 MB | Sorts/hash de agregações do silver/gold; **cuidado**: multiplica por conexão |
| `maintenance_work_mem` | 64MB | 512 MB | CREATE INDEX / VACUUM mais rápidos nas cargas noturnas |
| `wal_compression` | off | `on` | Reduz IO/WAL gerado por cargas bulk (pg 16: lz4) |
| `checkpoint_timeout` / `checkpoint_completion_target` | 5min / 0.9 | 15min / 0.9 | Menos spikes de IO durante janela de carga |
| `max_connections` | 100 | 60 + PgBouncer | Com pooling transaction, 60 é folgado |
| `random_page_cost` | 4.0 | 1.1 | SSD/NVMe (volume Docker local é SSD) |
| `jit` | on | `off` | Overhead do JIT raramente compensa em queries analíticas curtas/médias |
| `autovacuum_vacuum_scale_factor` (controle_execucao) | 0.2 | 0.02 + `analyze_scale_factor=0.01` | Tabela de log sofre append/update constante |
| `log_min_duration_statement` | -1 | 1000ms | Captura queries lentas desde o dia 1 |

Aplicação via `command:` no compose ou `ALTER SYSTEM`, versionada em `sql/tuning/`.

### 3.3 Pooling de conexões

Cada step abre conexão própria via `PostgresConnector`; com N projetos × 3 camadas, picos de conexão
escalam linearmente. Recomendação: **PgBouncer em modo transaction** entre Airflow e Postgres
(`pool_mode=transaction`, `default_pool_size=20`). Mudança de connection string apenas
(`...@pgbouncer:6432/bronze`). Atenção: prepared statements do psycopg2 exigem
`disable_prepared_binary_output=yes` ou driver atualizado — validar antes.

### 3.4 Índices, particionamento e retenção

| Objeto | Ação | Justificativa |
|--------|------|---------------|
| `global.controle_execucao` | Particionar por mês (`PARTITION BY RANGE (inicio)`) + job de drop de partições > 12 meses | Única tabela de crescimento ilimitado; hoje vira gargalo de vacuum e de consultas de monitoramento |
| `global.controle_execucao` | Índice BRIN em `inicio` como alternativa leve (< 1M linhas/ano) | BRIN custa KBs e resolve filtro temporal do dashboard de pipeline |
| `global.schedule` | Índice parcial `(projeto, layer, ordem) WHERE ativo` | A leitura quente do framework filtra `ativo = TRUE` sempre |
| Tabelas gold (`dm_*`) | B-tree nas FKs/chaves naturais; avaliar covering index por página de dashboard | Dashboards não devem fazer seq scan a cada refresh |
| Silver grande (>10M linhas) | Particionar por data de partição de carga quando houver carga incremental | DROP PARTITION substitui DELETE em retenções |

### 3.5 Estratégias de carga — o maior ganho de escala

Hoje `strategy_destiny` suporta `truncate | append | replace`. O padrão `truncate` recarrega a tabela
inteira a cada execução. Para qualquer fonte com histórico, migrar para:

1. **`upsert` incremental:** coluna de watermark (`updated_at`, `id`, data da partição) guardada em
   `config.watermark`; carga traz `WHERE watermark > último valor` (último valor persistido em
   `controle_execucao.metadados`). Esforço estimado: 1–2 dias de dev no `models/*/transform.py`
   + validações.
2. **`merge` SCD2 já existente:** `src/historics/history.py` implementa SCD Tipo 2 — garantir que as
   chaves estejam indexadas e que a comparação de hash seja feita em lote (hoje comparar linha a linha
   em pandas é O(n)); alternativa: hash calculado no próprio SQL.
3. **Bulk copy:** substituir `to_sql` pandas (row-by-row fallback) por `COPY ... FROM STDIN`
   (psycopg2 `copy_expert`) ou `execute_values` com page_size — ganho típico de 5–20x em cargas
   tabulares médias.

### 3.6 Backup, PITR e DR

| Item | Proposta | Custo |
|------|----------|-------|
| Dump lógico diário | `pg_dump -Fc` dos 5 bancos em cron/container lateral, retenção 7 diária + 4 semanal, upload para bucket externo | ~1h setup |
| PITR físico | WAL-G ou pgBackRest apontando para object storage externo (S3/B2), RPO ≤ 5 min | ~1–2 dias setup |
| MinIO | `mc mirror` noturno para segundo destino + habilitar versioning no bucket `elt-datalake` | ~2h |
| Runbook | Documentar restore drill (restaurar em container efêmero e validar contagens) | ~2h |
| Metas sugeridas (lab→prod) | RPO 24h/5min, RTO 4h/1h | — |

> Hoje: falha de disco = perda total de dados E de metadados de execução. É o risco nº 1 fora do lab.

### 3.7 Segurança de banco (complemento ao que já existe)

- TLS interno entre containers (postgres com certificado ou rede interna sem portas publicadas — já ok no lab).
- Roles por camada (3.1) + `ro_bi` somente-leitura para a ferramenta de BI.
- RLS (Row-Level Security) por projeto/UF quando houver multi-tenant — o campo `projeto` do schedule
  já dá a chave natural de segregação.
- `pip-audit` + SBOM CycloneDX no CI (pendência já registrada no README).

---

## 4. Performance do Pipeline (Airflow)

### 4.1 Executor — correção de maior impacto e menor custo

O Airflow agora usa **LocalExecutor**: tasks independentes podem executar em paralelo no mesmo host.
Como o metadata DB já é PostgreSQL, a configuração aplicada é:

```env
AIRFLOW__CORE__EXECUTOR=LocalExecutor
```

Ganho: tasks de projetos independentes rodam em paralelo. Configurar ainda:

```env
AIRFLOW__CORE__PARALLELISM=16
AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG=2
AIRFLOW__SCHEDULER__MAX_TIS_PER_QUERY=512
AIRFLOW__SCHEDULER__PARSING_PROCESSES=2
```

### 4.2 Bind mount do Windows no DAGs folder

`AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/elt` onde `/opt/airflow/elt` é bind mount de
`C:\Users\...\git`. Filesystem 9P do WSL2 torna cada varredura/listagem de DAGs lenta
(DAG_DIR_LIST_INTERVAL=30s piora). Opções:

1. **Copiar código na imagem** (`Dockerfile.airflow`: `COPY . /opt/airflow/elt`) — melhor perf; exige rebuild a cada mudança (ok p/ produção).
2. Manter bind mount só em dev, mas mover repo para dentro do filesystem WSL2 (`\\wsl$\...` ou clone em `~/projeto` dentro da distro) — ganho imediato sem trocar workflow.
3. `git-sync` sidecar (padrão mercado) quando houver cluster.

### 4.3 Conexões e pools

- Reaproveitar engine SQLAlchemy por processo (singleton) em vez de abrir conexão por step — reduz latência e consumo de conexões (sinergia com PgBouncer).
- Definir **Airflow Pools por fonte** (ex.: pool `oracle_prod=2`) para proteger sistemas origem de rajadas.
- `retries=1, retry_delay=30s` está agressivo para fontes externas instáveis (FTP/API): sugerir backoff exponencial (`retry_exponential_backoff=True`, delay 2–5 min).

### 4.4 Higiene dos metadados

Com LocalExecutor + uso contínuo, o banco `airflow` cresce rápido. Agendar `airflow db clean`
(retenção 30–60d) mensalmente — senão o scheduler degrada em semanas/meses.

---

## 5. Datalake (MinIO)

| Item | Situação | Recomendação |
|------|----------|--------------|
| Versioning | Desabilitado | Habilitar no bucket `elt-datalake` (proteção contra sobrescrita acidental; barato) |
| Lifecycle | Ausente | ILM: transição de objetos > 90d para storage class fria (em cloud) ou expiração de partições antigas |
| Compressão | Parquet sem compressão explícita | Padronizar `zstd` (ganho típico 30–50% vs snappy, custo CPU baixo) — definir no writer dos extractors |
| Layout | Objetos soltos (`bronze/tabela.parquet`) | Particionar `bronze/fonte/tabela/dt=YYYY-MM-DD/part-*.parquet` — habilita pruning e carga incremental natural |
| HA | Single-node | Aceitável no lab; em prod, MinIO distribuído (≥4 nodes) ou S3 gerenciado |
| Licença | AGPL-3.0 | OK para uso interno; revisar se exposto como serviço a terceiros |

---

## 6. Qualidade de Dados e Observabilidade

1. **Testes de dados por camada** (gate entre silver→gold):
   - Leve: `not_null`, `unique`, `accepted_values`, `row_count > 0`, freshness — implementáveis com
     queries SQL registradas na própria `schedule` (`pos_query` já existe como ponto de extensão!).
   - Evolução: Great Expectations ou dbt tests quando houver > ~10 projetos.
2. **Quarantine:** linhas rejeitadas vão para `silver_quarantine.<tabela>` com motivo — evita quebrar a carga inteira por 0,1% sujo.
3. **Métricas:** Prometheus + Grafana + `postgres_exporter` + StatsD do Airflow (`AIRFLOW__METRICS__STATSD_ON=true`); cAdvisor para containers; Loki para logs centralizados. Dashboard mínimo: duração por step (vem de `controle_execucao.inicio/fim`), taxa de erro, freshest timestamp por tabela gold.
4. **Alertas:** o callback de e-mail já existe (`controller/dags.py`); adicionar alerta de *freshness* (tabela gold não carrega há X horas) — é o alerta que o negócio realmente sente.

## 7. CI/CD (inexistente hoje)

Pipeline GitHub Actions mínimo:

```yaml
push/PR → pytest (247 testes) → ruff/black → pip-audit --desc → build imagens
main     → push registry (tags imutáveis) → deploy compose em host de staging
```

Custo: US$ 0 (free tier para repo privado pequeno). Pendências do README (pip-audit, SBOM) entram aqui.

---

## 8. Custos

### 8.1 Cenário atual (lab local)

R$ 0/mês de infraestrutura; consome ~4–6 GB RAM do workstation (postgres+airflow+minio+jupyter).
Custo real = horas de máquina do desenvolvedor.

### 8.2 Projeções cloud (valores de referência — validar no orçamento do provedor)

| Cenário | Composição | Estimativa mensal* |
|---------|-----------|--------------------|
| **Dev/Staging compartilhado** | VM 4 vCPU/16 GB (Linux) + 100 GB SSD + snapshot diário | USD 45–80 (~R$ 260–460) |
| **Produção pequeno** (<50M linhas/gold) | VM apps 8 vCPU/32GB + PG gerenciado 2vCPU/8GB/100GB + object storage 200GB + backups | USD 220–420 (~R$ 1.250–2.400) |
| **Produção médio** (50–500M linhas, BI concorrente) | VM apps 8vCPU/32GB + PG gerenciado 4vCPU/16GB/500GB Multi-AZ + 1TB storage tiered | USD 500–900 (~R$ 2.800–5.000) |
| Alternativa serverless-PG (Neon/Supabase tier pago) | reduz custo de staging para USD 25–40/mês, scale-to-zero à noite | — |

\* Faixas grosseiras AWS/GCP/Azure/Hetzner-DO em mar/2026; spot/preemptible pode cortar 40–70% da VM de dev.

### 8.3 Alavancas de otimização (por ordem de impacto)

| Alavanca | Economia típica |
|----------|-----------------|
| Carga incremental (3.5) em vez de reload full | Reduz tempo de janela e IO em 80–95% com histórico acumulado — adia upgrade de instância por meses |
| Parquet zstd + partição por dt | 30–50% menos storage e network |
| Spot/preemptible para dev e workers não críticos | 40–70% do compute |
| Retenção/particionamento (3.4) + lifecycle MinIO | Storage cresce sublinear |
| PgBouncer | Adia upgrade vertical motivado por conexões |
| Agendar cargas fora do horário comercial e escalonar (bronze 05h, silver 06h, gold 07h) | Pico de CPU plano em vez de concorrente |

---

## 9. Roadmap Priorizado

### Quick wins (≤ 1 semana somada)

| # | Ação | Ref |
|---|------|-----|
| 1 | `LocalExecutor` + paralelismos | 4.1 |
| 2 | Roles por camada + `ro_bi` | 3.1 |
| 3 | Tuning postgres (ALTER SYSTEM versionado) | 3.2 |
| 4 | `pg_dump` diário + mirror MinIO | 3.6 |
| 5 | Repo dentro do filesystem WSL2 (dev) | 4.2 |
| 6 | CI com pytest + pip-audit | 7 |

### Curto prazo (2–4 semanas)

| # | Ação | Ref |
|---|------|-----|
| 7 | COPY/execute_values nas cargas | 3.5 |
| 8 | Watermark/upsert incremental | 3.5 |
| 9 | Particionamento/BRIN + retenção de `controle_execucao` | 3.4 |
| 10 | Prometheus + Grafana + freshness alerts | 6 |
| 11 | Testes de dados gate silver→gold via `pos_query` | 6 |

### Estrutural (1–2 trimestres)

| # | Ação | Ref |
|---|------|-----|
| 12 | PgBouncer + instância separada p/ airflow metadata | 3.1/3.3 |
| 13 | WAL-G/pgBackRest PITR + runbook de restore | 3.6 |
| 14 | Layout particionado do datalake + ILM | 5 |
| 15 | Deploy prod (registry, secrets backend, TLS reverso) | 7/README |

---

*Documento gerado a partir de análise estática do código e configuração em `1817e0e`. Valores de tuning são pontos de partida — medir com `pg_stat_statements` e métricas reais antes de consolidar.*
