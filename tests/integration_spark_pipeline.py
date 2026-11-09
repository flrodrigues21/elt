"""Runtime check for the Docker Spark/MinIO municipality pipeline.

Run after triggering the general ``elt_pipeline`` DAG:
docker exec elt-airflow-scheduler python /opt/airflow/elt/tests/integration_spark_pipeline.py
"""

import os

from elt.src.spark.session import get_spark_session


def main() -> None:
    spark = get_spark_session("elt-integration-check-municipios")
    try:
        bucket = os.environ["MINIO_BUCKET"]
        silver = spark.read.parquet(f"s3a://{bucket}/silver/municipios/")
        gold = spark.read.parquet(f"s3a://{bucket}/gold/municipios_por_uf/")

        assert set(silver.columns) >= {"codigo_ibge", "nome", "uf", "estado"}
        assert silver.select("codigo_ibge").distinct().count() == silver.count()
        assert gold.count() == 9
        assert gold.agg({"total_municipios": "sum"}).first()[0] == silver.count()
        print("Spark integration passed: Bronze -> Silver -> Gold on MinIO")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
