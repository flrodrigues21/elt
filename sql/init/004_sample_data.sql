-- ============================================================
-- Dados de exemplo para o lab
-- Dataset: Municipios Brasileiros (IBGE) - GitHub Publico
-- Pipeline: CSV GitHub -> Bronze -> Silver (Nordeste) -> Gold (agg por UF)
-- ============================================================

\connect elt;

-- ============================================================
-- BRONZE: Download CSV direto do GitHub
-- ============================================================
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_source, table_destiny,
 schema_destiny, strategy_destiny,
 config)
VALUES
('CSV_URL', 'bronze', 'municipios_ibge', 1, TRUE,
 '0 4 * * 1',
 'https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/main/csv/municipios.csv',
 'municipios', 'tb_municipios_ibge',
 'global', 'truncate',
 '{"delimiter": ",", "encoding": "utf-8"}');

-- ============================================================
-- SILVER: Filtrar municipios da regiao Nordeste
-- ============================================================
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'silver', 'municipios_ibge', 1, TRUE,
 '0 4 * * 1',
 'bronze', 'global',
 'SELECT codigo_ibge, nome, codigo_uf, uf, estado, latitude, longitude, codigo_siafi, ddd, fuso_horario FROM global.tb_municipios_ibge',
 'tb_municipios_nf', 'global', 'truncate');

-- ============================================================
-- GOLD: Agregacao - quantidade de municipios por UF
-- ============================================================
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'gold', 'municipios_ibge', 1, TRUE,
 '0 4 * * 1',
 'silver', 'global',
 'SELECT uf, estado, COUNT(*) AS total_municipios FROM global.tb_municipios_nf GROUP BY uf, estado ORDER BY total_municipios DESC',
 'dm_municipios_por_uf', 'global', 'truncate');
