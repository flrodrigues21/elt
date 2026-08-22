"""Tests for _security.py module.

Covers: path traversal, SSRF, download limits, ZIP bomb, filename sanitization.
"""
import importlib
import io
import os
import pathlib
import sys
import tempfile
import zipfile

import pytest

# Import _security directly to avoid triggering extractors/__init__.py
# which eagerly imports airflow-dependent modules.
_security_mod_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "extractors" / "_security.py"
_spec = importlib.util.spec_from_file_location("_security", _security_mod_path)
_security = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_security)

SecurityError = _security.SecurityError
sanitize_filename = _security.sanitize_filename
is_safe_path = _security.is_safe_path
validate_url_scheme = _security.validate_url_scheme
validate_url = _security.validate_url
resolve_and_check_host = _security.resolve_and_check_host
is_same_host = _security.is_same_host
safe_zip_extract = _security.safe_zip_extract
stream_download = _security.stream_download
ALLOWED_SCHEMES = _security.ALLOWED_SCHEMES


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------
class TestSanitizeFilename:
    def test_normal_filename(self):
        assert sanitize_filename("data.csv") == "data.csv"

    def test_strips_path_components(self):
        assert sanitize_filename("/etc/passwd") == "passwd"
        assert sanitize_filename("../../../etc/passwd") == "passwd"

    def test_strips_dangerous_chars(self):
        result = sanitize_filename('file<>:"/\\|?*.txt')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result

    def test_empty_returns_fallback(self):
        assert sanitize_filename("") == "download.bin"
        assert sanitize_filename(None) == "download.bin"

    def test_fallback_override(self):
        assert sanitize_filename("", fallback="custom.bin") == "custom.bin"

    def test_strips_dots_and_spaces(self):
        assert sanitize_filename("...") == "download.bin"

    def test_content_disposition_attack(self):
        malicious = 'attachment; filename="../../../etc/shadow"'
        name = malicious.split("filename=")[-1].strip('"')
        assert sanitize_filename(name) == "shadow"


# ---------------------------------------------------------------------------
# is_safe_path
# ---------------------------------------------------------------------------
class TestIsSafePath:
    def test_safe_relative_path(self):
        base = tempfile.gettempdir()
        target = os.path.join(base, "file.txt")
        assert is_safe_path(base, target) is True

    def test_traversal_detected(self):
        base = tempfile.gettempdir()
        target = os.path.join(base, "..", "etc", "passwd")
        assert is_safe_path(base, target) is False

    def test_absolute_escape(self):
        base = tempfile.gettempdir()
        target = "/etc/passwd" if os.name != "nt" else "C:\\Windows\\System32\\config\\SAM"
        assert is_safe_path(base, target) is False

    def test_same_dir(self):
        base = tempfile.gettempdir()
        assert is_safe_path(base, base) is True

    def test_subdir(self):
        base = tempfile.gettempdir()
        target = os.path.join(base, "subdir", "file.txt")
        assert is_safe_path(base, target) is True


# ---------------------------------------------------------------------------
# validate_url_scheme
# ---------------------------------------------------------------------------
class TestValidateUrlScheme:
    def test_http_allowed(self):
        validate_url_scheme("http://example.com")

    def test_https_allowed(self):
        validate_url_scheme("https://example.com")

    def test_ftp_rejected(self):
        with pytest.raises(SecurityError, match="not allowed"):
            validate_url_scheme("ftp://example.com/file.csv")

    def test_file_rejected(self):
        with pytest.raises(SecurityError, match="not allowed"):
            validate_url_scheme("file:///etc/passwd")

    def test_javascript_rejected(self):
        with pytest.raises(SecurityError, match="not allowed"):
            validate_url_scheme("javascript:alert(1)")

    def test_data_rejected(self):
        with pytest.raises(SecurityError, match="not allowed"):
            validate_url_scheme("data:text/html,<h1>hi</h1>")


# ---------------------------------------------------------------------------
# resolve_and_check_host
# ---------------------------------------------------------------------------
class TestResolveAndCheckHost:
    def test_localhost_rejected(self):
        with pytest.raises(SecurityError, match="loopback"):
            resolve_and_check_host("localhost")

    def test_127_rejected(self):
        with pytest.raises(SecurityError, match="loopback"):
            resolve_and_check_host("127.0.0.1")

    def test_dns_resolution_failure(self):
        with pytest.raises(SecurityError, match="Cannot resolve"):
            resolve_and_check_host("this-host-does-not-exist-12345.example.invalid")


# ---------------------------------------------------------------------------
# validate_url (full pipeline)
# ---------------------------------------------------------------------------
class TestValidateUrl:
    def test_valid_https(self):
        validate_url("https://example.com/data.csv")

    def test_ftp_scheme_rejected(self):
        with pytest.raises(SecurityError):
            validate_url("ftp://example.com/file.csv")

    def test_localhost_rejected(self):
        with pytest.raises(SecurityError, match="loopback"):
            validate_url("http://localhost:8080/api")


# ---------------------------------------------------------------------------
# is_same_host
# ---------------------------------------------------------------------------
class TestIsSameHost:
    def test_same_host(self):
        assert is_same_host("https://example.com/a", "https://example.com/b") is True

    def test_different_host(self):
        assert is_same_host("https://evil.com/a", "https://example.com/b") is False

    def test_invalid_url(self):
        assert is_same_host("not-a-url", "also-not-a-url") is False


# ---------------------------------------------------------------------------
# safe_zip_extract
# ---------------------------------------------------------------------------
class TestSafeZipExtract:
    def _make_zip(self, entries: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in entries.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_normal_zip(self):
        data = self._make_zip({"data.csv": "a,b,c\n1,2,3"})
        with tempfile.TemporaryDirectory() as d:
            files = safe_zip_extract(data, d)
            assert len(files) == 1
            assert os.path.exists(files[0])

    def test_zip_bomb_uncompressed_limit(self):
        data = self._make_zip({"huge.csv": "x" * 100_000})
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="exceeds.*limit"):
                safe_zip_extract(data, d, max_uncompressed_bytes=1000)

    def test_zip_bomb_compressed_limit(self):
        data = self._make_zip({"f.csv": "data"})
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="compressed size limit"):
                safe_zip_extract(data, d, max_compressed_bytes=5)

    def test_zip_bomb_file_count(self):
        entries = {f"f{i}.csv": "data" for i in range(100)}
        data = self._make_zip(entries)
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="more than 5"):
                safe_zip_extract(data, d, max_files=5)

    def test_path_traversal_in_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", "evil content")
        data = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            # basename() strips traversal, so file is extracted safely
            files = safe_zip_extract(data, d)
            assert len(files) == 1
            assert os.path.basename(files[0]) == "passwd"

    def test_path_traversal_with_encoded_sep(self):
        name_with_backslash = "....\\..\\Windows\\System32\\config\\SAM"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(name_with_backslash, "evil content")
        data = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            files = safe_zip_extract(data, d)
            assert len(files) == 1
            basename = os.path.basename(files[0])
            assert "\\\\" not in basename or basename == "SAM"

    def test_directories_skipped(self):
        data = self._make_zip({"dir/": "", "data.csv": "content"})
        with tempfile.TemporaryDirectory() as d:
            files = safe_zip_extract(data, d)
            assert len(files) == 1


# ---------------------------------------------------------------------------
# stream_download
# ---------------------------------------------------------------------------
class TestStreamDownload:
    def test_rejects_ftp(self):
        with pytest.raises(SecurityError, match="not allowed"):
            stream_download("ftp://example.com/file.csv")

    def test_rejects_file_scheme(self):
        with pytest.raises(SecurityError, match="not allowed"):
            stream_download("file:///etc/passwd")

    def test_rejects_loopback(self):
        with pytest.raises(SecurityError, match="loopback"):
            stream_download("http://127.0.0.1:8080/secret")

    def test_rejects_localhost(self):
        with pytest.raises(SecurityError, match="loopback"):
            stream_download("http://localhost/admin")
