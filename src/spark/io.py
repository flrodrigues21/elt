"""Spark JDBC and S3A/MinIO DataFrame helpers."""

import os

from typing import Any, Mapping


_WRITE_MODES = {
    "truncate": "overwrite",
    "replace": "overwrite",
    "append": "append",
    "fail": "errorifexists",
}
_FORMATS = frozenset({"parquet", "csv", "json", "orc"})


def map_write_strategy(strategy: str) -> str:
    if not isinstance(strategy, str):
        raise ValueError("Write strategy must be a string")
    try:
        return _WRITE_MODES[strategy.strip().lower()]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported write strategy {strategy!r}; expected append, fail, replace, or truncate"
        ) from exc


def _required(config: Mapping[str, Any], key: str) -> Any:
    value = config.get(key)
    if value is None or value == "":
        raise ValueError(f"Missing required connection field: {key}")
    return value


def _jdbc_url(credentials: Mapping[str, Any]) -> str:
    if credentials.get("url"):
        return str(credentials["url"])
    host = _required(credentials, "host")
    port = credentials.get("port", 5432)
    database = _required(credentials, "database")
    return f"jdbc:postgresql://{host}:{port}/{database}"


def read_jdbc(spark, credentials: Mapping[str, Any], *, query: str | None = None, table: str | None = None):
    if bool(query) == bool(table):
        raise ValueError("Exactly one of query or table is required for a JDBC read")
    options = {
        "url": _jdbc_url(credentials),
        "user": _required(credentials, "user"),
        "password": _required(credentials, "password"),
        "driver": credentials.get("driver", "org.postgresql.Driver"),
        "dbtable": f"({query}) AS source_data" if query else table,
    }
    return spark.read.format("jdbc").options(**options).load()


def write_jdbc(dataframe, credentials: Mapping[str, Any], *, table: str, strategy: str) -> None:
    if not table:
        raise ValueError("A destination JDBC table is required")
    options = {
        "url": _jdbc_url(credentials),
        "user": _required(credentials, "user"),
        "password": _required(credentials, "password"),
        "driver": credentials.get("driver", "org.postgresql.Driver"),
        "dbtable": table,
    }
    writer = dataframe.write.format("jdbc").options(**options).mode(map_write_strategy(strategy))
    if strategy.strip().lower() == "truncate":
        writer = writer.option("truncate", "true")
    writer.save()


def _minio_path(config: Mapping[str, Any], default_name: str | None = None) -> str:
    bucket = config.get("bucket") or os.getenv("MINIO_BUCKET")
    if not bucket:
        raise ValueError("Missing MinIO bucket in config or MINIO_BUCKET")
    object_name = config.get("object_name") or default_name
    if not object_name:
        raise ValueError("Missing required MinIO field: object_name")
    return f"s3a://{bucket}/{str(object_name).lstrip('/')}"


def _format(config: Mapping[str, Any]) -> str:
    value = str(config.get("format", "parquet")).lower()
    if value not in _FORMATS:
        raise ValueError(f"Unsupported Spark file format: {value}")
    return value


def read_minio(spark, config: Mapping[str, Any], *, default_name: str | None = None):
    return spark.read.format(_format(config)).load(_minio_path(config, default_name))


def write_minio(
    dataframe,
    config: Mapping[str, Any],
    *,
    strategy: str,
    partition_by: list[str] | None = None,
    default_name: str | None = None,
) -> None:
    writer = dataframe.write.format(_format(config)).mode(map_write_strategy(strategy))
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.save(_minio_path(config, default_name))


# Names that make the backing service explicit at call sites.
read_minio_dataframe = read_minio
write_minio_dataframe = write_minio
read_jdbc_dataframe = read_jdbc
write_jdbc_dataframe = write_jdbc
