import logging

import oracledb
import pandas as pd

from elt.src.connectors.airflow_connections import AirflowConnector
from elt.src.connectors.oracle_connector import OracleConnector
from elt.src.extractors.base import BaseExtractor
from elt.src.utils.validation import validate_identifier

logger = logging.getLogger(__name__)


class OracleExtractor(BaseExtractor):
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.source_connection = self.config.get("connection_airflow")
        if not self.source_connection or not str(self.source_connection).strip():
            raise ValueError(
                "A chave 'connection_airflow' e obrigatoria no config "
                "para o extrator ORACLE (ex.: {'connection_airflow': 'sisus_oracle'})."
            )
        self.source_connection = str(self.source_connection).strip()
        self.schema_source = None
        self.table_source = None
        self.query_source = None
        self.connector = self._build_connector()

    def _build_connector(self) -> OracleConnector:
        airflow_connector = AirflowConnector()
        creds = airflow_connector.get_connection(self.source_connection)

        from elt.src.connectors.airflow_connections import _sanitize_for_log
        logger.debug(f"Airflow connection '{self.source_connection}': host={_sanitize_for_log(creds.get('host'))}, user={_sanitize_for_log(creds.get('user'))}")

        host = creds.get("host") or self.config.get("host")
        port = creds.get("port") or self.config.get("port") or 1521
        user = creds.get("user") or self.config.get("user")
        password = creds.get("password") or self.config.get("password")
        service = (
            creds.get("service")
            or creds.get("schema")
            or self.config.get("service")
            or self.config.get("service_name")
            or ""
        )

        if not host or not user or not password or not service:
            raise ValueError(
                f"Conexao '{self.source_connection}' incompleta. "
                f"host={bool(host)}, user={bool(user)}, service={bool(service)}. "
                f"Verifique a conexao Airflow ou a config."
            )

        logger.info(f"Oracle connector: host={host}, port={port}, service={service}, user={user}")

        return OracleConnector(
            host=host,
            port=port,
            service=service,
            user=user,
            password=password,
        )

    def _build_query(self) -> str:
        if self.query_source and str(self.query_source).strip():
            return str(self.query_source)
        if not self.table_source or not str(self.table_source).strip():
            raise ValueError(
                "Informe query_source ou table_source na schedule para o extrator ORACLE."
            )
        safe_schema = validate_identifier(self.schema_source, "schema_source") if self.schema_source else None
        safe_table = validate_identifier(self.table_source, "table_source")
        target = (
            f'"{safe_schema}"."{safe_table}"'
            if safe_schema
            else f'"{safe_table}"'
        )
        return f"SELECT * FROM {target}"

    def extract(self, row: dict) -> pd.DataFrame:
        self.schema_source = row.get("schema_source") or self.schema_source
        self.table_source = row.get("table_source") or self.table_source
        if not self.query_source and row.get("query_source"):
            self.query_source = row.get("query_source")

        query = self._build_query()
        logger.info(
            f"ORACLE [{self.source_connection}] executando: {query}"
        )

        try:
            conn = self.connector._get_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            df = pd.DataFrame(rows, columns=columns)
            cursor.close()
            logger.info(f"Extraidos {len(df)} registros do Oracle")
            return df
        except Exception as e:
            error_msg = str(e)
            if "ORA-01843" in error_msg or "ORA-01861" in error_msg:
                logger.warning(
                    f"Erro de formato de data no Oracle, refazendo com casts para text: {e}"
                )
                return self._extract_safe(query)
            raise

    def _extract_safe(self, original_query: str) -> pd.DataFrame:
        conn = self.connector._get_connection()
        cursor = conn.cursor()

        if self.schema_source and self.table_source:
            cursor.execute(
                "SELECT column_name FROM all_tab_columns "
                "WHERE owner = UPPER(:owner) AND table_name = UPPER(:tbl)",
                {"owner": self.schema_source, "tbl": self.table_source},
            )
            columns = [row[0] for row in cursor.fetchall()]
            select_parts = [f'"{c}" AS "{c}"' for c in columns]
            safe_query = (
                f"SELECT {', '.join(select_parts)} "
                f'FROM "{self.schema_source}"."{self.table_source}"'
            )
        else:
            safe_query = original_query

        logger.info(f"ORACLE [{self.source_connection}] query segura: {safe_query}")
        cursor.execute(safe_query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        cursor.close()
        return pd.DataFrame(rows, columns=columns)
