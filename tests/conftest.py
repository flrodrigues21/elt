"""pytest conftest — make the local checkout importable as 'elt'.

Also installs an autouse fixture that blocks any real DNS resolution or TCP
connection so every test is fully isolated from the network.
"""
import importlib
import pathlib
import sys
from unittest.mock import patch

import pytest

_project_root = pathlib.Path(__file__).resolve().parent.parent

# Ensure the parent of project root is on sys.path
parent = str(_project_root.parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

_dir_name = _project_root.name
if _dir_name != "elt" and "elt" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "elt",
        _project_root / "__init__.py",
        submodule_search_locations=[str(_project_root)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["elt"] = mod
    spec.loader.exec_module(mod)


# ---------------------------------------------------------------------------
# Autouse fixture: block ALL real DNS and network access
# ---------------------------------------------------------------------------

def _fail_getaddrinfo(*args, **kwargs):
    raise AssertionError(
        "UNMOCKED socket.getaddrinfo call — test is not isolated. "
        "Mock socket.getaddrinfo or resolve_and_check_host in your test."
    )


def _fail_create_connection(*args, **kwargs):
    raise AssertionError(
        "UNMOCKED socket.create_connection call — test is not isolated."
    )


@pytest.fixture(autouse=True)
def _block_real_network():
    """Prevent any real DNS resolution or TCP connection during tests."""
    with (
        patch("socket.getaddrinfo", side_effect=_fail_getaddrinfo),
        patch("socket.create_connection", side_effect=_fail_create_connection),
    ):
        yield
