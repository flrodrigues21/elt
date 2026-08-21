import logging
import os
import tempfile

import pandas as pd
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MinioConnector:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.endpoint = config.get(
            "endpoint", os.getenv("MINIO_ENDPOINT", "localhost:9000")
        )
        self.access_key = config.get(
            "access_key", os.getenv("MINIO_ACCESS_KEY", "")
        )
        self.secret_key = config.get(
            "secret_key", os.getenv("MINIO_SECRET_KEY", "")
        )
        self.secure = config.get(
            "secure", os.getenv("MINIO_SECURE", "false").lower() == "true"
        )
        self.bucket = config.get("bucket", os.getenv("MINIO_BUCKET", "cnes-bronze"))
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

    def ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info(f"Bucket criado: {self.bucket}")
        else:
            logger.info(f"Bucket ja existe: {self.bucket}")

    def upload_file(
        self,
        file_path: str,
        object_name: str,
        content_type: str | None = None,
    ) -> str:
        self.ensure_bucket()
        self.client.fput_object(
            bucket_name=self.bucket,
            object_name=object_name,
            file_path=file_path,
            content_type=content_type,
        )
        url = f"minio://{self.bucket}/{object_name}"
        logger.info(f"Upload realizado: {url}")
        return url

    def upload_dataframe(
        self,
        df: pd.DataFrame,
        object_name: str,
        format: str = "parquet",
        content_type: str | None = None,
    ) -> str:
        tmp_dir = os.getenv("TMPDIR", tempfile.gettempdir())
        ext = format.lower()
        tmp_path = os.path.join(tmp_dir, os.path.basename(object_name))

        if ext == "parquet":
            df.to_parquet(tmp_path, index=False)
            ct = content_type or "application/octet-stream"
        elif ext == "csv":
            df.to_csv(tmp_path, index=False)
            ct = content_type or "text/csv"
        elif ext == "json":
            df.to_json(tmp_path, orient="records", indent=2)
            ct = content_type or "application/json"
        else:
            raise ValueError(f"Formato nao suportado para upload: {format}")

        try:
            return self.upload_file(tmp_path, object_name, content_type=ct)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def list_objects(self, prefix: str = "") -> list:
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]

    def object_exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False

    def read_dataframe(
        self,
        object_name: str,
        format: str = "parquet",
    ) -> pd.DataFrame:
        tmp_dir = os.getenv("TMPDIR", tempfile.gettempdir())
        ext = format.lower()
        tmp_path = os.path.join(tmp_dir, object_name.replace("/", "_"))

        self.client.fget_object(self.bucket, object_name, tmp_path)

        try:
            if ext == "parquet":
                df = pd.read_parquet(tmp_path)
            elif ext == "csv":
                df = pd.read_csv(tmp_path)
            elif ext == "json":
                df = pd.read_json(tmp_path)
            else:
                raise ValueError(f"Formato nao suportado para leitura: {format}")

            logger.info(f"Lido {len(df)} registros de minio://{self.bucket}/{object_name}")
            return df
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)