"""Validation for per-step processing configuration."""

import json
from typing import Any, Mapping


VALID_ENGINES = frozenset({"python", "sql", "spark"})


def parse_processing_config(value: Any) -> dict[str, Any]:
    """Parse and validate a config JSON value or a schedule row containing it."""
    if isinstance(value, Mapping) and "config" in value:
        value = value["config"]

    if value is None or value == "":
        config: dict[str, Any] = {}
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Malformed processing config JSON: {exc}") from exc
        if not isinstance(decoded, dict):
            raise ValueError("Processing config JSON must contain an object")
        config = decoded
    elif isinstance(value, Mapping):
        config = dict(value)
    else:
        raise TypeError("Processing config must be a JSON object, string, or null")

    engine = config.get("engine", "python")
    if not isinstance(engine, str) or engine not in VALID_ENGINES:
        raise ValueError(
            f"Invalid processing engine {engine!r}; expected one of: python, spark, sql"
        )
    config["engine"] = engine

    transform = config.get("transform")
    if transform is not None and (not isinstance(transform, str) or not transform.strip()):
        raise ValueError("Processing config 'transform' must be a non-empty string")

    spark = config.get("spark", {})
    if not isinstance(spark, Mapping):
        raise ValueError("Processing config 'spark' must be an object")
    spark = dict(spark)
    partition_by = spark.get("partition_by")
    if partition_by is not None:
        if (
            not isinstance(partition_by, list)
            or not partition_by
            or any(not isinstance(column, str) or not column.strip() for column in partition_by)
        ):
            raise ValueError("Processing config 'spark.partition_by' must be a non-empty list of column names")
    count_records = spark.get("count_records", False)
    if not isinstance(count_records, bool):
        raise ValueError("Processing config 'spark.count_records' must be a boolean")
    spark["count_records"] = count_records
    config["spark"] = spark
    return config


def resolve_engine(value: Any) -> str:
    """Return the validated engine, defaulting to ``python``."""
    return parse_processing_config(value)["engine"]


# Concise alias for callers that already operate in processing context.
parse_config = parse_processing_config
