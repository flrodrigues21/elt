import logging
import os
import tempfile

import pandas as pd
import requests

from elt.src.connectors.airflow_connections import AirflowConnector
from elt.src.extractors._security import (
    SecurityError,
    create_safe_tempdir,
    is_safe_path,
    sanitize_filename,
    stream_download,
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

        response = requests.post(
            url=url,
            json=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )

        if response.status_code == 401:
            raise ValueError(
                f"Autenticacao falhou para {url}: "
                f"HTTP {response.status_code} - verifique login/senha"
            )

        response.raise_for_status()

        data = response.json()
        token = data.get("token")
        if not token:
            raise ValueError(f"Resposta de login nao contem campo 'token': {data}")

        logger.info(f"API [{self.source_connection}] Token obtido com sucesso")
        return token

    def _build_url(self, endpoint: str = None) -> str:
        base = self.base_url.rstrip("/")
        ep = (endpoint or self.endpoint).lstrip("/")
        return f"{base}/{ep}"

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

        response = requests.request(
            method=self.method,
            url=url,
            headers=headers,
            params=self.params or None,
            json=self.body or None,
            auth=auth,
            timeout=30,
        )

        if response.status_code == 401:
            if self.auth_type == "token":
                logger.info("Token expirado, reautenticando...")
                self.token = self._authenticate_token()
                headers["Authorization"] = f"Bearer {self.token}"
                response = requests.request(
                    method=self.method,
                    url=url,
                    headers=headers,
                    params=self.params or None,
                    json=self.body or None,
                    timeout=30,
                )
            else:
                raise ValueError(
                    f"Autenticacao falhou para {url}: "
                    f"HTTP {response.status_code} - verifique login/senha na Connection Airflow"
                )

        if response.status_code == 403:
            raise ValueError(
                f"Acesso negado para {url}: "
                f"HTTP {response.status_code} - verifique permissoes do usuario"
            )

        if response.status_code == 404:
            raise ValueError(
                f"Recurso nao encontrado para {url}: "
                f"HTTP {response.status_code}"
            )

        if response.status_code >= 500:
            raise ValueError(
                f"Erro no servidor remoto para {url}: "
                f"HTTP {response.status_code}"
            )

        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        content_disposition = response.headers.get("Content-Disposition", "")

        if "application/json" in content_type or "text" in content_type:
            data = response.json()
            if isinstance(data, list):
                return pd.DataFrame(data)
            if isinstance(data, dict):
                documents = data.get("documents", [])
                if documents:
                    return pd.DataFrame(documents)
                return pd.DataFrame([data])
            return pd.DataFrame([data])

        if "attachment" in content_disposition or "filename" in content_disposition:
            filename = None
            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=")[-1].strip('"')
            elif "filename*" in content_disposition:
                filename = content_disposition.split("filename*=")[-1].strip('"')

            safe_name = sanitize_filename(filename or "download.bin")
            tmp_dir = create_safe_tempdir()
            tmp_path = os.path.join(tmp_dir, safe_name)

            if not is_safe_path(tmp_dir, tmp_path):
                raise SecurityError(
                    f"Resolved path escapes temp directory: {tmp_path}"
                )

            max_bytes = self.config.get("max_download_bytes", 2 * 1024 * 1024 * 1024)
            content = stream_download(url, max_bytes=max_bytes)

            with open(tmp_path, "wb") as f:
                f.write(content)

            logger.info(f"Arquivo salvo temporariamente: {tmp_path}")
            return pd.DataFrame(
                [{"file_path": tmp_path, "filename": safe_name}]
            )

        return pd.DataFrame(
            [{"raw_content": response.content, "status_code": response.status_code}]
        )
