-- ============================================================
-- Tabela de controle de execucao ELT
-- Proposito: Registrar cada execucao de step (bronze, silver, gold)
-- para auditoria, rastreabilidade e monitoramento
-- ============================================================

CREATE TABLE IF NOT EXISTS global.controle_execucao (
    id SERIAL PRIMARY KEY,
    processo VARCHAR(100) NOT NULL,
        -- Nome do processo (ex: 'bronze', 'silver', 'gold')
    projeto VARCHAR(100),
        -- Nome do projeto (ex: 'meu_projeto')
    tabela_destino VARCHAR(100),
        -- Tabela afetada pela execucao
    database_destino VARCHAR(100),
        -- Banco de dados onde a tabela foi gravada (ex: bronze, prata, ouro)
    schema_destino VARCHAR(100),
        -- Schema onde a tabela foi gravada (ex: global)
    layer VARCHAR(20),
        -- Camada: bronze, silver, gold
    type_source VARCHAR(50),
        -- Tipo do extrator ou 'DW'
    inicio TIMESTAMP NOT NULL DEFAULT NOW(),
        -- Inicio da execucao
    fim TIMESTAMP,
        -- Fim da execucao
    status VARCHAR(20) DEFAULT 'em_andamento',
        -- 'em_andamento', 'sucesso', 'erro'
    registros_inseridos INTEGER DEFAULT 0,
        -- Quantidade de registros processados
    erro TEXT,
        -- Mensagem de erro, se houver
    metadados JSONB DEFAULT '{}',
        -- Metadados adicionais (ex: config usada, colunas, fonte)
    ds_fonte VARCHAR(200),
        -- Descricao da fonte de dados
    trigger_type VARCHAR(20),
        -- Tipo de gatilho: 'scheduled', 'manual', 'backfill'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_controle_execucao_processo ON global.controle_execucao (processo);
CREATE INDEX IF NOT EXISTS idx_controle_execucao_projeto ON global.controle_execucao (projeto);
CREATE INDEX IF NOT EXISTS idx_controle_execucao_status ON global.controle_execucao (status);
CREATE INDEX IF NOT EXISTS idx_controle_execucao_inicio ON global.controle_execucao (inicio);
