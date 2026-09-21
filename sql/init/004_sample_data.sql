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
 'https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/975a51d6f2e7a9ee22a734a42ebd624263812f0c/csv/municipios.csv',
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
 'SELECT codigo_ibge, nome, codigo_uf,
    CASE codigo_uf
      WHEN ''21'' THEN ''MA'' WHEN ''22'' THEN ''PI'' WHEN ''23'' THEN ''CE''
      WHEN ''24'' THEN ''RN'' WHEN ''25'' THEN ''PB'' WHEN ''26'' THEN ''PE''
      WHEN ''27'' THEN ''AL'' WHEN ''28'' THEN ''SE'' WHEN ''29'' THEN ''BA''
    END AS uf,
    CASE codigo_uf
      WHEN ''21'' THEN ''Maranhao'' WHEN ''22'' THEN ''Piaui'' WHEN ''23'' THEN ''Ceara''
      WHEN ''24'' THEN ''Rio Grande do Norte'' WHEN ''25'' THEN ''Paraiba'' WHEN ''26'' THEN ''Pernambuco''
      WHEN ''27'' THEN ''Alagoas'' WHEN ''28'' THEN ''Sergipe'' WHEN ''29'' THEN ''Bahia''
    END AS estado,
    latitude, longitude, siafi_id AS codigo_siafi, ddd, fuso_horario
  FROM global.tb_municipios_ibge
  WHERE codigo_uf IN (''21'', ''22'', ''23'', ''24'', ''25'', ''26'', ''27'', ''28'', ''29'')',
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
