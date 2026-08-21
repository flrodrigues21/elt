import logging
import os

import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

from elt.src.schedule.schedule_table import load_schedule_table, get_steps
from elt.src.connectors.postgres_connector import PostgresConnector, registrar_execucao
from elt.src.connectors.minio_connector import MinioConnector
from elt.src.connectors.airflow_connections import AirflowConnector

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def connect_db(connection_id: str):
    airflow_connector = AirflowConnector()
    credentials = airflow_connector.get_connection(connection_id)
    postgres = PostgresConnector(
        host=credentials['host'],
        port=credentials['port'],
        database=credentials['database'],
        user=credentials['user'],
        password=credentials['password']
    )
    return postgres, credentials


def _parse_config(row):
    config = row.get('config')
    if isinstance(config, str):
        try:
            import json
            return json.loads(config)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(config, dict):
        return config
    return {}


def transform(
    projeto: str | None = None,
    connection_origem_id: str | None = 'elt_bronze',
    connection_destino_id: str | None = 'elt_silver',
    trigger_type: str | None = None,
):
    df_schedule = load_schedule_table()
    df_steps = get_steps(
        df_schedule,
        layer=['silver', 'prata'],
        projeto=projeto
    )

    if df_steps.empty:
        logging.warning("Nenhum step de transformacao silver encontrado")
        return {}

    postgres_destino, cred_destino = connect_db(connection_destino_id)

    schema_default = os.getenv('SILVER_SCHEMA', 'global')

    logging.info(
        f'[SILVER] Destino: {cred_destino["host"]}:{cred_destino["port"]} '
        f'banco={cred_destino["database"]} schema={schema_default}'
    )

    resultados = {}
    postgres_origem = None

    for _, row in df_steps.iterrows():
        table_destiny = row['table_destiny']
        schema_destiny = row.get('schema_destiny') or schema_default
        strategy = row.get('strategy_destiny') or 'truncate'
        query = row.get('query_source')
        config = _parse_config(row.to_dict())
        minio_source_config = config.get("minio_source")

        try:
            if minio_source_config:
                minio_src = MinioConnector(minio_source_config)
                fmt = minio_source_config.get("format", "parquet")
                object_name = minio_source_config.get(
                    "object_name", f"{table_destiny}.{fmt}"
                )
                logging.info(f"[SILVER] Lendo de MinIO: minio://{minio_src.bucket}/{object_name}")
                df = minio_src.read_dataframe(object_name=object_name, format=fmt)
                logging.info(f"[SILVER] Lido {len(df)} registros do MinIO")
            else:
                if not query:
                    logging.error(f"query_source nao definida para {table_destiny}")
                    resultados[table_destiny] = {'status': 'erro', 'erro': 'query_source vazio'}
                    continue

                if postgres_origem is None:
                    postgres_origem, cred_origem = connect_db(connection_origem_id)
                    logging.info(
                        f'[SILVER] Conectado a origem: {cred_origem["host"]}:{cred_origem["port"]} '
                        f'banco={cred_origem["database"]}'
                    )

                database_source = row.get('database_source')
                if database_source and ('prata' in database_source or 'silver' in database_source):
                    if postgres_destino is None:
                        postgres_destino, cred_destino = connect_db(connection_destino_id)

                logging.info(f"[SILVER] Executando query para {table_destiny}")
                df = pd.read_sql(text(query), postgres_origem.engine)
                logging.info(f"[SILVER] Lido {len(df)} registros da origem")

            minio_sink_config = config.get("minio")
            if minio_sink_config:
                minio_conn = MinioConnector(minio_sink_config)
                fmt = minio_sink_config.get("format", "parquet")
                object_name = minio_sink_config.get(
                    "object_name", f"{table_destiny}.{fmt}"
                )
                minio_conn.upload_dataframe(
                    df=df,
                    object_name=object_name,
                    format=fmt,
                )
                logging.info(
                    f"[SILVER] Enviado para MinIO: {object_name} ({len(df)} registros)"
                )
            else:
                postgres_destino.write_dataframe(
                    df=df,
                    table_name=table_destiny,
                    schema=schema_destiny,
                    if_exists=strategy
                )
                logging.info(f"[SILVER] Tabela {schema_destiny}.{table_destiny} criada/atualizada com {len(df)} registros")

            pos_query = row.get('pos_query')
            if pos_query:
                parsed_query = pos_query.format(
                    schema_destiny=schema_destiny,
                    table_destiny=table_destiny
                )
                postgres_destino.execute_script(parsed_query)

            resultados[table_destiny] = {
                'status': 'sucesso',
                'registros': len(df)
            }

            registrar_execucao(
                processo='silver',
                projeto=row.get('projeto', 'default'),
                tabela_destino=table_destiny,
                database_destino=cred_destino['database'],
                schema_destino=schema_destiny,
                status='sucesso',
                registros=len(df),
                layer='silver',
                type_source='MINIO' if minio_source_config else 'DW',
                trigger_type=trigger_type,
            )

            logging.info(f"[SILVER] Finalizado: {schema_destiny}.{table_destiny} ({len(df)} registros)")

        except Exception as e:
            erro_msg = str(e)
            projeto_val = row.get('projeto', 'default')
            erro_msg += f"\n| Consulta: SELECT * FROM global.schedule WHERE projeto = '{projeto_val}' AND layer = 'silver' AND table_destiny = '{table_destiny}';"
            logging.exception(f"Erro ao transformar {table_destiny}: {erro_msg}")
            resultados[table_destiny] = {
                'status': 'erro',
                'erro': erro_msg
            }

            registrar_execucao(
                processo='silver',
                projeto=projeto_val,
                tabela_destino=table_destiny,
                database_destino=cred_destino['database'],
                schema_destino=schema_destiny,
                status='erro',
                erro=erro_msg,
                layer='silver',
                type_source='MINIO' if minio_source_config else 'DW',
                trigger_type=trigger_type,
            )

    return resultados
