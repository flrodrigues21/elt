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
import zipfile
from typing import Optional

import pandas as pd
import requests

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

        delimiter = config.get("delimiter", ";")
        encoding = config.get("encoding", "latin-1")
        compression = config.get("compression", None)
        header_row = config.get("header_row", 0)

        logger.info(f"Baixando de {url}...")
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()

        if compression == "zip" or url.endswith(".zip"):
            zip_path = os.path.join(tempfile.gettempdir(), "download.zip")
            with open(zip_path, "wb") as f:
                f.write(resp.content)
            with zipfile.ZipFile(zip_path, "r") as z:
                csv_name = [n for n in z.namelist() if n.endswith(".csv")][0]
                with z.open(csv_name) as f:
                    raw = f.read().decode(encoding)
            os.remove(zip_path)

            reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
            header = [c.strip().strip('"').strip() for c in next(reader)]
            rows = list(reader)
            df = pd.DataFrame(rows, columns=header)

        elif url.endswith(".csv"):
            raw = resp.content.decode(encoding)
            reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
            header = [c.strip().strip('"').strip() for c in next(reader)]
            rows = list(reader)
            df = pd.DataFrame(rows, columns=header)

        elif url.endswith(".parquet"):
            tmp = os.path.join(tempfile.gettempdir(), "download.parquet")
            with open(tmp, "wb") as f:
                f.write(resp.content)
            df = pd.read_parquet(tmp)
            os.remove(tmp)

        else:
            raw = resp.content.decode(encoding)
            reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
            header = [c.strip().strip('"').strip() for c in next(reader)]
            rows = list(reader)
            df = pd.DataFrame(rows, columns=header)

        logger.info(f"Extraidos {len(df)} registros de {url}")
        return df.reset_index(drop=True)
