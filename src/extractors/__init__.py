from elt.src.extractors.base import BaseExtractor
from elt.src.extractors.google_sheets import GoogleSheetsExtractor
from elt.src.extractors.postgres import PostgresExtractor
from elt.src.extractors.oracle import OracleExtractor
from elt.src.extractors.xlsx import XlsxExtractor
from elt.src.extractors.ftp import FTPExtractor
from elt.src.extractors.s3 import S3Extractor
from elt.src.extractors.minio import MinioExtractor
from elt.src.extractors.api import ApiExtractor


EXTRACTOR_REGISTRY = {
    'GOOGLE_SHEETS': GoogleSheetsExtractor,
    'POSTGRE': PostgresExtractor,
    'ORACLE': OracleExtractor,
    'XLSX': XlsxExtractor,
    'FTP': FTPExtractor,
    'S3': S3Extractor,
    'CKAN': S3Extractor,
    'CSV_URL': S3Extractor,
    'MINIO': MinioExtractor,
    'API': ApiExtractor,
}


def get_extractor(type_source: str):
    type_upper = type_source.upper().strip()
    if type_upper not in EXTRACTOR_REGISTRY:
        raise ValueError(
            f"Tipo de extrator desconhecido: '{type_source}'. "
            f"Disponiveis: {list(EXTRACTOR_REGISTRY.keys())}"
        )
    return EXTRACTOR_REGISTRY[type_upper]


def register_extractor(type_source: str, extractor_class):
    EXTRACTOR_REGISTRY[type_source.upper().strip()] = extractor_class
