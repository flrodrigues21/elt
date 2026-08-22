"""
Extrator generico para S3 / CKAN / URLs HTTP.

Baixa arquivos CSV (zipados ou nao) de URLs publicas ou S3 e retorna DataFrame.

Configuracao via schedule (coluna config - JSONB):
{
    "delimiter": ";",
    "encoding": "latin-1",
    "compression": "zip",
    "header_row": 1,
    "file_extension": ".csv",
    "max_download_bytes": 524288000
}
"""
import csv
import io
import logging
import os

import pandas as pd

from elt.src.extractors._security import (
    SecurityError,
    safe_zip_extract,
    stream_download_to_file,
    unique_temp_path,
    validate_url,
)
from elt.src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class S3Extractor(BaseExtractor):
    def extract(self, row: dict) -> pd.DataFrame:
        url = row.get("url", "")
        config = row.get("config", {})
        if isinstance(config, str):
            import json
            config = json.loads(config)

        if not url:
            raise ValueError("URL nao definida para extracao S3")

        validate_url(url)

        delimiter = config.get("delimiter", ";")
        encoding = config.get("encoding", "latin-1")
        compression = config.get("compression", None)
        max_bytes = config.get("max_download_bytes", 500 * 1024 * 1024)

        logger.info(f"Baixando de {url}...")
        download_path = stream_download_to_file(url, max_bytes=max_bytes)

        try:
            if compression == "zip" or url.endswith(".zip"):
                df = self._extract_zip(download_path, encoding, delimiter, config)
            elif url.endswith(".csv") or url.endswith(".csv.gz"):
                df = self._extract_csv(download_path, encoding, delimiter)
            elif url.endswith(".parquet"):
                df = pd.read_parquet(download_path)
            else:
                df = self._extract_csv(download_path, encoding, delimiter)
        finally:
            from elt.src.extractors._security import _safe_remove
            _safe_remove(download_path)

        logger.info(f"Extraidos {len(df)} registros de {url}")
        return df.reset_index(drop=True)

    def _extract_zip(
        self, zip_path: str, encoding: str, delimiter: str, config: dict
    ) -> pd.DataFrame:
        with open(zip_path, "rb") as f:
            zip_data = f.read()

        tmp_dir = unique_temp_path(suffix="").rstrip(".")
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            extracted = safe_zip_extract(zip_data, tmp_dir)
            csv_files = [f for f in extracted if f.endswith(".csv")]
            if not csv_files:
                raise ValueError("ZIP nao contem arquivos .csv")

            with open(csv_files[0], encoding=encoding) as f:
                raw = f.read()
        finally:
            for p in extracted:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass

        reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
        header = [c.strip().strip('"').strip() for c in next(reader)]
        rows = list(reader)
        return pd.DataFrame(rows, columns=header)

    def _extract_csv(self, path: str, encoding: str, delimiter: str) -> pd.DataFrame:
        with open(path, encoding=encoding) as f:
            raw = f.read()
        reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
        header = [c.strip().strip('"').strip() for c in next(reader)]
        rows = list(reader)
        return pd.DataFrame(rows, columns=header)
