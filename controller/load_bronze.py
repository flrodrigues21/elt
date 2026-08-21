import logging
import os

from dotenv import load_dotenv

from elt.models.bronze.extract import extract_and_load
from elt.src.connectors.postgres_connector import PostgresConnector
from elt.src.connectors.airflow_connections import AirflowConnector
from elt.src.historics.history import HistoricoRegistros

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def connect_bronze(connection_id: str):
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


def _get_trigger_type(**kwargs) -> str | None:
    dag_run = kwargs.get('dag_run')
    if dag_run:
        return getattr(dag_run, 'run_type', None)
    return None


def load_bronze(projeto: str | None = None, **kwargs):
    logging.info("[BRONZE] Inicio da carga na camada bronze")

    trigger_type = _get_trigger_type(**kwargs)
    resultados = extract_and_load(projeto=projeto, trigger_type=trigger_type)

    if not resultados:
        logging.warning("Nenhum resultado de extracao")
        return

    erros = []
    for tabela, resultado in resultados.items():
        status = resultado.get('status', 'desconhecido')
        registros = resultado.get('registros', 0)
        logging.info(f"  {tabela}: {status} ({registros} registros)")
        if status == 'erro':
            erros.append(f"{tabela}: {resultado.get('erro', 'erro desconhecido')}")

    if erros:
        raise RuntimeError(f"Erros na camada bronze:\n" + "\n".join(erros))

    logging.info("[BRONZE] Carga bronze finalizada com sucesso!")


def load_bronze_com_historico(
    projeto: str | None = None,
    connection_id: str | None = 'elt_bronze',
    table_configs: dict | None = None,
    **kwargs
):
    load_bronze(projeto=projeto)

    if not table_configs:
        return

    postgres, credentials = connect_bronze(connection_id)
    schema = os.getenv('BRONZE_SCHEMA', 'global')

    for table_name, config in table_configs.items():
        historico = HistoricoRegistros(
            postgres=postgres,
            schema=schema,
            config=config,
        )
        output = historico.sincronizar()
        logging.info(
            f"Historico processado para {table_name}: {output}"
        )
