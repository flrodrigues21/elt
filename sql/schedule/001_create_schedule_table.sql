-- ============================================================
-- Tabela de parametrizacao generica ELT
-- Proposito: Controlar todos os steps de ETL (bronze, silver, gold)
-- Projetada para ser compativel com o schedule table do GARA
-- e extensivel para novos extratores (FTP, S3, API, etc.)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS global;

CREATE TABLE IF NOT EXISTS global.schedule (
    id SERIAL PRIMARY KEY,

    -- Identificacao do step
    type_source VARCHAR(50) NOT NULL,
        -- 'GOOGLE_SHEETS' = extracao de Google Sheets (bronze)
        -- 'FTP' = extracao de FTP (bronze)
        -- 'S3' = extracao de S3/CKAN (bronze)
        -- 'CSV_URL' = extracao de CSV via URL (bronze)
        -- 'XLSX' = extracao de arquivo XLSX local (bronze)
        -- 'DW' = transformacao SQL (silver/gold)
        -- 'SQL' = extracao de outra tabela SQL (bronze)

    layer VARCHAR(20) NOT NULL DEFAULT 'bronze',
        -- 'bronze' = extracao/carga crua
        -- 'silver' = transformacao e limpeza
        -- 'gold' = modelo dimensional

    projeto VARCHAR(100) DEFAULT 'default',
        -- Nome do projeto para agrupar steps (ex: 'gara', 'dados_abertos', 'cnes')

    ordem INTEGER DEFAULT 0,
        -- Ordem de execucao dentro do mesmo layer/projeto

    ativo BOOLEAN DEFAULT TRUE,
        -- FALSE para desabilitar sem precisar deletar

    -- === CONFIGURACAO DE ORIGEM ===

    conexao_origem_id VARCHAR(100),
        -- Nome da conexao no Airflow (ex: 'elt_bronze', 'meu_ftp')
        -- Se vazio, usa a conexao padrao do .env para o layer

    host_source VARCHAR(200),
        -- Host do banco de dados de origem (para type_source = 'Postgre')

    port_source INTEGER,
        -- Porta do banco de dados de origem (para type_source = 'Postgre')

    url VARCHAR(500),
        -- URL da fonte: Google Sheets, FTP, S3, etc.

    database_source VARCHAR(100),
        -- Nome do banco de dados de origem (para type_source = 'DW' ou 'SQL')

    schema_source VARCHAR(100),
        -- Schema de origem

    table_source VARCHAR(100),
        -- Tabela de origem (ou nome da aba no Google Sheets)

    query_source TEXT,
        -- SQL query completa (para type_source = 'DW')

    header_row_source INTEGER,
        -- Linha do cabecalho (para Google Sheets / XLSX)

    columns_source TEXT,
        -- Colunas esperadas separadas por virgula (opcional)

    -- === CONFIGURACAO DE DESTINO ===

    conexao_destino_id VARCHAR(100),
        -- Nome da conexao Airflow de destino
        -- Se vazio, usa a conexao padrao do .env para o layer

    database_destiny VARCHAR(100),
        -- Banco de destino (se vazio, usa o padrao do .env)

    schema_destiny VARCHAR(100),
        -- Schema de destino (se vazio, usa o padrao do .env)

    table_destiny VARCHAR(100),
        -- Nome da tabela de destino

    strategy_destiny VARCHAR(20) DEFAULT 'truncate',
        -- 'truncate' = limpa e insere (padrao)
        -- 'append' = apenas insere novos registros
        -- 'replace' = drop, create e insere

    -- === POS-PROCESSAMENTO ===

    pos_query TEXT,
        -- SQL executado APOS a carga (ex: renomear colunas, atualizar metadados)
        -- Placeholder: {schema_destiny}, {table_destiny}

    -- === CONFIGURACAO DE AGENDAMENTO ===

    schedule_cron VARCHAR(50),
        -- Expressao cron para agendar a DAG do projeto no Airflow
        -- Ex: '0 6 * * 1' = toda segunda 06:00
        -- Ex: '45 8 * * 1-5' = dias uteis 08:45
        -- Se vazio, o projeto nao gera DAG propria (usa a DAG geral)

    -- === CONFIGURACAO DE HISTORICO (SCD Tipo 2) ===

    historico_ativo BOOLEAN DEFAULT FALSE,
    historico_unique_keys TEXT,
        -- Colunas chave para historico separadas por virgula

    -- === CONFIG EXTRAS (JSON) ===

    config JSONB DEFAULT '{}',
        -- Configuracoes especificas do extrator
        -- Ex: {"delimiter": ";", "encoding": "latin1", "compress": "gzip"}
        -- Ex: {"sheet_name": "Dados", "header_row": 2}

    -- === METADADOS ===

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indices para consulta eficiente
CREATE INDEX IF NOT EXISTS idx_schedule_type_source ON global.schedule (type_source);
CREATE INDEX IF NOT EXISTS idx_schedule_layer ON global.schedule (layer);
CREATE INDEX IF NOT EXISTS idx_schedule_projeto ON global.schedule (projeto);
CREATE INDEX IF NOT EXISTS idx_schedule_ativo ON global.schedule (ativo);
CREATE INDEX IF NOT EXISTS idx_schedule_ordem ON global.schedule (layer, projeto, ordem);
