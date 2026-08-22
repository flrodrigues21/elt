"""
Extrator generico para FTP.

Conecta a qualquer servidor FTP, lista e baixa arquivos, e retorna como DataFrame.

Configuracao via schedule (coluna config - JSONB):
{
    "ftp_host": "ftp.example.com",
    "ftp_port": 21,
    "ftp_user": "anonymous",
    "ftp_pass": "",
    "ftp_base": "/dados",
    "file_pattern": "*.csv",
    "file_format": "csv",
    "encoding": "utf-8",
    "max_files": 10
}
"""

import ftplib
import logging
import os
import re
import tempfile
from typing import Optional

import pandas as pd

from elt.src.extractors._security import (
    SecurityError,
    create_safe_tempdir,
    is_safe_path,
)
from elt.src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

DEFAULT_MAX_FTP_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


class FTPExtractor(BaseExtractor):
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.host = config.get("ftp_host", "")
        self.port = int(config.get("ftp_port", 21))
        self.user = config.get("ftp_user", "anonymous")
        self.password = config.get("ftp_pass", "")
        self.base_path = config.get("ftp_base", "/")
        self.file_pattern = config.get("file_pattern", "")
        self.file_format = config.get("file_format", "csv")
        self.encoding = config.get("encoding", "utf-8")
        self.max_files = int(config.get("max_files", 0))

    def _connect(self) -> ftplib.FTP:
        ftp = ftplib.FTP()
        ftp.connect(self.host, self.port, timeout=30)
        ftp.login(self.user, self.password)
        logger.info(f"[FTP] Conectado a {self.host}:{self.port}")
        return ftp

    def _list_files(self, ftp: ftplib.FTP) -> list[str]:
        raw = []
        ftp.retrlines(f"LIST {self.base_path}", raw.append)

        files = []
        for line in raw:
            parts = line.split()
            if not parts:
                continue
            name = parts[-1]
            if name in (".", ".."):
                continue
            if self.file_pattern:
                if not re.match(
                    self.file_pattern.replace(".", "\\.").replace("*", ".*"),
                    name,
                ):
                    continue
            files.append(name)

        files.sort()
        if self.max_files > 0:
            files = files[: self.max_files]

        logger.info(
            f"[FTP] {len(files)} arquivo(s) encontrado(s) em {self.base_path}"
        )
        return files

    def _download(self, ftp: ftplib.FTP, filename: str) -> str:
        remote = f"{self.base_path}/{filename}"
        tmp = os.path.join(create_safe_tempdir(), os.path.basename(filename))

        if not is_safe_path(os.path.dirname(tmp), tmp):
            raise SecurityError(
                f"Download path escapes temp directory: {filename}"
            )

        total_bytes = 0
        max_bytes = DEFAULT_MAX_FTP_BYTES

        def _write_with_limit(data):
            nonlocal total_bytes
            total_bytes += len(data)
            if total_bytes > max_bytes:
                raise SecurityError(
                    f"FTP download exceeded size limit ({max_bytes} bytes)"
                )
            f.write(data)

        with open(tmp, "wb") as f:
            ftp.retrbinary(f"RETR {remote}", _write_with_limit)

        return tmp

    def _read_file(self, path: str) -> pd.DataFrame:
        fmt = self.file_format.lower()

        if fmt == "csv":
            return pd.read_csv(path, encoding=self.encoding)
        elif fmt == "parquet":
            return pd.read_parquet(path)
        elif fmt == "json":
            return pd.read_json(path)
        elif fmt == "tsv":
            return pd.read_csv(path, sep="\t", encoding=self.encoding)
        elif fmt == "excel":
            return pd.read_excel(path)
        else:
            return pd.read_csv(path, encoding=self.encoding)

    def extract(self, row: dict) -> pd.DataFrame:
        config = row.get("config")
        if config and isinstance(config, dict):
            self.host = config.get("ftp_host", self.host)
            self.port = int(config.get("ftp_port", self.port))
            self.user = config.get("ftp_user", self.user)
            self.password = config.get("ftp_pass", self.password)
            self.base_path = config.get("ftp_base", self.base_path)
            self.file_pattern = config.get("file_pattern", self.file_pattern)
            self.file_format = config.get("file_format", self.file_format)
            self.encoding = config.get("encoding", self.encoding)
            self.max_files = int(config.get("max_files", self.max_files))

        if not self.host:
            url = row.get("url", "")
            if url:
                url = url.replace("ftp://", "")
                self.host = url.split("/")[0]
                self.base_path = "/" + "/".join(url.split("/")[1:])

        if not self.host:
            raise ValueError("ftp_host nao definido no config ou url")

        ftp = self._connect()
        try:
            files = self._list_files(ftp)
            if not files:
                raise ValueError(
                    f"Nenhum arquivo encontrado em {self.base_path} "
                    f"com pattern '{self.file_pattern}'"
                )

            frames = []
            for filename in files:
                logger.info(f"[FTP] Baixando {filename}")
                tmp = self._download(ftp, filename)
                try:
                    df = self._read_file(tmp)
                    frames.append(df)
                    logger.info(f"[FTP] {filename}: {len(df)} registros")
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)

            df_final = pd.concat(frames, ignore_index=True)
            logger.info(
                f"[FTP] Total: {len(df_final)} registros de {len(files)} arquivo(s)"
            )
            return df_final
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
