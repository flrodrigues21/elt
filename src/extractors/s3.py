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
    "use_minio": false,
    "minio_endpoint": "minio.example.com:9000",
    "minio_bucket": "cnes-bronze",
    "minio_object": "caminho/arquivo.parquet"
}
"""

import csv
import io
import logging
import os
import tempfile

import pandas as pd

from elt.src.extractors._security import (
    SecurityError,
    create_safe_tempdir,
    safe_zip_extract,
    stream_download,
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
        header_row = config.get("header_row", 0)
        max_bytes = config.get("max_download_bytes", 2 * 1024 * 1024 * 1024)

        logger.info(f"Baixando de {url}...")
        resp_bytes = stream_download(url, max_bytes=max_bytes)

        if compression == "zip" or url.endswith(".zip"):
            tmp_dir = create_safe_tempdir()
            extracted_files = safe_zip_extract(resp_bytes, tmp_dir)
            csv_files = [f for f in extracted_files if f.endswith(".csv")]
            if not csv_files:
                raise ValueError("ZIP nao contem arquivos .csv")
            csv_path = csv_files[0]
            with open(csv_path, encoding=encoding) as f:
                raw = f.read()
            for f in extracted_files:
                os.remove(f)
            os.rmdir(tmp_dir)

            reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
            header = [c.strip().strip('"').strip() for c in next(reader)]
            rows = list(reader)
            df = pd.DataFrame(rows, columns=header)

        elif url.endswith(".csv"):
            raw = resp_bytes.decode(encoding)
            reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
            header = [c.strip().strip('"').strip() for c in next(reader)]
            rows = list(reader)
            df = pd.DataFrame(rows, columns=header)

        elif url.endswith(".parquet"):
            tmp = os.path.join(tempfile.gettempdir(), "download.parquet")
            with open(tmp, "wb") as f:
                f.write(resp_bytes)
            df = pd.read_parquet(tmp)
            os.remove(tmp)

        else:
            raw = resp_bytes.decode(encoding)
            reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
            header = [c.strip().strip('"').strip() for c in next(reader)]
            rows = list(reader)
            df = pd.DataFrame(rows, columns=header)

        logger.info(f"Extraidos {len(df)} registros de {url}")
        return df.reset_index(drop=True)
