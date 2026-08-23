"""Shared security utilities for ELT extractors.

Provides path traversal protection, SSRF mitigation with internal host
allowlisting, manual redirect following, file-based streaming downloads,
and safe ZIP extraction.

**Residual risk – DNS rebinding / TOCTOU:**
``validate_url`` resolves and checks the target IP immediately before each
call, but ``requests`` (via urllib3) performs its own DNS resolution when
opening the TCP connection.  Between validation and connection a DNS rebinding
attack could theoretically redirect the request to a different (blocked) IP.
This is an inherent limitation of using a high-level HTTP library that manages
its own connection pool.  For environments that require absolute assurance
against DNS rebinding, use one or more of:

* **Egress firewall / proxy:** restrict outbound connections to an allowlist
  of IPs or CIDRs.
* **DNS sinkhole / split-horizon DNS:** resolve internal-only names via a
  controlled resolver.
* **Domain allowlist at the proxy level:** the proxy validates the destination
  before forwarding.
"""
from __future__ import annotations

import io
import ipaddress
import logging
import os
import re
import socket
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Sequence
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------
DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MB
DEFAULT_MAX_ZIP_BYTES = 200 * 1024 * 1024  # 200 MB compressed
DEFAULT_MAX_UNCOMPRESSED_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB decompressed
DEFAULT_MAX_FILES = 200
DEFAULT_STREAM_CHUNK = 256 * 1024  # 256 KB
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_REDIRECTS = 5

# ---------------------------------------------------------------------------
# Internal host / CIDR allowlist
# Configurable via env vars at startup or via configure_allowed_internals().
# ---------------------------------------------------------------------------
_ALLOWED_INTERNAL_HOSTS: set[str] = set()
_ALLOWED_INTERNAL_CIDRS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []

_LOCK = threading.Lock()


def configure_allowed_internals(
    *,
    hosts: Sequence[str] | None = None,
    cidrs: Sequence[str] | None = None,
) -> None:
    """Configure hosts and/or CIDRs that are permitted internal targets.

    Thread-safe.  When a URL target resolves to one of these, it bypasses
    the private/metadata block.
    """
    global _ALLOWED_INTERNAL_HOSTS, _ALLOWED_INTERNAL_CIDRS
    with _LOCK:
        _ALLOWED_INTERNAL_HOSTS = set(h.lower() for h in (hosts or []))
        _ALLOWED_INTERNAL_CIDRS = [
            ipaddress.ip_network(c, strict=False) for c in (cidrs or [])
        ]


def _load_allowlist_from_env() -> None:
    """Load allowlist from ELT_ALLOWED_INTERNAL_HOSTS / ELT_ALLOWED_INTERNAL_CIDRS.

    Called once at module load.  Comma-separated values.
    """
    hosts_str = os.environ.get("ELT_ALLOWED_INTERNAL_HOSTS", "")
    cidrs_str = os.environ.get("ELT_ALLOWED_INTERNAL_CIDRS", "")
    hosts = [h.strip() for h in hosts_str.split(",") if h.strip()]
    cidrs = [c.strip() for c in cidrs_str.split(",") if c.strip()]
    if hosts or cidrs:
        configure_allowed_internals(hosts=hosts, cidrs=cidrs)
        logger.info(
            "Security allowlist loaded from env: %d host(s), %d CIDR(s)",
            len(_ALLOWED_INTERNAL_HOSTS),
            len(_ALLOWED_INTERNAL_CIDRS),
        )


class SecurityError(Exception):
    """Raised when a security check fails."""


# ---------------------------------------------------------------------------
# Filename / path helpers
# ---------------------------------------------------------------------------

def sanitize_filename(name: str, fallback: str = "download.bin") -> str:
    """Strip directory components and dangerous characters from a filename."""
    if not name:
        return fallback
    name = os.path.basename(name.strip())
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or fallback


def is_safe_path(base_dir: str, target: str) -> bool:
    """Return True if *target* resolves inside *base_dir*."""
    try:
        base = Path(base_dir).resolve(strict=False)
        target_resolved = Path(target).resolve(strict=False)
        return (
            str(target_resolved).startswith(str(base) + os.sep)
            or target_resolved == base
        )
    except (OSError, ValueError):
        return False


def unique_temp_path(suffix: str = ".tmp", prefix: str = "elt_") -> str:
    """Return a unique temporary file path that does not yet exist."""
    tmp_dir = tempfile.gettempdir()
    name = f"{prefix}{uuid.uuid4().hex}{suffix}"
    return os.path.join(tmp_dir, name)


# ---------------------------------------------------------------------------
# URL / SSRF helpers
# ---------------------------------------------------------------------------

def _ip_in_allowlisted_network(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if *ip* falls within any configured ALLOWED_INTERNAL_CIDRS."""
    with _LOCK:
        cidrs = list(_ALLOWED_INTERNAL_CIDRS)
    for net in cidrs:
        if ip in net:
            return True
    return False


def validate_url_scheme(url: str) -> None:
    """Raise SecurityError if URL scheme is not allowed."""
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SecurityError(
            f"URL scheme '{parsed.scheme}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_SCHEMES))}"
        )


def _classify_ip(addr: str, hostname: str) -> str | None:
    """Return a reason string if the IP should be blocked, else None."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return None

    if ip.is_loopback:
        return f"loopback address {addr}"
    if ip.is_link_local:
        return f"link-local address {addr}"
    if ip.is_multicast:
        return f"multicast address {addr}"
    if ip.is_unspecified:
        return f"unspecified address {addr}"
    if ip.is_reserved:
        return f"reserved address {addr}"
    if ip.is_private:
        if _ip_in_allowlisted_network(ip):
            return None  # explicitly allowed
        return f"private address {addr} (not in internal allowlist)"
    return None


def resolve_and_check_host(hostname: str) -> list[str]:
    """Resolve hostname and reject disallowed IPs.

    Returns the list of resolved IP strings.
    """
    with _LOCK:
        hosts_copy = set(_ALLOWED_INTERNAL_HOSTS)

    hostname_lower = hostname.lower()
    if hostname_lower in hosts_copy:
        try:
            infos = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
            return [sockaddr[0] for _, _, _, _, sockaddr in infos]
        except socket.gaierror as exc:
            raise SecurityError(
                f"Cannot resolve allowlisted host '{hostname}': {exc}"
            ) from exc

    try:
        infos = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise SecurityError(f"Cannot resolve host '{hostname}': {exc}") from exc

    resolved_ips: list[str] = []
    for _family, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        resolved_ips.append(ip_str)
        reason = _classify_ip(ip_str, hostname)
        if reason:
            raise SecurityError(
                f"Host '{hostname}' resolves to blocked address: {reason}"
            )
    return resolved_ips


def validate_url(url: str) -> str:
    """Validate URL scheme and host.  Returns the URL if valid."""
    validate_url_scheme(url)
    parsed = urlparse(url)
    if parsed.hostname:
        resolve_and_check_host(parsed.hostname)
    return url


def is_same_host(url: str, base_url: str) -> bool:
    """Check if *url* targets the same host as *base_url*."""
    try:
        a = urlparse(url)
        b = urlparse(base_url)
        if not a.hostname or not b.hostname:
            return False
        return a.hostname.lower() == b.hostname.lower()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Manual redirect following with SSRF checks
# ---------------------------------------------------------------------------

def safe_request(
    method: str,
    url: str,
    *,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: int = DEFAULT_TIMEOUT,
    **kwargs,
) -> requests.Response:
    """Issue an HTTP request with disabled automatic redirects.

    Each ``30x`` response is followed manually up to *max_redirects* hops.
    Every ``Location`` URL is fully validated (scheme + DNS) before following.
    Relative redirects are resolved with ``urljoin`` against the current URL.

    The previous response is closed in all code paths (including errors).

    .. note::

       There is an inherent TOCTOU window between DNS validation and the
       actual TCP connection made by ``requests``.  See module docstring
       for mitigations against DNS rebinding in high-security environments.
    """
    current_url = url
    resp = None

    try:
        resp = requests.request(
            method, current_url, allow_redirects=False, timeout=timeout, **kwargs
        )

        hops = 0
        while resp.is_redirect and hops < max_redirects:
            location = resp.headers.get("Location", "")
            if not location:
                break

            next_url = urljoin(current_url, location)
            validate_url(next_url)

            resp.close()
            current_url = next_url
            resp = requests.request(
                method, current_url, allow_redirects=False, timeout=timeout, **kwargs
            )
            hops += 1

        if hops >= max_redirects and resp.is_redirect:
            raise SecurityError(
                f"Too many redirects (>{max_redirects}) from {url}"
            )

        return resp

    except BaseException:
        if resp is not None:
            resp.close()
        raise


# ---------------------------------------------------------------------------
# File-based streaming download
# ---------------------------------------------------------------------------

def stream_download_to_file(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    dest_path: str | None = None,
) -> str:
    """Download *url* by streaming directly to a temporary file.

    Returns the path to the downloaded file.  The caller is responsible for
    deleting the file when done (use a try/finally block).

    Raises SecurityError on scheme/host/size violations.
    """
    validate_url(url)

    resp = safe_request(
        "GET",
        url,
        max_redirects=max_redirects,
        timeout=timeout,
        stream=True,
    )
    resp.raise_for_status()

    content_length = resp.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                resp.close()
                raise SecurityError(
                    f"Content-Length ({content_length}) exceeds limit ({max_bytes})"
                )
        except (ValueError, TypeError):
            pass

    if dest_path is None:
        ext = _guess_ext(resp)
        dest_path = unique_temp_path(suffix=ext)

    total = 0
    try:
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=DEFAULT_STREAM_CHUNK):
                total += len(chunk)
                if total > max_bytes:
                    raise SecurityError(
                        f"Download exceeded size limit ({max_bytes} bytes)"
                    )
                f.write(chunk)
    except BaseException:
        _safe_remove(dest_path)
        raise
    finally:
        resp.close()

    return dest_path


def _guess_ext(resp: requests.Response) -> str:
    """Heuristic file extension from response headers."""
    ct = resp.headers.get("Content-Type", "")
    cd = resp.headers.get("Content-Disposition", "")
    if ".zip" in cd or "zip" in ct:
        return ".zip"
    if ".parquet" in cd or "parquet" in ct:
        return ".parquet"
    if ".csv" in cd or "csv" in ct:
        return ".csv"
    return ".bin"


def _safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Safe ZIP extraction (collision-proof, byte-tracked, cleanup-aware)
# ---------------------------------------------------------------------------

def safe_zip_extract(
    data: bytes | str,
    dest_dir: str,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_compressed_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> list[str]:
    """Extract a ZIP archive safely.

    *data* can be ``bytes`` (in-memory) or a ``str`` file path.  When a file
    path is given the ZIP is read lazily via ``ZipFile(path)`` without loading
    the entire archive into memory.

    * Prevents path traversal via ``basename()`` + ``is_safe_path()``.
    * Detects ZIP bombs via compressed-size, uncompressed-size, and file-count limits.
    * Prevents name collisions when multiple entries flatten to the same basename
      by appending ``_1``, ``_2``, etc.
    * Tracks total bytes actually written.
    * Cleans up extracted files on any error.

    Returns list of extracted file paths.
    """
    extracted: list[str] = []
    used_names: dict[str, int] = {}

    try:
        if isinstance(data, str):
            file_size = os.path.getsize(data)
            if file_size > max_compressed_bytes:
                raise SecurityError(
                    f"ZIP file ({file_size} bytes) exceeds compressed size limit "
                    f"({max_compressed_bytes})"
                )
            _extract_from_file(data, dest_dir, extracted, used_names,
                               max_files, max_uncompressed_bytes)
        else:
            if len(data) > max_compressed_bytes:
                raise SecurityError(
                    f"ZIP data ({len(data)} bytes) exceeds compressed size limit "
                    f"({max_compressed_bytes})"
                )
            _extract_from_bytes(data, dest_dir, extracted, used_names,
                                max_files, max_uncompressed_bytes)

    except BaseException:
        for p in extracted:
            _safe_remove(p)
        raise

    return extracted


def _pre_scan_zip(zf: zipfile.ZipFile, max_files: int, max_uncompressed_bytes: int) -> None:
    """Pre-scan ZIP entries to detect bombs before writing anything."""
    total_uncompressed = 0
    file_count = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        file_count += 1
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed_bytes:
            raise SecurityError(
                f"ZIP uncompressed content exceeds limit "
                f"({max_uncompressed_bytes} bytes)"
            )
    if file_count > max_files:
        raise SecurityError(
            f"ZIP contains {file_count} files, limit is {max_files}"
        )


def _extract_entries(
    zf: zipfile.ZipFile,
    dest_dir: str,
    extracted: list[str],
    used_names: dict[str, int],
    max_uncompressed_bytes: int,
) -> None:
    """Extract entries from an open ZipFile with collision-safe naming."""
    total_written = 0
    for info in zf.infolist():
        if info.is_dir():
            continue

        base = sanitize_filename(os.path.basename(info.filename))
        if base in used_names:
            used_names[base] += 1
            stem, ext = os.path.splitext(base)
            base = f"{stem}_{used_names[base]}{ext}"
        else:
            used_names[base] = 0

        target = os.path.join(dest_dir, base)
        if not is_safe_path(dest_dir, target):
            raise SecurityError(
                f"ZIP entry '{info.filename}' escapes extraction directory"
            )

        with zf.open(info) as src, open(target, "wb") as dst:
            while True:
                buf = src.read(DEFAULT_STREAM_CHUNK)
                if not buf:
                    break
                total_written += len(buf)
                if total_written > max_uncompressed_bytes:
                    raise SecurityError(
                        f"ZIP written bytes ({total_written}) exceeds "
                        f"limit ({max_uncompressed_bytes})"
                    )
                dst.write(buf)
        extracted.append(target)


def _extract_from_bytes(
    data: bytes,
    dest_dir: str,
    extracted: list[str],
    used_names: dict[str, int],
    max_files: int,
    max_uncompressed_bytes: int,
) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        _pre_scan_zip(zf, max_files, max_uncompressed_bytes)
        _extract_entries(zf, dest_dir, extracted, used_names, max_uncompressed_bytes)


def _extract_from_file(
    path: str,
    dest_dir: str,
    extracted: list[str],
    used_names: dict[str, int],
    max_files: int,
    max_uncompressed_bytes: int,
) -> None:
    """Open ZIP from file path without loading entire content into memory."""
    with zipfile.ZipFile(path) as zf:
        _pre_scan_zip(zf, max_files, max_uncompressed_bytes)
        _extract_entries(zf, dest_dir, extracted, used_names, max_uncompressed_bytes)
