"""API REST extractor.

Single request per attempt.  Preserves method, auth, headers, params, body.
Streams attachment downloads directly to a unique temp file.  Redirects are
followed manually with SSRF validation on each hop.  JSON/text/raw responses
are size-limited and streamed via iter_content.
"""
import json
import logging
import os

import pandas as pd
import requests

from elt.src.connectors.airflow_connections import AirflowConnector
from elt.src.extractors._security import (
    DEFAULT_STREAM_CHUNK,
    SecurityError,
    safe_request,
    sanitize_filename,
    stream_download_to_file,
    unique_temp_path,
    validate_url,
)
from elt.src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class ApiExtractor(BaseExtractor):
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.source_connection = self.config.get("connection_airflow")
        if not self.source_connection or not str(self.source_connection).strip():
            raise ValueError(
                "A chave 'connection_airflow' e obrigatoria no config "
                "para o extrator API (ex.: {'connection_airflow': 'ceos_api'})."
            )
        self.source_connection = str(self.source_connection).strip()
        self.base_url = self.config.get("base_url", "")
        self.endpoint = self.config.get("endpoint", "")
        self.method = self.config.get("method", "GET").upper()
        self.extra_headers = self.config.get("headers", {})
        self.params = self.config.get("params", {})
        self.body = self.config.get("body", {})
        self.auth_type = self.config.get("auth_type", "basic")
        self.login_endpoint = self.config.get("login_endpoint", "/service/login")
        self.login_body = self.config.get("login_body", {})
        self.token = None

    def _get_credentials(self):
        airflow_connector = AirflowConnector()
        creds = airflow_connector.get_connection(self.source_connection)
        return creds.get("login", ""), creds.get("password", "")

    def _authenticate_token(self) -> str:
        url = self._build_url(self.login_endpoint)
        validate_url(url)
        user, password = self._get_credentials()
        body = self.login_body or {"user": user, "pass": password}

        logger.info(f"API [{self.source_connection}] Autenticando em {url}")

        resp = safe_request(
            "POST",
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token")
        if not token:
            raise ValueError(f"Resposta de login nao contem campo 'token': {data}")

        logger.info(f"API [{self.source_connection}] Token obtido com sucesso")
        return token

    def _build_url(self, endpoint: str = None) -> str:
        base = self.base_url.rstrip("/")
        ep = (endpoint or self.endpoint).lstrip("/")
        return f"{base}/{ep}"

    # ------------------------------------------------------------------
    def _get_max_download_bytes(self) -> int:
        return int(self.config.get("max_download_bytes", 500 * 1024 * 1024))

    def _stream_response(self, response: requests.Response, max_bytes: int) -> bytes:
        """Stream response body via iter_content, enforcing *max_bytes*.

        Returns the complete body as bytes.  Caller must close *response*.
        """
        total = 0
        chunks: list[bytes] = []
        for chunk in response.iter_content(chunk_size=DEFAULT_STREAM_CHUNK):
            total += len(chunk)
            if total > max_bytes:
                raise SecurityError(
                    f"Response body exceeded size limit ({max_bytes} bytes)"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def extract(self, row: dict) -> pd.DataFrame:
        url = self._build_url()
        validate_url(url)

        headers = {"Accept": "application/json"}
        headers.update(self.extra_headers)

        auth = None
        if self.auth_type == "token":
            self.token = self._authenticate_token()
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.auth_type == "basic":
            user, password = self._get_credentials()
            if user:
                auth = (user, password)

        logger.info(f"API [{self.source_connection}] {self.method} {url}")

        response = safe_request(
            self.method,
            url,
            headers=headers,
            params=self.params or None,
            json=self.body or None,
            auth=auth,
            timeout=30,
        )

        if response.status_code == 401 and self.auth_type == "token":
            logger.info("Token expirado, reautenticando...")
            self.token = self._authenticate_token()
            headers["Authorization"] = f"Bearer {self.token}"
            response.close()
            response = safe_request(
                self.method,
                url,
                headers=headers,
                params=self.params or None,
                json=self.body or None,
                timeout=30,
            )

        self._raise_for_status(response, url)

        content_type = response.headers.get("Content-Type", "")
        content_disposition = response.headers.get("Content-Disposition", "")
        max_bytes = self._get_max_download_bytes()

        # Check Content-Length before reading body
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    response.close()
                    raise SecurityError(
                        f"Content-Length ({content_length}) exceeds limit "
                        f"({max_bytes})"
                    )
            except (ValueError, TypeError):
                pass

        # JSON / text → stream via iter_content, enforce size limit
        if "application/json" in content_type or "text" in content_type:
            try:
                raw = self._stream_response(response, max_bytes)
                try:
                    data = json.loads(raw.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ValueError(f"Resposta invalida (nao e JSON/texto): {exc}")
                if isinstance(data, list):
                    return pd.DataFrame(data)
                if isinstance(data, dict):
                    documents = data.get("documents", [])
                    if documents:
                        return pd.DataFrame(documents)
                    return pd.DataFrame([data])
                return pd.DataFrame([data])
            finally:
                response.close()

        # Attachment → stream to unique temp file (large)
        if "attachment" in content_disposition or "filename" in content_disposition:
            filename = self._parse_filename(content_disposition)
            safe_name = sanitize_filename(filename or "download.bin")
            tmp_path = unique_temp_path(
                suffix=os.path.splitext(safe_name)[1] or ".bin"
            )
            try:
                total = 0
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=DEFAULT_STREAM_CHUNK):
                        total += len(chunk)
                        if total > max_bytes:
                            raise SecurityError(
                                f"Download exceeded size limit ({max_bytes} bytes)"
                            )
                        f.write(chunk)
            except BaseException:
                from elt.src.extractors._security import _safe_remove
                _safe_remove(tmp_path)
                raise
            finally:
                response.close()

            logger.info(f"Arquivo salvo temporariamente: {tmp_path}")
            return pd.DataFrame(
                [{"file_path": tmp_path, "filename": safe_name}]
            )

        # Fallback: raw content via iter_content, enforce size limit
        try:
            raw = self._stream_response(response, max_bytes)
            return pd.DataFrame(
                [{"raw_content": raw, "status_code": response.status_code}]
            )
        finally:
            response.close()

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_filename(content_disposition: str) -> str | None:
        if "filename=" in content_disposition:
            return content_disposition.split("filename=")[-1].strip('"')
        if "filename*" in content_disposition:
            return content_disposition.split("filename*=")[-1].strip('"')
        return None

    @staticmethod
    def _raise_for_status(response: requests.Response, url: str) -> None:
        if response.status_code == 401:
            raise ValueError(
                f"Autenticacao falhou para {url}: "
                f"HTTP {response.status_code} - verifique login/senha"
            )
        if response.status_code == 403:
            raise ValueError(
                f"Acesso negado para {url}: "
                f"HTTP {response.status_code} - verifique permissoes"
            )
        if response.status_code == 404:
            raise ValueError(
                f"Recurso nao encontrado para {url}: HTTP {response.status_code}"
            )
        if response.status_code >= 500:
            raise ValueError(
                f"Erro no servidor remoto para {url}: "
                f"HTTP {response.status_code}"
            )
        response.raise_for_status()
