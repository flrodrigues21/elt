-- ============================================================
-- Exemplo completo: Projeto dados_abertos (CNES) no ELT
-- ============================================================
-- Fluxo:
--   Bronze: tb_estabelecimento_unidade (carga direta do S3/FTP)
--   Silver: Filtra apenas registros de PE (CO_UF = 26)
--   Gold:   Modelo dimensional com joins em municipio e geres
-- ============================================================

-- ============================================================
-- BRONZE - Download do CSV completo do S3 CKAN
-- ============================================================
-- O extrator CSV_URL (S3Extractor) baixa o arquivo ZIP do S3,
-- descompacta o CSV, faz o parse e carrega na tabela de destino.
-- O schedule_cron define que este projeto gera a DAG elt_dados_abertos
-- no Airflow, executando toda segunda-feira as 04:00.
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 url, table_source, table_destiny,
 schema_destiny, strategy_destiny,
 config)
VALUES
('CSV_URL', 'bronze', 'dados_abertos', 1, TRUE,
 '0 4 * * 1',
 'https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip',
 'cnes_estabelecimentos_csv', 'tb_estabelecimento_unidade',
 'global', 'truncate',
 '{"delimiter": ";", "encoding": "latin-1", "compression": "zip"}');

-- ============================================================
-- SILVER - Estabelecimentos de PE
-- ============================================================
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'silver', 'dados_abertos', 1, TRUE,
 '0 4 * * 1',
 'bronze', 'global',
 'SELECT *
  FROM global.tb_estabelecimento_unidade
  WHERE "CO_UF" = 26',
 'tb_estabelecimento_pe', 'global', 'truncate');

-- ============================================================
-- GOLD - Dimensao estabelecimento (modelo dimensional)
-- ============================================================
INSERT INTO global.schedule
(type_source, layer, projeto, ordem, ativo,
 schedule_cron,
 database_source, schema_source,
 query_source,
 table_destiny, schema_destiny, strategy_destiny)
VALUES
('DW', 'gold', 'dados_abertos', 1, TRUE,
 '0 4 * * 1',
 'prata', 'global',
 $$SELECT
    LPAD("CO_CNES"::text, 7, '0') AS nr_cnes,
    '' AS sk_estabelecimento,
    '' AS cd_estabelecimento,
    '' AS cd_municipio_gestor,
    m.cod_ibge_7 AS cd_municipio_ibge,
    m.cod_uf AS cd_uf,
    "NO_RAZAO_SOCIAL" AS nm_razao_social,
    "NO_FANTASIA" AS nm_fantasia,
    '' AS nm_logradouro,
    ' ' AS ds_complement,
    ' ' AS nm_bairro,
    "CO_CEP" AS nr_cod_cep,
    ' ' AS sn_hospital_ambulatorio,
    ' ' AS sn_hospital_internacao,
    "NU_CNPJ_MANTENEDORA" AS nr_cnpj,
    "NU_ENDERECO" AS nr_numero,
    UPPER(m.nome_municipio) AS ds_municipio,
    UNACCENT(UPPER(m.nome_municipio)) AS ds_municipio_sem_acento,
    g.ds_geres AS ds_geres,
    '' AS ds_regiao,
    g.ds_macro AS ds_macro,
    ' ' AS dt_carga_estabelecimento,
    ' ' AS rank
FROM global.tb_estabelecimento_pe e
LEFT JOIN global.tb_municipio m ON e."CO_IBGE" = m.cod_datasus_6
LEFT JOIN global.dm_geres g ON m.cod_ibge_7 = g.cd_munci_pi0$$,
 'dm_estabelecimento', 'global', 'truncate');
