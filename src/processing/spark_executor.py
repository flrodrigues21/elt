"""Execution of one Silver or Gold schedule step with Spark."""

import logging
import time
from typing import Any, Mapping

from .config import parse_processing_config
from .registry import get_transformation
from ..spark.io import read_jdbc, read_minio, write_jdbc, write_minio
from ..spark.session import get_spark_session
from ..utils.validation import validate_identifier


logger = logging.getLogger(__name__)


def execute_spark_step(
    row: Mapping[str, Any],
    source_credentials: Mapping[str, Any],
    destination_credentials: Mapping[str, Any],
    *,
    spark=None,
) -> dict[str, Any]:
    """Read, transform, and write exactly one validated Silver/Gold step."""
    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    layer = str(row.get("layer", "")).lower()
    if layer not in {"silver", "prata", "gold"}:
        raise ValueError("Spark execution is limited to Silver or Gold steps")

    config = parse_processing_config(row)
    if config["engine"] != "spark":
        raise ValueError(f"Spark executor cannot run engine {config['engine']!r}")
    transform_name = config.get("transform")
    if not transform_name:
        raise ValueError("Spark processing requires config.transform")

    # Importing this fixed module activates only the project's allow-listed built-ins.
    from ..spark import transformations as _built_in_transformations  # noqa: F401

    transform = get_transformation(transform_name)
    table = row.get("table_destiny")
    if not table:
        raise ValueError("table_destiny is required")
    schema = row.get("schema_destiny") or "global"
    validate_identifier(str(table), "table_destiny")
    validate_identifier(str(schema), "schema_destiny")
    strategy = row.get("strategy_destiny") or "truncate"
    partition_by = config["spark"].get("partition_by")
    project = row.get("projeto") or "default"
    app_name = f"elt-{project}-{layer}-{table}"
    session = spark or get_spark_session(app_name)
    started = time.monotonic()

    source_config = config.get("minio_source")
    if source_config is not None:
        if not isinstance(source_config, Mapping):
            raise ValueError("config.minio_source must be an object")
        dataframe = read_minio(session, source_config, default_name=f"{table}.parquet")
        read_format = str(source_config.get("format", "parquet"))
        source_name = source_config.get("object_name") or f"{table}.parquet"
    else:
        query = row.get("query_source")
        source_table = row.get("table_source")
        if query:
            dataframe = read_jdbc(session, source_credentials, query=query)
            source_name = "query_source"
        elif source_table:
            source_schema = row.get("schema_source") or "global"
            validate_identifier(str(source_schema), "schema_source")
            validate_identifier(str(source_table), "table_source")
            dataframe = read_jdbc(
                session,
                source_credentials,
                table=f"{source_schema}.{source_table}",
            )
            source_name = f"{source_schema}.{source_table}"
        else:
            raise ValueError("query_source or table_source is required for a JDBC source")
        read_format = "jdbc"

    dataframe = transform(dataframe, spark=session, config=config, row=dict(row))
    if dataframe is None:
        raise ValueError(f"Transformation {transform_name!r} returned no DataFrame")

    sink_config = config.get("minio")
    destination = f"{schema}.{table}"
    if sink_config is not None:
        if not isinstance(sink_config, Mapping):
            raise ValueError("config.minio must be an object")
        write_minio(
            dataframe,
            sink_config,
            strategy=strategy,
            partition_by=partition_by,
            default_name=f"{table}.parquet",
        )
        write_format = str(sink_config.get("format", "parquet"))
        destination_name = sink_config.get("object_name") or f"{table}.parquet"
    else:
        if partition_by:
            dataframe = dataframe.repartition(*partition_by)
        write_jdbc(dataframe, destination_credentials, table=destination, strategy=strategy)
        write_format = "jdbc"
        destination_name = destination

    records = dataframe.count() if config["spark"]["count_records"] else None
    duration = time.monotonic() - started
    logger.info(
        "Spark step completed project=%s layer=%s source=%s destination=%s engine=spark app_name=%s "
        "transform=%s read_format=%s write_format=%s partitions=%s records=%s duration_seconds=%.3f",
        project,
        layer,
        source_name,
        destination_name,
        app_name,
        transform_name,
        read_format,
        write_format,
        partition_by or "none",
        records if records is not None else "not_counted",
        duration,
    )
    return {
        "status": "success",
        "table": destination,
        "records": records,
        "duration_seconds": duration,
        "app_name": app_name,
    }


execute_step = execute_spark_step
