import logging
import os

import pandas as pd
from dotenv import load_dotenv

from elt.src.schedule.schedule_table import load_schedule_table, get_steps
from elt.src.connectors.postgres_connector import PostgresConnector, registrar_execucao
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


def transform(
    projeto: str | None = None,
    connection_origem_id: str | None = 'elt_silver',
    connection_destino_id: str | None = 'elt_gold',
    trigger_type: str | None = None,
):
    df_schedule = load_schedule_table()
    df_steps = get_steps(
        df_schedule,
        layer='gold',
        projeto=projeto
    )

    if df_steps.empty:
        logging.warning("Nenhum step de transformacao gold encontrado")
        return {}

    postgres_origem, cred_origem = connect_db(connection_origem_id)
    postgres_destino, cred_destino = connect_db(connection_destino_id)

    schema_default = os.getenv('GOLD_SCHEMA', 'global')

    logging.info(
        f'Transformacao gold: {cred_origem["host"]}:{cred_origem["port"]} '
        f'-> {cred_destino["host"]}:{cred_destino["port"]} '
        f'schema={schema_default}'
    )

    resultados = {}

    for _, row in df_steps.iterrows():
        table_destiny = row['table_destiny']
        schema_destiny = row.get('schema_destiny') or schema_default
        strategy = row.get('strategy_destiny') or 'truncate'
        query = row.get('query_source')

        if not query:
            logging.error(f"query_source nao definida para {table_destiny}")
            resultados[table_destiny] = {'status': 'erro', 'erro': 'query_source vazio'}
            continue

        try:
            logging.info(f"Executando query para {table_destiny}")
            df = pd.read_sql(query, postgres_origem.engine)

            logging.info(f"Transformados {len(df)} registros para {table_destiny}")

            postgres_destino.write_dataframe(
                df=df,
                table_name=table_destiny,
                schema=schema_destiny,
                if_exists=strategy
            )

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
                processo='gold',
                projeto=row.get('projeto', 'default'),
                tabela_destino=table_destiny,
                database_destino=cred_destino['database'],
                schema_destino=schema_destiny,
                status='sucesso',
                registros=len(df),
                layer='gold',
                type_source='DW',
                trigger_type=trigger_type,
            )

        except Exception as e:
            erro_msg = str(e)
            projeto_val = row.get('projeto', 'default')
            erro_msg += f"\n| Consulta: SELECT * FROM global.schedule WHERE projeto = '{projeto_val}' AND layer = 'gold' AND table_destiny = '{table_destiny}';"
            logging.exception(f"Erro ao transformar {table_destiny}: {erro_msg}")
            resultados[table_destiny] = {
                'status': 'erro',
                'erro': erro_msg
            }

            registrar_execucao(
                processo='gold',
                projeto=projeto_val,
                tabela_destino=table_destiny,
                database_destino=cred_destino['database'],
                schema_destino=schema_destiny,
                status='erro',
                erro=erro_msg,
                layer='gold',
                type_source='DW',
                trigger_type=trigger_type,
            )

    return resultados
