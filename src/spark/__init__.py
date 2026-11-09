"""Lazy-loading Spark support for ELT processing."""

from .io import map_write_strategy
from .session import get_spark_session

__all__ = ["get_spark_session", "map_write_strategy"]
