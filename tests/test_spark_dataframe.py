import pytest


pyspark = pytest.importorskip("pyspark")

from elt.src.spark.transformations import municipios_gold, municipios_silver


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    session = SparkSession.builder.master("local[1]").appName("spark-core-tests").getOrCreate()
    yield session
    session.stop()


def test_municipios_transformations(spark):
    source = spark.createDataFrame(
        [
            ("2100055", " Acailandia ", "21", "-4.9", "-47.4", "105", "99", "America/Fortaleza"),
            ("2100055", "duplicate", "21", "-4.9", "-47.4", "105", "99", "America/Fortaleza"),
            ("2900108", None, "29", "-13.2", "-41.6", "334", "77", "America/Bahia"),
            ("3550308", "Sao Paulo", "35", "-23.5", "-46.6", "7107", "11", "America/Sao_Paulo"),
        ],
        ["codigo_ibge", "nome", "codigo_uf", "latitude", "longitude", "siafi_id", "ddd", "fuso_horario"],
    )
    silver = municipios_silver(source, spark=spark)
    assert silver.count() == 2
    assert {row.uf for row in silver.collect()} == {"MA", "BA"}
    assert "codigo_siafi" in silver.columns

    gold = municipios_gold(silver).collect()
    assert len(gold) == 2
    assert sum(row.total_municipios for row in gold) == 2
