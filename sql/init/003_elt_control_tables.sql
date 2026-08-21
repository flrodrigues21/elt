-- ============================================================
-- ELT: schema global + tabela schedule + controle_execucao
-- Banco de controle do framework
-- ============================================================

\connect elt;

CREATE SCHEMA IF NOT EXISTS global;

-- ============================================================
-- Tabela de parametrizacao generica ELT
-- ============================================================

CREATE TABLE IF NOT EXISTS global.schedule (
    id SERIAL PRIMARY KEY,

    type_source VARCHAR(50) NOT NULL,
    layer VARCHAR(20) NOT NULL DEFAULT 'bronze',
    projeto VARCHAR(100) DEFAULT 'default',
    ordem INTEGER DEFAULT 0,
    ativo BOOLEAN DEFAULT TRUE,

    conexao_origem_id VARCHAR(100),
    host_source VARCHAR(200),
    port_source INTEGER,
    url VARCHAR(500),
    database_source VARCHAR(100),
    schema_source VARCHAR(100),
    table_source VARCHAR(100),
    query_source TEXT,
    header_row_source INTEGER,
    columns_source TEXT,

    conexao_destino_id VARCHAR(100),
    database_destiny VARCHAR(100),
    schema_destiny VARCHAR(100),
    table_destiny VARCHAR(100),
    strategy_destiny VARCHAR(20) DEFAULT 'truncate',

    pos_query TEXT,

    schedule_cron VARCHAR(50),

    historico_ativo BOOLEAN DEFAULT FALSE,
    historico_unique_keys TEXT,

    config JSONB DEFAULT '{}',

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedule_type_source ON global.schedule (type_source);
CREATE INDEX IF NOT EXISTS idx_schedule_layer ON global.schedule (layer);
CREATE INDEX IF NOT EXISTS idx_schedule_projeto ON global.schedule (projeto);
CREATE INDEX IF NOT EXISTS idx_schedule_ativo ON global.schedule (ativo);
CREATE INDEX IF NOT EXISTS idx_schedule_ordem ON global.schedule (layer, projeto, ordem);

-- ============================================================
-- Tabela de controle de execucao
-- ============================================================

CREATE TABLE IF NOT EXISTS global.controle_execucao (
    id SERIAL PRIMARY KEY,
    processo VARCHAR(100) NOT NULL,
    projeto VARCHAR(100),
    tabela_destino VARCHAR(100),
    database_destino VARCHAR(100),
    schema_destino VARCHAR(100),
    layer VARCHAR(20),
    type_source VARCHAR(50),
    inicio TIMESTAMP NOT NULL DEFAULT NOW(),
    fim TIMESTAMP,
    status VARCHAR(20) DEFAULT 'em_andamento',
    registros_inseridos INTEGER DEFAULT 0,
    erro TEXT,
    metadados JSONB DEFAULT '{}',
    ds_fonte VARCHAR(200),
    trigger_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_controle_execucao_processo ON global.controle_execucao (processo);
CREATE INDEX IF NOT EXISTS idx_controle_execucao_projeto ON global.controle_execucao (projeto);
CREATE INDEX IF NOT EXISTS idx_controle_execucao_status ON global.controle_execucao (status);
CREATE INDEX IF NOT EXISTS idx_controle_execucao_inicio ON global.controle_execucao (inicio);
