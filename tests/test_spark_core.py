import pathlib

import pytest

from elt.src.processing.config import parse_processing_config, resolve_engine
from elt.src.processing.registry import get_transformation, register_transformation
from elt.src.processing.spark_executor import execute_spark_step
from elt.src.spark.io import map_write_strategy


def test_config_defaults_to_python_and_accepts_spark_options():
    assert resolve_engine({}) == "python"
    config = parse_processing_config(
        '{"engine":"spark","transform":"municipios_silver",'
        '"spark":{"partition_by":["uf"],"count_records":true}}'
    )
    assert config["engine"] == "spark"
    assert config["transform"] == "municipios_silver"
    assert config["spark"] == {"partition_by": ["uf"], "count_records": True}


@pytest.mark.parametrize("value", ["{", "[]", 3])
def test_config_rejects_malformed_or_non_object_values(value):
    with pytest.raises((TypeError, ValueError)):
        parse_processing_config(value)


@pytest.mark.parametrize("engine", ["pyspark", "Python", 1, None])
def test_engine_rejects_invalid_values(engine):
    with pytest.raises(ValueError, match="engine"):
        resolve_engine({"engine": engine})


def test_config_rejects_invalid_spark_values():
    with pytest.raises(ValueError, match="partition_by"):
        parse_processing_config({"spark": {"partition_by": "uf"}})
    with pytest.raises(ValueError, match="count_records"):
        parse_processing_config({"spark": {"count_records": 1}})


def test_registry_decorator_lookup_duplicate_and_missing():
    name = "test_spark_core_transform"

    @register_transformation(name)
    def transform(value):
        return value

    assert get_transformation(name) is transform
    with pytest.raises(ValueError, match="already registered"):
        register_transformation(name)(lambda value: value)
    with pytest.raises(KeyError, match="Unknown transformation"):
        get_transformation("definitely_missing_transform")


@pytest.mark.parametrize(
    ("strategy", "mode"),
    [("truncate", "overwrite"), ("replace", "overwrite"), ("append", "append"), ("fail", "errorifexists")],
)
def test_write_strategy_mapping(strategy, mode):
    assert map_write_strategy(strategy) == mode


def test_write_strategy_rejects_unknown_values():
    with pytest.raises(ValueError, match="Unsupported"):
        map_write_strategy("merge")


def test_executor_rejects_missing_transform_before_starting_spark():
    row = {
        "layer": "silver",
        "table_destiny": "municipios",
        "config": {"engine": "spark"},
    }
    with pytest.raises(ValueError, match="config.transform"):
        execute_spark_step(row, {}, {})


def test_spark_source_has_no_dynamic_execution_or_import():
    root = pathlib.Path(__file__).parents[1] / "src"
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in (root / "processing", root / "spark")
        for path in folder.glob("*.py")
    )
    forbidden = ("ev" + "al(", "ex" + "ec(", "import" + "lib", "__im" + "port__")
    assert not any(token in sources for token in forbidden)
