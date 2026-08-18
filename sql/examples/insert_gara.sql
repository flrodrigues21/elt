-- ============================================================
-- Exemplo: Extracao de Google Sheets + transformacoes SQL
-- ============================================================

-- Exemplo de extracao de planilha Google Sheets para a camada bronze
-- O schedule_cron '0 7 * * 5' = toda sexta 07:00
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_source, table_destiny, header_row_source,
 schema_destiny, strategy_destiny)
VALUES
('GOOGLE_SHEETS', 'bronze', 'meu_projeto', 1, TRUE,
 '0 4 * * 1',
 'https://docs.google.com/spreadsheets/d/ABC123/edit',
 'MinhaAba', 'minha_tabela', 2,
 'meu_schema', 'truncate');

-- Exemplo de transformacao SQL na camada silver
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source, query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'silver', 'meu_projeto', 1, TRUE,
 '0 4 * * 1',
 'bronze', 'meu_schema',
 'SELECT * FROM meu_schema.minha_tabela WHERE ativo = true',
 'minha_tabela_tratada', 'meu_schema', 'truncate');

-- Exemplo de modelo dimensional na camada gold
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source, query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'gold', 'meu_projeto', 1, TRUE,
 '0 4 * * 1',
 'prata', 'meu_schema',
 'SELECT DISTINCT categoria FROM meu_schema.minha_tabela_tratada',
 'dm_categoria', 'meu_schema', 'append');
