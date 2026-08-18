import logging
import pandas as pd

from elt.src.connectors.airflow_connections import AirflowConnector
from elt.src.connectors.postgres_connector import PostgresConnector
from elt.src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class PostgresExtractor(BaseExtractor):
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.source_connection = self.config.get('connection_airflow')
        if not self.source_connection or not str(self.source_connection).strip():
            raise ValueError(
                "A chave 'connection_airflow' e obrigatoria no config "
                "para o extrator POSTGRES (ex.: {'connection_airflow': 'caju'})."
            )
        self.source_connection = str(self.source_connection).strip()
        self.schema_source = self.config.get('schema_source', 'public')
        self.table_source = self.config.get('table_source')
        self.query_source = self.config.get('query_source')
        self.chunksize = self.config.get('chunksize', 10000)
        self.engine = self._build_engine()

    def _build_engine(self):
        airflow_connector = AirflowConnector()
        creds = airflow_connector.get_connection(self.source_connection)
        return PostgresConnector(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
        ).engine

    def _build_query(self) -> str:
        if self.query_source and str(self.query_source).strip():
            return str(self.query_source)
        if not self.table_source or not str(self.table_source).strip():
            raise ValueError(
                "Informe query_source ou table_source no config para o extrator POSTGRES."
            )
        return f"SELECT * FROM {self.schema_source}.{self.table_source}"

    def _build_safe_query(self) -> str:
        with self.engine.connect() as conn:
            result = conn.execute(
                f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = '{self.schema_source}'
                  AND table_name = '{self.table_source}'
                """
            )
            columns = [row[0] for row in result.fetchall()]

        select_parts = [f'"{col}"::text AS "{col}"' for col in columns]
        return f"SELECT {', '.join(select_parts)} FROM {self.schema_source}.{self.table_source}"

    def extract(self, row: dict) -> pd.DataFrame:
        if not self.query_source and row.get('query_source'):
            self.query_source = row.get('query_source')
        if not self.table_source and row.get('table_source'):
            self.table_source = row.get('table_source')
        query = self._build_query()
        logger.info(
            f"POSTGRES [{self.source_connection}] "
            f"executando: {query}"
        )
        try:
            return pd.read_sql(query, self.engine)
        except ValueError as e:
            if "year" in str(e) and "out of range" in str(e):
                logger.warning(
                    f"Ano fora do alcance detectado, refazendo com casts para text: {e}"
                )
                safe_query = self._build_safe_query()
                logger.info(
                    f"POSTGRES [{self.source_connection}] "
                    f"refazendo com query segura: {safe_query}"
                )
                return pd.read_sql(safe_query, self.engine)
            raise

    def extract_chunks(self, row: dict):
        if not self.query_source and row.get('query_source'):
            self.query_source = row.get('query_source')
        if not self.table_source and row.get('table_source'):
            self.table_source = row.get('table_source')
        query = self._build_query()
        logger.info(
            f"POSTGRES [{self.source_connection}] "
            f"executando com chunksize={self.chunksize}: {query}"
        )
        try:
            yield from pd.read_sql(query, self.engine, chunksize=self.chunksize)
        except ValueError as e:
            if "year" in str(e) and "out of range" in str(e):
                logger.warning(
                    f"Ano fora do alcance detectado, refazendo com casts para text: {e}"
                )
                safe_query = self._build_safe_query()
                logger.info(
                    f"POSTGRES [{self.source_connection}] "
                    f"refazendo com query segura: {safe_query}"
                )
                yield from pd.read_sql(safe_query, self.engine, chunksize=self.chunksize)
            else:
                raise
