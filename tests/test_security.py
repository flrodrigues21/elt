"""Tests for _security.py module.

All network, DNS, and HTTP calls are fully mocked – no real connections.
"""
import importlib
import io
import os
import pathlib
import socket
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

_security_mod_path = (
    pathlib.Path(__file__).resolve().parent.parent / "src" / "extractors" / "_security.py"
)
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
stream_download_to_file = _security.stream_download_to_file
safe_request = _security.safe_request
unique_temp_path = _security.unique_temp_path
_configure = _security.configure_allowed_internals
_classify_ip = _security._classify_ip
_safe_remove = _security._safe_remove
ALLOWED_SCHEMES = _security.ALLOWED_SCHEMES
IPBoundHTTPSAdapter = _security.IPBoundHTTPSAdapter

PUBLIC_IP = "93.184.216.34"


def _mock_getaddrinfo(ip: str = PUBLIC_IP):
    """Return a socket.getaddrinfo mock returning a single IPv4 result."""
    return patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))],
    )


def _mock_do_request(resp=None, side_effect=None):
    """Patch _do_request to return *resp* without any network calls."""
    kwargs: dict = {}
    if resp is not None:
        kwargs["return_value"] = resp
    if side_effect is not None:
        kwargs["side_effect"] = side_effect
    return patch.object(_security, "_do_request", **kwargs)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------
class TestSanitizeFilename:
    def test_normal(self):
        assert sanitize_filename("data.csv") == "data.csv"

    def test_strips_path(self):
        assert sanitize_filename("/etc/passwd") == "passwd"
        assert sanitize_filename("../../../etc/passwd") == "passwd"

    def test_dangerous_chars(self):
        result = sanitize_filename('file<>:"/\\|?*.txt')
        for ch in '<>:"/\\|?*':
            assert ch not in result

    def test_empty_returns_fallback(self):
        assert sanitize_filename("") == "download.bin"
        assert sanitize_filename(None) == "download.bin"

    def test_custom_fallback(self):
        assert sanitize_filename("", fallback="x.bin") == "x.bin"

    def test_dots_only(self):
        assert sanitize_filename("...") == "download.bin"

    def test_content_disposition_attack(self):
        name = 'attachment; filename="../../../etc/shadow"'
        raw = name.split("filename=")[-1].strip('"')
        assert sanitize_filename(raw) == "shadow"


# ---------------------------------------------------------------------------
# is_safe_path
# ---------------------------------------------------------------------------
class TestIsSafePath:
    def test_safe(self):
        base = tempfile.gettempdir()
        assert is_safe_path(base, os.path.join(base, "f.txt")) is True

    def test_traversal(self):
        base = tempfile.gettempdir()
        assert is_safe_path(base, os.path.join(base, "..", "etc", "passwd")) is False

    def test_absolute(self):
        base = tempfile.gettempdir()
        target = "/etc/passwd" if os.name != "nt" else "C:\\Windows\\System32\\config\\SAM"
        assert is_safe_path(base, target) is False

    def test_same_dir(self):
        base = tempfile.gettempdir()
        assert is_safe_path(base, base) is True


# ---------------------------------------------------------------------------
# validate_url_scheme
# ---------------------------------------------------------------------------
class TestValidateUrlScheme:
    def test_http_ok(self):
        validate_url_scheme("http://example.com")

    def test_https_ok(self):
        validate_url_scheme("https://example.com")

    @pytest.mark.parametrize("url", [
        "ftp://x.com/f", "file:///etc/passwd",
        "javascript:alert(1)", "data:text/html,x",
    ])
    def test_rejected(self, url):
        with pytest.raises(SecurityError, match="not allowed"):
            validate_url_scheme(url)


# ---------------------------------------------------------------------------
# _classify_ip
# ---------------------------------------------------------------------------
class TestClassifyIP:
    def test_loopback(self):
        assert _classify_ip("127.0.0.1", "h") is not None

    def test_link_local(self):
        assert _classify_ip("169.254.1.1", "h") is not None

    def test_multicast(self):
        assert _classify_ip("224.0.0.1", "h") is not None

    def test_unspecified(self):
        assert _classify_ip("0.0.0.0", "h") is not None

    def test_reserved(self):
        assert _classify_ip("240.0.0.1", "h") is not None

    def test_private_blocked_by_default(self):
        assert _classify_ip("10.0.0.1", "h") is not None
        assert _classify_ip("192.168.1.1", "h") is not None
        assert _classify_ip("172.16.0.1", "h") is not None

    def test_private_allowed_when_in_cidr(self):
        _configure(cidrs=["10.0.0.0/8"])
        try:
            assert _classify_ip("10.0.0.1", "h") is None
        finally:
            _configure(cidrs=[])

    def test_public_ok(self):
        assert _classify_ip("8.8.8.8", "h") is None


# ---------------------------------------------------------------------------
# resolve_and_check_host
# ---------------------------------------------------------------------------
class TestResolveAndCheckHost:
    def test_localhost_blocked(self):
        with _mock_getaddrinfo("127.0.0.1"):
            with pytest.raises(SecurityError, match="loopback"):
                resolve_and_check_host("localhost")

    def test_private_blocked(self):
        with _mock_getaddrinfo("10.0.0.1"):
            with pytest.raises(SecurityError, match="private"):
                resolve_and_check_host("internal.corp")

    def test_private_allowed_via_allowlist_cidr(self):
        _configure(cidrs=["10.0.0.0/8"])
        try:
            with _mock_getaddrinfo("10.0.0.1"):
                result = resolve_and_check_host("internal.corp")
                assert "10.0.0.1" in result
        finally:
            _configure(cidrs=[])

    def test_host_allowed_via_allowlist(self):
        _configure(hosts=["myserver.local"])
        try:
            with _mock_getaddrinfo("10.0.0.5"):
                result = resolve_and_check_host("myserver.local")
                assert "10.0.0.5" in result
        finally:
            _configure(hosts=[])

    def test_dns_failure(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("no such host")):
            with pytest.raises(SecurityError, match="Cannot resolve"):
                resolve_and_check_host("no-such-host.invalid")

    def test_public_ok(self):
        with _mock_getaddrinfo(PUBLIC_IP):
            result = resolve_and_check_host("example.com")
            assert PUBLIC_IP in result


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------
class TestValidateUrl:
    def test_ftp_rejected(self):
        with pytest.raises(SecurityError):
            validate_url("ftp://example.com/f.csv")

    def test_localhost_rejected(self):
        with _mock_getaddrinfo("127.0.0.1"):
            with pytest.raises(SecurityError, match="loopback"):
                validate_url("http://localhost/api")

    def test_public_ok(self):
        with _mock_getaddrinfo(PUBLIC_IP):
            validate_url("https://example.com/data.csv")


# ---------------------------------------------------------------------------
# is_same_host
# ---------------------------------------------------------------------------
class TestIsSameHost:
    def test_same(self):
        assert is_same_host("https://a.com/x", "https://a.com/y") is True

    def test_different(self):
        assert is_same_host("https://evil.com/x", "https://a.com/y") is False

    def test_no_hostname(self):
        assert is_same_host("not-a-url", "also-not") is False


# ---------------------------------------------------------------------------
# unique_temp_path
# ---------------------------------------------------------------------------
class TestUniqueTempPath:
    def test_unique(self):
        a = unique_temp_path()
        b = unique_temp_path()
        assert a != b
        assert not os.path.exists(a)
        assert not os.path.exists(b)


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

    def test_normal(self):
        data = self._make_zip({"data.csv": "a,b,c\n1,2,3"})
        with tempfile.TemporaryDirectory() as d:
            files = safe_zip_extract(data, d)
            assert len(files) == 1
            assert os.path.exists(files[0])

    def test_normal_from_file_path(self):
        data = self._make_zip({"data.csv": "a,b,c\n1,2,3"})
        with tempfile.TemporaryDirectory() as d:
            zip_path = os.path.join(d, "test.zip")
            with open(zip_path, "wb") as f:
                f.write(data)
            files = safe_zip_extract(zip_path, d)
            assert len(files) == 1

    def test_bomb_uncompressed(self):
        data = self._make_zip({"huge.csv": "x" * 100_000})
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="exceeds.*limit"):
                safe_zip_extract(data, d, max_uncompressed_bytes=1000)

    def test_bomb_compressed(self):
        data = self._make_zip({"f.csv": "data"})
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="compressed size limit"):
                safe_zip_extract(data, d, max_compressed_bytes=5)

    def test_bomb_file_count(self):
        data = self._make_zip({f"f{i}.csv": "d" for i in range(100)})
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="100 files"):
                safe_zip_extract(data, d, max_files=5)

    def test_collision_naming(self):
        data = self._make_zip({"a/data.csv": "1", "b/data.csv": "2"})
        with tempfile.TemporaryDirectory() as d:
            files = safe_zip_extract(data, d)
            assert len(files) == 2
            basenames = [os.path.basename(f) for f in files]
            assert basenames[0] == "data.csv"
            assert "data_1.csv" in basenames

    def test_cleanup_on_error(self):
        bad_zip = b"not a zip at all"
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(Exception):
                safe_zip_extract(bad_zip, d)
            assert os.listdir(d) == []

    def test_traversal_via_basename(self):
        data = self._make_zip({"../../etc/passwd": "evil"})
        with tempfile.TemporaryDirectory() as d:
            files = safe_zip_extract(data, d)
            assert os.path.basename(files[0]) == "passwd"

    def test_security_error_preserved_on_bomb(self):
        data = self._make_zip({f"f{i}.csv": "d" for i in range(10)})
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(SecurityError, match="10 files"):
                safe_zip_extract(data, d, max_files=5)
            assert os.listdir(d) == []


# ---------------------------------------------------------------------------
# safe_request (manual redirects) — all mocked, zero network access
# ---------------------------------------------------------------------------
class TestSafeRequest:
    def test_simple_get(self):
        mock_resp = MagicMock()
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        with _mock_do_request(mock_resp) as m:
            resp = safe_request("GET", "https://example.com")
            m.assert_called_once()
            assert resp is mock_resp

    def test_redirect_validated(self):
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "http://127.0.0.1/secret"}
        r1.close = MagicMock()

        with patch.object(_security, "validate_url", side_effect=SecurityError("blocked")):
            with _mock_do_request(r1):
                with pytest.raises(SecurityError, match="blocked"):
                    safe_request("GET", "https://example.com")

    def test_redirect_followed(self):
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "https://example.com/new"}
        r1.close = MagicMock()

        r2 = MagicMock()
        r2.is_redirect = False
        r2.status_code = 200

        with _mock_do_request(side_effect=[r1, r2]):
            resp = safe_request("GET", "https://example.com")
            assert resp is r2

    def test_relative_redirect_resolved(self):
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "/api/v2/data"}
        r1.close = MagicMock()

        r2 = MagicMock()
        r2.is_redirect = False
        r2.status_code = 200

        with _mock_do_request(side_effect=[r1, r2]) as m:
            resp = safe_request("GET", "https://example.com/api/v1/data")
            assert resp is r2
            second_call_url = m.call_args_list[1][0][1]
            assert second_call_url == "https://example.com/api/v2/data"

    def test_too_many_redirects(self):
        r = MagicMock()
        r.is_redirect = True
        r.headers = {"Location": "https://example.com/loop"}
        r.close = MagicMock()

        with _mock_do_request(r):
            with pytest.raises(SecurityError, match="Too many redirects"):
                safe_request("GET", "https://example.com", max_redirects=2)

    def test_redirect_rebinding_detected(self):
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "https://example.com/other"}
        r1.close = MagicMock()

        with _mock_do_request(r1):
            with patch.object(_security, "validate_url"):
                with patch.object(
                    _security, "resolve_and_check_host",
                    return_value=["1.2.3.4"],
                ):
                    with pytest.raises(SecurityError, match="DNS rebinding"):
                        safe_request(
                            "GET", "https://example.com",
                            resolved_ips=["5.6.7.8"],
                        )

    def test_cross_host_redirect_not_rebinding(self):
        """Redirect to a different public host is NOT rebinding."""
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "https://other.com/data"}
        r1.close = MagicMock()

        r2 = MagicMock()
        r2.is_redirect = False
        r2.status_code = 200

        with _mock_do_request(side_effect=[r1, r2]):
            resp = safe_request(
                "GET", "https://example.com",
                resolved_ips=["93.184.216.34"],
            )
            assert resp is r2

    def test_response_closed_on_validation_error(self):
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "https://evil.com/x"}
        r1.close = MagicMock()

        with _mock_do_request(r1):
            with pytest.raises(SecurityError):
                safe_request("GET", "https://example.com")
            r1.close.assert_called()

    def test_current_url_updates_each_hop(self):
        """After a redirect, the current URL used for urljoin is updated."""
        r1 = MagicMock()
        r1.is_redirect = True
        r1.headers = {"Location": "/page2"}
        r1.close = MagicMock()

        r2 = MagicMock()
        r2.is_redirect = True
        r2.headers = {"Location": "/page3"}
        r2.close = MagicMock()

        r3 = MagicMock()
        r3.is_redirect = False
        r3.status_code = 200

        with _mock_do_request(side_effect=[r1, r2, r3]) as m:
            resp = safe_request("GET", "https://example.com/page1", max_redirects=5)
            assert resp is r3
            assert m.call_args_list[1][0][1] == "https://example.com/page2"
            assert m.call_args_list[2][0][1] == "https://example.com/page3"


# ---------------------------------------------------------------------------
# IPBoundHTTPSAdapter
# ---------------------------------------------------------------------------
class TestIPBoundAdapter:
    def test_adapter_saves_ip(self):
        adapter = IPBoundHTTPSAdapter("1.2.3.4")
        assert adapter._resolved_ip == "1.2.3.4"


# ---------------------------------------------------------------------------
# stream_download_to_file — mocked, no network
# ---------------------------------------------------------------------------
class TestStreamDownloadToFile:
    def test_ftp_rejected(self):
        with pytest.raises(SecurityError, match="not allowed"):
            stream_download_to_file("ftp://example.com/f.csv")

    def test_loopback_rejected(self):
        with _mock_getaddrinfo("127.0.0.1"):
            with pytest.raises(SecurityError, match="loopback"):
                stream_download_to_file("http://localhost/secret")

    def test_writes_to_file(self):
        mock_resp = MagicMock()
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/csv", "Content-Length": "5"}
        mock_resp.iter_content.return_value = [b"hello"]
        mock_resp.close = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with _mock_do_request(mock_resp):
            path = stream_download_to_file("https://example.com/data.csv")
            try:
                assert os.path.exists(path)
                with open(path, "rb") as f:
                    assert f.read() == b"hello"
            finally:
                _safe_remove(path)

    def test_content_length_exceeded(self):
        mock_resp = MagicMock()
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Length": "999999999"}
        mock_resp.close = MagicMock()

        with _mock_do_request(mock_resp):
            with pytest.raises(SecurityError, match="Content-Length"):
                stream_download_to_file(
                    "https://example.com/big.bin", max_bytes=1000
                )

    def test_cleanup_on_error(self):
        mock_resp = MagicMock()
        mock_resp.is_redirect = False
        mock_resp.headers = {}
        mock_resp.iter_content.side_effect = IOError("network error")
        mock_resp.close = MagicMock()

        with _mock_do_request(mock_resp):
            with pytest.raises(IOError):
                stream_download_to_file("https://example.com/fail.csv")


# ---------------------------------------------------------------------------
# configure_allowed_internals / env loading
# ---------------------------------------------------------------------------
class TestAllowedInternals:
    def test_set_and_reset(self):
        _configure(hosts=["h1.corp", "h2.corp"], cidrs=["10.0.0.0/8"])
        try:
            assert "h1.corp" in _security._ALLOWED_INTERNAL_HOSTS
            assert len(_security._ALLOWED_INTERNAL_CIDRS) == 1
        finally:
            _configure(hosts=[], cidrs=[])
        assert len(_security._ALLOWED_INTERNAL_HOSTS) == 0
        assert len(_security._ALLOWED_INTERNAL_CIDRS) == 0

    def test_env_loading(self):
        with patch.dict(os.environ, {
            "ELT_ALLOWED_INTERNAL_HOSTS": "db.local,cache.local",
            "ELT_ALLOWED_INTERNAL_CIDRS": "10.0.0.0/8,172.16.0.0/12",
        }):
            _security._load_allowlist_from_env()
            try:
                assert "db.local" in _security._ALLOWED_INTERNAL_HOSTS
                assert "cache.local" in _security._ALLOWED_INTERNAL_HOSTS
                assert len(_security._ALLOWED_INTERNAL_CIDRS) == 2
            finally:
                _configure(hosts=[], cidrs=[])

    def test_env_empty(self):
        with patch.dict(os.environ, {
            "ELT_ALLOWED_INTERNAL_HOSTS": "",
            "ELT_ALLOWED_INTERNAL_CIDRS": "",
        }):
            before_hosts = set(_security._ALLOWED_INTERNAL_HOSTS)
            _security._load_allowlist_from_env()
            assert _security._ALLOWED_INTERNAL_HOSTS == before_hosts
