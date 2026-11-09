"""Explicit allow-list of transformations available to processing steps."""

import re
from collections.abc import Callable
from typing import Any


_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TRANSFORMATIONS: dict[str, Callable[..., Any]] = {}


def register_transformation(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a callable under a stable, configuration-safe name."""
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"Invalid transformation name: {name!r}")

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        if not callable(function):
            raise TypeError("A registered transformation must be callable")
        if name in _TRANSFORMATIONS:
            raise ValueError(f"Transformation already registered: {name}")
        _TRANSFORMATIONS[name] = function
        return function

    return decorator


def get_transformation(name: str) -> Callable[..., Any]:
    """Look up a registered transformation, rejecting unknown names."""
    if not isinstance(name, str) or not name:
        raise ValueError("A non-empty transformation name is required")
    try:
        return _TRANSFORMATIONS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown transformation: {name}") from exc


transformation = register_transformation
get = get_transformation
