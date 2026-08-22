"""
Extrator para ler dados do MinIO (arquivos .parquet).

Configuracao via schedule (coluna config - JSONB):
{
    "endpoint": "minio.example.com:9000",
    "bucket": "cnes-bronze",
    "object_name": "st/2604/data.parquet",
    "secure": false
}
"""
import logging
import os
from typing import Optional

import pandas as pd
from minio import Minio

from elt.src.extractors._security import (
    _safe_remove,
    is_safe_path,
    sanitize_filename,
    unique_temp_path,
)
from elt.src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class MinioExtractor(BaseExtractor):
    def _conectar(self, config: dict):
        endpoint = config.get("endpoint", os.getenv("MINIO_ENDPOINT", "localhost:9000"))
        access_key = config.get("access_key", os.getenv("MINIO_ACCESS_KEY", ""))
        secret_key = config.get("secret_key", os.getenv("MINIO_SECRET_KEY", ""))
        secure = config.get("secure", os.getenv("MINIO_SECURE", "false").lower() == "true")

        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        return client

    def extract(self, row: dict) -> pd.DataFrame:
        config = row.get("config", {})
        if isinstance(config, str):
            import json
            config = json.loads(config)

        bucket = config.get("bucket", os.getenv("MINIO_BUCKET", "cnes-bronze"))
        object_name = config.get("object_name", "")

        if not object_name:
            url = row.get("url", "")
            if url:
                object_name = url

        if not object_name:
            raise ValueError(
                "object_name nao definido no config ou url na schedule"
            )

        client = self._conectar(config)

        # Unique temp path – no collision between DAGs
        ext = os.path.splitext(object_name)[1] or ".parquet"
        tmp_path = unique_temp_path(suffix=ext)

        logger.info(f"Baixando minio://{bucket}/{object_name}")
        client.fget_object(bucket, object_name, tmp_path)

        try:
            if object_name.endswith(".parquet"):
                df = pd.read_parquet(tmp_path)
            elif object_name.endswith(".csv"):
                df = pd.read_csv(tmp_path)
            else:
                df = pd.read_parquet(tmp_path)

            logger.info(f"Extraidos {len(df)} registros do MinIO")
            return df
        finally:
            _safe_remove(tmp_path)
