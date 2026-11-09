"""Central Spark session construction."""

import os


def _is_secure(value: str | None) -> bool:
    return (value or "false").strip().lower() in {"1", "true", "yes", "on"}


def get_spark_session(app_name: str):
    """Build or reuse the consistently configured project Spark session."""
    if not isinstance(app_name, str) or not app_name.strip():
        raise ValueError("app_name must be a non-empty string")

    from pyspark.sql import SparkSession

    secure = _is_secure(os.getenv("MINIO_SECURE"))
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000").rstrip("/")
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"{'https' if secure else 'http'}://{endpoint}"

    builder = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER_URL", "local[2]"))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.hadoop.fs.s3a.endpoint", endpoint)
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_ACCESS_KEY", ""))
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_SECRET_KEY", ""))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", str(secure).lower())
        .config(
            "spark.redaction.regex",
            "(?i)secret|password|passwd|token|access[.]?key|credential",
        )
        .config(
            "spark.sql.redaction.options.regex",
            "(?i)password|secret|token|access[.]?key",
        )
    )
    driver_host = os.getenv("SPARK_DRIVER_HOST")
    driver_bind_address = os.getenv("SPARK_DRIVER_BIND_ADDRESS")
    if driver_host:
        builder = builder.config("spark.driver.host", driver_host)
    if driver_bind_address:
        builder = builder.config("spark.driver.bindAddress", driver_bind_address)
    return builder.getOrCreate()
