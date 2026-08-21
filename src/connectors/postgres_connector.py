import json
import os
import re
import pandas as pd
from sqlalchemy import text, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)


class PostgresConnector:
    def __init__(
        self,
        host: str,
        port: str,
        database: str,
        user: str,
        password: str
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.engine = self._create_engine()

    def _create_engine(self):
        url = URL.create(
            drivername="postgresql",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )
        return create_engine(url)

    def write_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: str = "public",
        if_exists: str = "replace",
        chunksize: int = 10000,
    ):
        if if_exists == "truncate":
            try:
                truncate_query = f'TRUNCATE TABLE "{schema}"."{table_name}";'
                self.execute_script(
                    query=truncate_query,
                    message=f"Tabela {schema}.{table_name} truncada"
                )
            except Exception:
                logger.info(f"Tabela {schema}.{table_name} nao existe, sera criada")
            if_exists = "append"

        total_rows = len(df)
        if total_rows > chunksize:
            logger.info(
                f"Gravando {total_rows} registros em lotes de {chunksize}"
            )
            for start in range(0, total_rows, chunksize):
                end = min(start + chunksize, total_rows)
                chunk = df.iloc[start:end]
                chunk.to_sql(
                    name=table_name,
                    con=self.engine,
                    schema=schema,
                    if_exists=if_exists,
                    index=False,
                )
                if_exists = "append"
                logger.info(f"Gravados {end}/{total_rows} registros")
        else:
            df.to_sql(
                name=table_name,
                con=self.engine,
                schema=schema,
                if_exists=if_exists,
                index=False,
            )

    def read_table(
        self,
        table_name: str,
        schema: str = "public"
    ) -> pd.DataFrame:
        query = f'SELECT * FROM "{schema}"."{table_name}"'
        return pd.read_sql(query, self.engine)

    def execute_script(
        self,
        query: str,
        params: dict | None = None,
        message: str | None = None
    ):
        with self.engine.begin() as conn:
            try:
                conn.execute(text(query), params or {})
                if message:
                    logger.info(message)
                return message
            except SQLAlchemyError as e:
                raise RuntimeError(
                    f"Erro ao executar o script: {str(e)}"
                )

    def apply_metadata(
        self,
        schema: str,
        table_name: str,
        metadata: dict | None = None
    ):
        if not metadata:
            return

        table_metadata = metadata.get(table_name)
        if not table_metadata:
            logger.info(f'{schema}.{table_name} nao possui descricoes')
            return

        table_description = table_metadata.get("description")
        if table_description:
            self.execute_script(
                query=f'COMMENT ON TABLE "{schema}"."{table_name}" IS :description',
                params={"description": table_description}
            )

        columns_metadata = table_metadata.get("columns", {})
        for column_name, column_description in columns_metadata.items():
            if not column_description:
                continue
            self.execute_script(
                query=f'COMMENT ON COLUMN "{schema}"."{table_name}"."{column_name}" IS :description',
                params={"description": column_description}
            )

        logger.info(f'Descricoes de {schema}.{table_name} carregadas com sucesso')


def registrar_execucao(
    processo: str,
    tabela_destino: str,
    status: str,
    registros: int = 0,
    erro: str | None = None,
    metadados: dict | None = None,
    projeto: str | None = None,
    database_destino: str | None = None,
    schema_destino: str | None = None,
    layer: str | None = None,
    type_source: str | None = None,
    ds_fonte: str | None = None,
    trigger_type: str | None = None,
):
    from elt.src.connectors.airflow_connections import AirflowConnector

    airflow = AirflowConnector()
    creds = airflow.get_connection('elt_schedule')
    url = URL.create(
        drivername="postgresql",
        username=creds['user'],
        password=creds['password'],
        host=creds['host'],
        port=creds['port'],
        database=creds['database'],
    )
    engine = create_engine(url)

    fim = 'NOW()' if status in ('sucesso', 'erro') else 'NULL'
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO global.controle_execucao
                    (processo, projeto, tabela_destino,
                     database_destino, schema_destino,
                     layer, type_source,
                     inicio, fim, status, registros_inseridos,
                     erro, metadados, ds_fonte, trigger_type)
                VALUES
                    (:processo, :projeto, :tabela,
                     :database, :schema,
                     :layer, :type_source,
                     NOW(), {fim}, :status, :registros,
                     :erro, CAST(:metadados AS jsonb), :ds_fonte, :trigger_type)
            """),
            {
                'processo': processo,
                'projeto': projeto,
                'tabela': tabela_destino,
                'database': database_destino,
                'schema': schema_destino,
                'layer': layer,
                'type_source': type_source,
                'status': status,
                'registros': registros,
                'erro': erro,
                'metadados': json.dumps(metadados or {}),
                'ds_fonte': ds_fonte,
                'trigger_type': trigger_type,
            }
        )
    logger.info(f'Execucao registrada: {processo}/{tabela_destino} = {status}')
