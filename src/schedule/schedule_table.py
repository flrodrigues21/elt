import os
import logging
import pandas as pd
from dotenv import load_dotenv

from elt.src.connectors.postgres_connector import PostgresConnector
from elt.src.connectors.airflow_connections import AirflowConnector

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def connect_db(connection_id: str | None = None):
    airflow_connector = AirflowConnector()
    credentials = airflow_connector.get_connection(connection_id)
    credentials['schema'] = os.getenv('SCHEDULE_SCHEMA')
    postgres = PostgresConnector(
        host=credentials['host'],
        port=credentials['port'],
        database=credentials['database'],
        user=credentials['user'],
        password=credentials['password']
    )
    return postgres, credentials


def load_schedule_table(connection_id: str | None = 'elt_schedule') -> pd.DataFrame:
    postgres, credentials = connect_db(connection_id)
    schema = credentials['schema'] or 'global'
    table = os.getenv('SCHEDULE_TABLE', 'schedule')
    df_schedule = postgres.read_table(table, schema)
    logging.info(f'Tabela {schema}.{table} conectada com sucesso!')
    return df_schedule


def get_steps(
    df_schedule: pd.DataFrame,
    layer: str | None = None,
    projeto: str | None = None,
    type_source: str | None = None
) -> pd.DataFrame:
    df = df_schedule[df_schedule['ativo'] == True].copy()

    if layer:
        layers = layer if isinstance(layer, list) else [layer]
        df = df[df['layer'].isin(layers)]
    if projeto:
        df = df[df['projeto'] == projeto]
    if type_source:
        df = df[df['type_source'] == type_source]

    return df.sort_values('ordem')
