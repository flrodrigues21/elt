"""Shared security utilities for ELT extractors.

Provides path traversal protection, SSRF mitigation, download size limits,
and safe ZIP extraction. Used by api.py, s3.py, ftp.py, and minio.py.
"""

from __future__ import annotations

import io
import ipaddress
import logging
import os
import re
import socket
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})

DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
DEFAULT_MAX_ZIP_BYTES = 500 * 1024 * 1024  # 500 MB compressed
DEFAULT_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB decompressed
DEFAULT_MAX_FILES = 500
DEFAULT_STREAM_CHUNK = 1024 * 1024  # 1 MB
DEFAULT_TIMEOUT = 300


class SecurityError(Exception):
    """Raised when a security check fails."""


def sanitize_filename(name: str, fallback: str = "download.bin") -> str:
    """Strip directory components and dangerous characters from a filename.

    Returns *fallback* if the result is empty after sanitization.
    """
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
        return str(target_resolved).startswith(str(base) + os.sep) or target_resolved == base
    except (OSError, ValueError):
        return False


def create_safe_tempdir(prefix: str = "elt_") -> str:
    """Create a temporary directory and return its path."""
    return tempfile.mkdtemp(prefix=prefix)


def validate_url_scheme(url: str) -> None:
    """Raise SecurityError if URL scheme is not allowed."""
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SecurityError(
            f"URL scheme '{parsed.scheme}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_SCHEMES))}"
        )


def _is_loopback(addr: str) -> bool:
    """Check if an IP address is loopback or link-local."""
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _is_private_or_metadata(addr: str) -> bool:
    """Check if an IP address is private, reserved, or cloud metadata."""
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_reserved or ip.is_unspecified
    except ValueError:
        return False


def resolve_and_check_host(hostname: str) -> str:
    """Resolve hostname and reject loopback/private/metadata IPs."""
    try:
        infos = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise SecurityError(f"Cannot resolve host '{hostname}': {exc}") from exc

    for _family, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        if _is_loopback(ip_str):
            raise SecurityError(
                f"Host '{hostname}' resolves to loopback/link-local address {ip_str}"
            )
        if _is_private_or_metadata(ip_str):
            raise SecurityError(
                f"Host '{hostname}' resolves to private/metadata address {ip_str}"
            )
    return hostname


def validate_url(url: str) -> str:
    """Validate URL scheme and host. Returns the URL if valid."""
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
        return a.hostname == b.hostname
    except Exception:
        return False


def stream_download(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """Download a URL with streaming and enforce a size limit.

    Returns the response body as bytes.
    Raises SecurityError if the response exceeds *max_bytes*.
    """
    import requests

    validate_url(url)
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()

    content_length = resp.headers.get("Content-Length")
    if content_length and int(content_length) > max_bytes:
        resp.close()
        raise SecurityError(
            f"Response Content-Length ({content_length}) exceeds limit ({max_bytes})"
        )

    total = 0
    chunks = []
    for chunk in resp.iter_content(chunk_size=DEFAULT_STREAM_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            resp.close()
            raise SecurityError(
                f"Download exceeded size limit ({max_bytes} bytes)"
            )
        chunks.append(chunk)
    resp.close()
    return b"".join(chunks)


def safe_zip_extract(
    data: bytes,
    dest_dir: str,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_compressed_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> list[str]:
    """Extract a ZIP archive safely, preventing ZIP bombs and path traversal.

    Returns list of extracted file paths.
    """
    if len(data) > max_compressed_bytes:
        raise SecurityError(
            f"ZIP data ({len(data)} bytes) exceeds compressed size limit ({max_compressed_bytes})"
        )

    extracted: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        total_uncompressed = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed_bytes:
                raise SecurityError(
                    f"ZIP uncompressed content exceeds limit ({max_uncompressed_bytes} bytes)"
                )

        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) > max_files:
            raise SecurityError(
                f"ZIP contains more than {max_files} files"
            )

        for name in names:
            target = os.path.join(dest_dir, os.path.basename(name))
            if not is_safe_path(dest_dir, target):
                raise SecurityError(
                    f"ZIP entry '{name}' would escape extraction directory"
                )
            with zf.open(name) as src, open(target, "wb") as dst:
                total_read = 0
                while True:
                    buf = src.read(DEFAULT_STREAM_CHUNK)
                    if not buf:
                        break
                    total_read += len(buf)
                    if total_read > max_uncompressed_bytes:
                        raise SecurityError(
                            f"ZIP entry '{name}' exceeds uncompressed size limit"
                        )
                    dst.write(buf)
            extracted.append(target)

    return extracted
