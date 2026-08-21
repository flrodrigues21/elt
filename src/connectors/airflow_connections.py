import logging

from airflow.hooks.base import BaseHook

logger = logging.getLogger(__name__)


def _sanitize_for_log(value):
    if value is None:
        return None
    s = str(value)
    if len(s) > 4:
        return s[:2] + "***" + s[-2:]
    return "***"


class AirflowConnector:
    def __init__(self, connection_ids: list[str] | None = None):
        self.connection_ids = connection_ids or []

    def get_connection(self, conn_id: str) -> dict:
        conn = BaseHook.get_connection(conn_id)

        logger.info(
            f"Connection '{conn_id}': conn_type='{conn.conn_type}', "
            f"host='{conn.host}', port={conn.port}, schema='{conn.schema}'"
        )

        if conn.conn_type == "postgres":
            return {
                "host": conn.host,
                "user": conn.login,
                "password": conn.password,
                "database": conn.schema,
                "port": conn.port,
                "extra": conn.extra_dejson,
            }

        extra = conn.extra_dejson or {}

        service = conn.schema or extra.get("service") or extra.get("service_name") or ""

        if service:
            return {
                "host": conn.host,
                "user": conn.login,
                "password": conn.password,
                "service": service,
                "port": conn.port,
                "extra": extra,
            }

        return {
            "conn_type": conn.conn_type,
            "host": conn.host,
            "user": conn.login,
            "password": conn.password,
            "schema": conn.schema,
            "port": conn.port,
            "extra": extra,
        }

    def get_connections(self, connection_ids: list[str] | None = None) -> dict:
        ids = connection_ids or self.connection_ids
        credentials = {}
        for conn_id in ids:
            credentials[conn_id] = self.get_connection(conn_id)
        return credentials
