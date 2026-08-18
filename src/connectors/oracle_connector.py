import logging

import oracledb
import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)


class OracleConnector:
    def __init__(
        self,
        host: str,
        port: str | int,
        service: str,
        user: str,
        password: str,
    ):
        self.host = host
        self.port = int(port) if port else 1521
        self.service = service
        self.user = user
        self.password = password
        self.dsn = self._build_dsn()
        self._connection = None

    def _build_dsn(self) -> str:
        return (
            f"(DESCRIPTION="
            f"(ADDRESS=(PROTOCOL=TCP)(HOST={self.host})(PORT={self.port}))"
            f"(CONNECT_DATA=(SERVICE_NAME={self.service}))"
            f")"
        )

    def _get_connection(self):
        if self._connection is None:
            logger.info(f"Conectando ao Oracle: host={self.host}, port={self.port}, service={self.service}, user={self.user}")
            self._connection = oracledb.connect(
                user=self.user,
                password=self.password,
                dsn=self.dsn,
            )
        return self._connection

    def write_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: str | None = None,
        if_exists: str = "replace",
        chunksize: int = 10000,
    ):
        conn = self._get_connection()

        if if_exists == "truncate":
            try:
                target = (
                    f'"{schema}"."{table_name}"'
                    if schema
                    else f'"{table_name}"'
                )
                self.execute_script(
                    query=f"TRUNCATE TABLE {target};",
                    message=f"Tabela {target} truncada",
                )
            except Exception:
                logger.info(
                    f"Tabela {schema}.{table_name} nao existe, sera criada"
                )
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
                    con=conn,
                    schema=schema,
                    if_exists=if_exists,
                    index=False,
                )
                if_exists = "append"
                logger.info(f"Gravados {end}/{total_rows} registros")
        else:
            df.to_sql(
                name=table_name,
                con=conn,
                schema=schema,
                if_exists=if_exists,
                index=False,
            )

    def read_table(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> pd.DataFrame:
        target = (
            f'"{schema}"."{table_name}"'
            if schema
            else f'"{table_name}"'
        )
        return pd.read_sql(f"SELECT * FROM {target}", self._get_connection())

    def execute_script(
        self,
        query: str,
        params: dict | None = None,
        message: str | None = None,
    ):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or {})
            if message:
                logger.info(message)
            conn.commit()
            return message
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Erro ao executar script Oracle: {str(e)}")
        finally:
            cursor.close()

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None
