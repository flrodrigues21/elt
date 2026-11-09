"""Built-in, explicitly registered Spark transformations."""

from ..processing.registry import register_transformation


@register_transformation("municipios_silver")
def municipios_silver(dataframe, *, spark, **_context):
    """Normalize IBGE municipalities and enrich Northeast rows with state data."""
    from pyspark.sql import Window
    from pyspark.sql import functions as functions

    states = spark.createDataFrame(
        [
            (21, "MA", "Maranhao"), (22, "PI", "Piaui"), (23, "CE", "Ceara"),
            (24, "RN", "Rio Grande do Norte"), (25, "PB", "Paraiba"),
            (26, "PE", "Pernambuco"), (27, "AL", "Alagoas"),
            (28, "SE", "Sergipe"), (29, "BA", "Bahia"),
        ],
        ["codigo_uf", "uf", "estado"],
    )
    ranking = Window.partitionBy("codigo_ibge").orderBy(
        functions.col("nome").asc_nulls_last()
    )
    return (
        dataframe.select(
            functions.col("codigo_ibge").cast("long").alias("codigo_ibge"),
            functions.coalesce(functions.trim("nome"), functions.lit("Nao informado")).alias("nome"),
            functions.col("codigo_uf").cast("int").alias("codigo_uf"),
            functions.col("latitude").cast("double").alias("latitude"),
            functions.col("longitude").cast("double").alias("longitude"),
            functions.col("siafi_id").cast("string").alias("codigo_siafi"),
            functions.col("ddd").cast("int").alias("ddd"),
            functions.col("fuso_horario").cast("string").alias("fuso_horario"),
        )
        .filter(functions.col("codigo_ibge").isNotNull())
        .join(states, on="codigo_uf", how="inner")
        .withColumn("dedupe_rank", functions.row_number().over(ranking))
        .filter(functions.col("dedupe_rank") == 1)
        .drop("dedupe_rank")
        .dropDuplicates(["codigo_ibge"])
    )


@register_transformation("municipios_gold")
def municipios_gold(dataframe, **_context):
    """Aggregate the curated municipality grain by Northeast state."""
    from pyspark.sql import functions as functions

    return dataframe.filter(functions.col("codigo_ibge").isNotNull()).groupBy(
        "uf", "estado"
    ).agg(
        functions.countDistinct("codigo_ibge").alias("total_municipios"),
        functions.avg("latitude").alias("latitude_media"),
    )
