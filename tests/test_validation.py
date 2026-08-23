"""Tests for SQL identifier validation (validation.py)."""
import importlib
import pathlib

import pytest

# Import validation directly to avoid triggering package __init__ chains.
_validation_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "utils" / "validation.py"
_spec = importlib.util.spec_from_file_location("validation", _validation_path)
_validation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validation)

validate_identifier = _validation.validate_identifier
validate_strategy = _validation.validate_strategy
sanitize_url = _validation.sanitize_url


class TestValidateIdentifier:
    def test_valid_simple(self):
        assert validate_identifier("my_table") == "my_table"

    def test_valid_with_underscore(self):
        assert validate_identifier("_private") == "_private"
        assert validate_identifier("table_name_123") == "table_name_123"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_identifier("")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_identifier("my table")

    def test_rejects_starts_with_digit(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_identifier("1table")

    def test_rejects_injection_with_semicolon(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_identifier("users; DROP TABLE--")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_identifier("table-name")
        with pytest.raises(ValueError, match="Invalid"):
            validate_identifier("table.name")

    def test_custom_label(self):
        with pytest.raises(ValueError, match="schema_source"):
            validate_identifier("bad;name", "schema_source")


class TestValidateStrategy:
    def test_valid_strategies(self):
        assert validate_strategy("append") == "append"
        assert validate_strategy("REPLACE") == "replace"
        assert validate_strategy("  truncate  ") == "truncate"
        assert validate_strategy("fail") == "fail"

    def test_rejects_invalid(self):
        with pytest.raises(ValueError, match="Invalid strategy"):
            validate_strategy("upsert")

    def test_case_insensitive(self):
        assert validate_strategy("APPEND") == "append"


class TestSanitizeUrl:
    def test_masks_password(self):
        result = sanitize_url("postgresql://user:secret123@host:5432/db")
        assert "secret123" not in result
        assert "***" in result

    def test_masks_complex_password(self):
        result = sanitize_url("postgresql://user:p@ss!w0rd@host:5432/db")
        assert "p@ss!w0rd" not in result
        assert "***" in result

    def test_empty_string(self):
        assert sanitize_url("") == ""

    def test_no_credentials(self):
        url = "https://example.com/api"
        assert sanitize_url(url) == url
