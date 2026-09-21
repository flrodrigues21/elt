# Demonstracao do OpenMetadata

Este roteiro sobe o catalogo, executa o bootstrap e percorre os recursos criados
sobre o pipeline `elt_municipios_ibge`.

## Preparacao

1. Suba o ELT:

   ```powershell
   .\setup.ps1
   ```

2. Abra o Airflow na porta configurada, execute a DAG `elt_municipios_ibge` e
   aguarde as tres tasks terminarem em `success`. Alternativamente, dispare pela
   CLI e acompanhe o resultado na interface:

   ```powershell
   docker exec elt-airflow-webserver airflow dags trigger elt_municipios_ibge
   ```

3. Catalogue e governe os ativos:

   ```powershell
   .\scripts\openmetadata\manage.ps1 bootstrap
   ```

4. Abra `http://localhost:8585` (ou a porta definida em `OPENMETADATA_PORT`) e
   entre com `admin@open-metadata.org` e `OM_ADMIN_PASSWORD` do `.env`.

O primeiro `setup.ps1` cria um unico `.env`, inicia todos os containers no projeto
Docker `elt` e troca a senha default do OpenMetadata por uma senha aleatoria. O
arquivo e local e nao deve ser versionado. O bootstrap pode ser repetido com
seguranca.

Prepare a stack e execute a DAG antes da apresentacao. O roteiro abaixo foi
organizado para uma navegacao de aproximadamente cinco minutos com os dados ja
catalogados.

## Roteiro

### 1. Catalogo

1. Pesquise por `tb_municipios_ibge`.
2. Confirme o service `elt_bronze`, database `bronze` e schema `global`.
3. Verifique a descricao, owner `DataEngineers` e as nove colunas documentadas.
4. Repita para `tb_municipios_nf` e `dm_municipios_por_uf`.

Resultado esperado: os tres ativos possuem descricoes de tabela e coluna, owner,
tag de sensibilidade e termos de glossario.

### 2. Airflow

1. Abra **Explore > Pipelines**.
2. Selecione `elt_airflow.elt_municipios_ibge`.
3. Verifique DAG, tasks, schedule e historico de execucao ingeridos do Airflow.

### 3. Lineage

1. Abra `tb_municipios_nf` e selecione a aba **Lineage**.
2. Expanda um nivel para cima e para baixo.
3. Confirme `tb_municipios_ibge -> tb_municipios_nf -> dm_municipios_por_uf`.
4. Ative a visualizacao de colunas para conferir mapeamentos diretos, renomeacao de `siafi_id`, derivacao de `uf`/`estado` e agregacao `COUNT(*)`.

### 4. Glossario e Classificacao

1. Abra **Governance > Glossary** e selecione `ELTGlossary`.
2. Confira os seis termos e o owner `DataStewards`.
3. Abra **Governance > Classification** e selecione `DataSensitivity`.
4. Confira `Public`, `Internal`, `Sensitive`, `Confidential` e `PII`.
5. Observe que `PII` nao foi aplicado, pois nao ha dados pessoais no dataset.

### 5. Qualidade

1. Abra cada tabela do fluxo e selecione **Data Quality**.
2. Confira o ultimo resultado dos testes de row count.
3. Valores esperados para a carga atual: Bronze 5571, Silver 1794 e Gold 9.

### 6. Ownership

1. Abra **Settings > Teams**.
2. Confira `DataOwners`, `DataStewards` e `DataEngineers`.
3. Volte aos ativos e confirme a separacao entre responsabilidade tecnica e de negocio.

## Comandos Operacionais

```powershell
.\scripts\openmetadata\manage.ps1 status     # Containers e health
.\scripts\openmetadata\manage.ps1 health     # Verificacao rapida da API
.\scripts\openmetadata\manage.ps1 bootstrap  # Reingestao idempotente
.\scripts\openmetadata\manage.ps1 stop       # Parar, preservando volumes
```

O script `stop` e deliberadamente nao destrutivo. Para remover somente a
infraestrutura e os dados do OpenMetadata, preservando PostgreSQL e MinIO do ELT:

```powershell
.\scripts\openmetadata\manage.ps1 stop
docker compose rm -f openmetadata-security-init openmetadata-server openmetadata-migrate openmetadata-elasticsearch openmetadata-postgres
docker volume rm elt_openmetadata-postgres-data elt_openmetadata-elasticsearch-data
```

Esses comandos sao destrutivos apenas para o catalogo e devem ser usados somente
quando a perda dos metadados do OpenMetadata tiver sido confirmada.

## Solucao de Problemas

| Sintoma | Verificacao |
|---------|-------------|
| API indisponivel | Execute `manage.ps1 status` e confira o health do server |
| Projeto `elt` ausente | Suba a stack completa com `.\setup.ps1` |
| Tabelas sem dados | Execute a DAG `elt_municipios_ibge` no Airflow |
| Aviso sobre `pg_stat_statements` | Ignore no lab; somente usage de queries e afetado |
| Bootstrap falha em qualidade | Compare os row counts reais com as regras em `bootstrap.py` |

Mais detalhes de papeis, taxonomia e controles estao em [`governance.md`](governance.md).
