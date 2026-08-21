import json
import logging
import os

import pandas as pd
from dotenv import load_dotenv

from elt.src.schedule.schedule_table import load_schedule_table, get_steps
from elt.src.connectors.postgres_connector import PostgresConnector, registrar_execucao
from elt.src.connectors.minio_connector import MinioConnector
from elt.src.connectors.airflow_connections import AirflowConnector
from elt.src.extractors import get_extractor, EXTRACTOR_REGISTRY

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
            return json.loads(config)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(config, dict):
        return config
    return {}


def extract_and_load(
    projeto: str | None = None,
    connection_id: str | None = 'elt_bronze',
    trigger_type: str | None = None,
):
    df_schedule = load_schedule_table()
    df_steps = get_steps(
        df_schedule,
        layer='bronze',
        projeto=projeto
    )

    if df_steps.empty:
        logging.warning("Nenhum step de extracao encontrado na schedule")
        return {}

    postgres, credentials = connect_db(connection_id)
    host = credentials['host']
    port = credentials['port']
    db = credentials['database']

    schema_default = os.getenv('BRONZE_SCHEMA', 'global')

    logging.info(
        f'[BRONZE] Conectado a origem: {host}:{port} | banco={db} | schema={schema_default}'
    )

    resultados = {}

    for _, row in df_steps.iterrows():
        type_source = str(row['type_source']).upper().strip()
        table_destiny = row['table_destiny']
        schema_destiny = row.get('schema_destiny') or schema_default
        strategy = row.get('strategy_destiny') or 'truncate'

        logging.info(
            f"[BRONZE] Processando [{type_source}] -> {schema_destiny}.{table_destiny}"
        )

        try:
            config = {}
            if type_source == 'DW':
                database_source = row.get('database_source')
                query = row.get('query_source')
                if not query:
                    logging.error(f"query_source nao definida para {table_destiny}")
                    resultados[table_destiny] = {
                        'status': 'erro', 'erro': 'query_source vazio'
                    }
                    continue
                logging.info(f"[BRONZE] Executando query contra {database_source}.{row.get('schema_source')}")
                df = pd.read_sql(query, postgres.engine)

            elif type_source in ('GOOGLE_SHEETS',):
                url = row.get('url')
                if not url:
                    logging.error(f"URL nao definida para {table_destiny}")
                    resultados[table_destiny] = {
                        'status': 'erro', 'erro': 'url vazio'
                    }
                    continue
                conn_id = row.get('conexao_origem_id')
                if pd.isna(conn_id) or not str(conn_id).strip():
                    conn_id = os.getenv(
                        'GOOGLE_SHEETS_CONN_ID', 'google_sheets'
                    )
                logging.info(f"[BRONZE] Conectado a origem Google Sheets: {url}")
                extractor_class = get_extractor(type_source)
                extractor = extractor_class(url, conn_id=conn_id)
                df = extractor.extract(row.to_dict())

            elif type_source == 'POSTGRE':
                config = _parse_config(row.to_dict())
                if not config.get('connection_airflow'):
                    logging.error(
                        f"config.connection_airflow nao definida para {table_destiny}"
                    )
                    resultados[table_destiny] = {
                        'status': 'erro',
                        'erro': 'config.connection_airflow obrigatoria para POSTGRES',
                    }
                    continue
                extractor_class = get_extractor(type_source)
                extractor = extractor_class(config=config)
                df = extractor.extract(row.to_dict())

            elif type_source == 'ORACLE':
                config = _parse_config(row.to_dict())
                if not config.get('connection_airflow'):
                    logging.error(
                        f"config.connection_airflow nao definida para {table_destiny}"
                    )
                    resultados[table_destiny] = {
                        'status': 'erro',
                        'erro': 'config.connection_airflow obrigatoria para ORACLE',
                    }
                    continue
                extractor_class = get_extractor(type_source)
                extractor = extractor_class(config=config)
                df = extractor.extract(row.to_dict())

            elif type_source in ('FTP', 'S3', 'CKAN', 'CSV_URL', 'MINIO', 'XLSX'):
                extractor_class = get_extractor(type_source)
                row_dict = row.to_dict()
                config = _parse_config(row_dict)

                source_url = row.get('url', 'N/A')
                logging.info(f"[BRONZE] Conectado a origem: {source_url}")

                if type_source == 'FTP':
                    row_dict['config'] = config
                    extractor = extractor_class(config)
                elif type_source in ('S3', 'CKAN', 'CSV_URL'):
                    row_dict['config'] = config
                    extractor = extractor_class()
                elif type_source == 'MINIO':
                    row_dict['config'] = config
                    extractor = extractor_class()
                elif type_source == 'XLSX':
                    file_path = config.get('file_path', row.get('url', ''))
                    if not file_path:
                        logging.error(f"file_path nao definido para {table_destiny}")
                        resultados[table_destiny] = {
                            'status': 'erro', 'erro': 'file_path vazio'
                        }
                        continue
                    extractor = extractor_class(file_path)

                df = extractor.extract(row_dict)

            else:
                extractor_class = get_extractor(type_source)
                row_dict = row.to_dict()
                config = _parse_config(row_dict)
                row_dict['config'] = config
                extractor = extractor_class(row_dict)
                df = extractor.extract(row_dict)

            logging.info(f"[BRONZE] Lido {len(df)} registros da origem")

            minio_config = config.get("minio")
            if minio_config:
                minio_conn = MinioConnector(minio_config)
                fmt = minio_config.get("format", "parquet")
                object_name = minio_config.get(
                    "object_name", f"{table_destiny}.{fmt}"
                )
                minio_conn.upload_dataframe(
                    df=df,
                    object_name=object_name,
                    format=fmt,
                )
                logging.info(
                    f"[BRONZE] Enviado para MinIO: {object_name} ({len(df)} registros)"
                )
            else:
                chunksize = config.get('chunksize', 10000)
                postgres.write_dataframe(
                    df=df,
                    table_name=table_destiny,
                    schema=schema_destiny,
                    if_exists=strategy,
                    chunksize=chunksize,
                )
                logging.info(
                    f"[BRONZE] Tabela {schema_destiny}.{table_destiny} criada/atualizada com {len(df)} registros"
                )

            pos_query = row.get('pos_query')
            if pos_query and str(pos_query).strip():
                parsed_query = str(pos_query).format(
                    schema_destiny=schema_destiny,
                    table_destiny=table_destiny
                )
                postgres.execute_script(parsed_query)

            resultados[table_destiny] = {
                'status': 'sucesso',
                'registros': len(df)
            }

            registrar_execucao(
                processo='bronze',
                projeto=row.get('projeto', 'default'),
                tabela_destino=table_destiny,
                database_destino=db,
                schema_destino=schema_destiny,
                status='sucesso',
                registros=len(df),
                layer='bronze',
                type_source=type_source,
                ds_fonte=row.get('url', ''),
                trigger_type=trigger_type,
            )

            logging.info(f"[BRONZE] Finalizado: {schema_destiny}.{table_destiny} ({len(df)} registros)")

        except Exception as e:
            erro_msg = str(e)
            projeto_val = row.get('projeto', 'default')
            erro_msg += f"\n| Consulta: SELECT * FROM global.schedule WHERE projeto = '{projeto_val}' AND layer = 'bronze' AND table_destiny = '{table_destiny}';"
            logging.exception(f"Erro ao processar {table_destiny}: {erro_msg}")
            resultados[table_destiny] = {
                'status': 'erro',
                'erro': erro_msg
            }

            registrar_execucao(
                processo='bronze',
                projeto=projeto_val,
                tabela_destino=table_destiny,
                database_destino=db,
                schema_destino=schema_destiny,
                status='erro',
                erro=erro_msg,
                layer='bronze',
                type_source=type_source,
                ds_fonte=row.get('url', ''),
                trigger_type=trigger_type,
            )

    return resultados
