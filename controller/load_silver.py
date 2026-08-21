import logging
import os

from dotenv import load_dotenv

from elt.models.silver.transform import transform

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def _get_trigger_type(**kwargs) -> str | None:
    dag_run = kwargs.get('dag_run')
    if dag_run:
        return getattr(dag_run, 'run_type', None)
    return None


def load_silver(projeto: str | None = None, **kwargs):
    logging.info("[SILVER] Inicio da carga na camada silver")

    trigger_type = _get_trigger_type(**kwargs)
    resultados = transform(
        projeto=projeto,
        connection_origem_id='elt_bronze',
        connection_destino_id='elt_silver',
        trigger_type=trigger_type,
    )

    if not resultados:
        logging.warning("Nenhuma transformacao silver executada")
        return

    erros = []
    for tabela, resultado in resultados.items():
        status = resultado.get('status', 'desconhecido')
        registros = resultado.get('registros', 0)
        logging.info(f"  {tabela}: {status} ({registros} registros)")
        if status == 'erro':
            erros.append(f"{tabela}: {resultado.get('erro', 'erro desconhecido')}")

    if erros:
        raise RuntimeError(f"Erros na camada silver:\n" + "\n".join(erros))

    try:
        postgres, _ = connect_prata()
        schema = os.getenv('SILVER_SCHEMA', 'global')
        postgres.execute_script(
            f'truncate table {schema}.atualizacao_dados;'
        )
        postgres.execute_script(
            f'insert into {schema}.atualizacao_dados values (current_timestamp);'
        )
        logging.info('Data e hora da carga na camada silver registrada')
    except Exception as e:
        logging.warning(f'Nao foi possivel registrar atualizacao: {e}')

    logging.info("[SILVER] Carga silver finalizada com sucesso!")


def connect_prata():
    from elt.src.connectors.airflow_connections import AirflowConnector
    from elt.src.connectors.postgres_connector import PostgresConnector
    airflow_connector = AirflowConnector()
    credentials = airflow_connector.get_connection('elt_silver')
    postgres = PostgresConnector(
        host=credentials['host'],
        port=credentials['port'],
        database=credentials['database'],
        user=credentials['user'],
        password=credentials['password']
    )
    return postgres, credentials
