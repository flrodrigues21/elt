"""pytest conftest — make the local checkout importable as 'elt'."""
import importlib
import pathlib
import sys

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
