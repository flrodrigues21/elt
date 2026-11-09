-- Spark/MinIO demonstrator. Idempotent so setup.ps1 can apply it to existing volumes.
\connect elt;

INSERT INTO global.schedule (
    type_source, layer, projeto, ordem, ativo, schedule_cron,
    url, table_source, table_destiny, schema_destiny, strategy_destiny, config
)
SELECT
    'CSV_URL', 'bronze', 'municipios_ibge_lakehouse', 1, TRUE, NULL,
    'https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/975a51d6f2e7a9ee22a734a42ebd624263812f0c/csv/municipios.csv',
    'municipios', 'tb_municipios_ibge_lakehouse', 'global', 'truncate',
    '{"delimiter": ",", "encoding": "utf-8", "minio": {"format": "parquet", "object_name": "bronze/municipios/municipios.parquet"}}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM global.schedule
    WHERE projeto = 'municipios_ibge_lakehouse' AND layer = 'bronze'
);

INSERT INTO global.schedule (
    type_source, layer, projeto, ordem, ativo, schedule_cron,
    database_source, schema_source, table_source,
    table_destiny, schema_destiny, strategy_destiny, config
)
SELECT
    'MINIO', 'silver', 'municipios_ibge_lakehouse', 1, TRUE, NULL,
    'minio', 'bronze', 'municipios',
    'tb_municipios_nf_lakehouse', 'global', 'truncate',
    '{
      "engine": "spark",
      "transform": "municipios_silver",
      "minio_source": {"format": "parquet", "object_name": "bronze/municipios/municipios.parquet"},
      "minio": {"format": "parquet", "object_name": "silver/municipios/"},
      "spark": {"partition_by": ["uf"]}
    }'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM global.schedule
    WHERE projeto = 'municipios_ibge_lakehouse' AND layer IN ('silver', 'prata')
);

INSERT INTO global.schedule (
    type_source, layer, projeto, ordem, ativo, schedule_cron,
    database_source, schema_source, table_source,
    table_destiny, schema_destiny, strategy_destiny, config
)
SELECT
    'MINIO', 'gold', 'municipios_ibge_lakehouse', 1, TRUE, NULL,
    'minio', 'silver', 'tb_municipios_nf_lakehouse',
    'dm_municipios_por_uf_lakehouse', 'global', 'truncate',
    '{
      "engine": "spark",
      "transform": "municipios_gold",
      "minio_source": {"format": "parquet", "object_name": "silver/municipios/"},
      "minio": {"format": "parquet", "object_name": "gold/municipios_por_uf/"},
      "spark": {"count_records": true}
    }'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM global.schedule
    WHERE projeto = 'municipios_ibge_lakehouse' AND layer = 'gold'
);
