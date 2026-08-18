-- ============================================================
-- Migracao: Adiciona colunas do novo ELT a tabela existente
-- sem perder dados. A tabela global.schedule ja existe com
-- a estrutura legada do GARA (sk, host_source, schedule_airflow...)
-- ============================================================

-- layer (caso ainda nao exista)
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS layer VARCHAR(20) NOT NULL DEFAULT 'bronze';

-- Novas colunas do framework ELT
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS projeto VARCHAR(100) DEFAULT 'default';
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS ordem INTEGER DEFAULT 0;
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT TRUE;
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS conexao_origem_id VARCHAR(100);
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS conexao_destino_id VARCHAR(100);
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS strategy_destiny VARCHAR(20) DEFAULT 'truncate';
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS pos_query TEXT;
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS schedule_cron VARCHAR(50);
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS historico_ativo BOOLEAN DEFAULT FALSE;
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS historico_unique_keys TEXT;
ALTER TABLE global.schedule ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}';

-- Indices para as novas colunas
CREATE INDEX IF NOT EXISTS idx_schedule_projeto ON global.schedule (projeto);
CREATE INDEX IF NOT EXISTS idx_schedule_ativo ON global.schedule (ativo);
CREATE INDEX IF NOT EXISTS idx_schedule_ordem ON global.schedule (layer, projeto, ordem);
