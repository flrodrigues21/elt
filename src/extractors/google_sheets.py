import io
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from elt.src.extractors.base import BaseExtractor

BASE_DIR = Path(__file__).resolve().parents[2]
credential_dir = Path(BASE_DIR / "utils" / "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Mimetype de arquivo Google Sheets nativo (planilha).
SHEETS_MIMETYPE = "application/vnd.google-apps.spreadsheet"


class GoogleSheetsExtractor(BaseExtractor):
    def __init__(
        self,
        spreadsheet_id_or_url: str,
        conn_id: str | None = None,
        credentials_path: Path = credential_dir
    ):
        self.spreadsheet_id_or_url = spreadsheet_id_or_url
        self.conn_id = self._normalize_conn_id(conn_id)
        self.credentials_path = Path(credentials_path)
        self.credentials = self._build_credentials()
        self.client = gspread.authorize(self.credentials)
        self.file_id = self._extract_spreadsheet_id(
            self.spreadsheet_id_or_url
        )
        # Decide o caminho ANTES, olhando a extensao do arquivo no Drive.
        self.mode = 'xlsx' if self._file_is_xlsx(self.file_id) else 'sheets'
        if self.mode == 'sheets':
            self.spreadsheet = self.client.open_by_key(self.file_id)

    @staticmethod
    def _normalize_conn_id(conn_id) -> str | None:
        if conn_id is None:
            return None
        if isinstance(conn_id, float) and pd.isna(conn_id):
            return None
        conn_id = str(conn_id).strip()
        if not conn_id or conn_id.lower() in ('nan', 'none'):
            return None
        return conn_id

    def _build_credentials(self):
        if self.conn_id:
            logging.info(
                f"Autenticando Google via connection '{self.conn_id}'"
            )
            return self._credentials_from_connection()
        if self.credentials_path.exists():
            logging.info(
                f"Autenticando Google Sheets via arquivo {self.credentials_path}"
            )
            return Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
        raise FileNotFoundError(
            f"Credenciais do Google nao encontradas. "
            f"Informe um conn_id do Airflow ou coloque o arquivo "
            f"{self.credentials_path}."
        )

    def _credentials_from_connection(self):
        from airflow.hooks.base import BaseHook
        conn = BaseHook.get_connection(self.conn_id)
        extra = conn.extra_dejson or {}
        info = extra.get('keyfile_json', extra)
        if isinstance(info, str):
            info = json.loads(info)
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    def _build_drive_service(self):
        from googleapiclient.discovery import build
        return build('drive', 'v3', credentials=self.credentials)

    def _file_is_xlsx(self, file_id: str) -> bool:
        if not file_id:
            return False
        try:
            meta = self._build_drive_service().files().get(
                fileId=file_id, fields='name,mimeType'
            ).execute()
        except Exception as e:
            logging.warning(
                f"Nao foi possivel verificar o arquivo no Drive ({e}); "
                f"assumindo Google Sheets nativo."
            )
            return False
        self.file_name = meta.get('name', '')
        mime = meta.get('mimeType', '')
        logging.info(
            f"Arquivo '{self.file_name}' | mimeType={mime}"
        )
        return (
            mime != SHEETS_MIMETYPE
            and str(self.file_name).lower().endswith('.xlsx')
        )

    def _extract_spreadsheet_id(self, spreadsheet_id_or_url: str) -> str:
        url = str(spreadsheet_id_or_url).strip()
        if not url.startswith(('http://', 'https://')):
            return url
        match = re.search(
            r'/(?:spreadsheets/|file/)?d/([a-zA-Z0-9_-]+)',
            url
        )
        if match:
            return match.group(1)
        query = parse_qs(urlparse(url).query)
        for key in ('id', 'fileid', 'spreadsheetid', 'docid'):
            if key in query and query[key]:
                return query[key][0]
        raise ValueError(f"URL do Google invalida: {spreadsheet_id_or_url}")

    def _rows_from_xlsx(self, sheet_name=None) -> list[list]:
        request = self._build_drive_service().files().get_media(
            fileId=self.file_id
        )
        file_bytes = request.execute()
        excel = pd.ExcelFile(io.BytesIO(file_bytes), engine='openpyxl')
        if not sheet_name or not str(sheet_name).strip():
            sheet_name = excel.sheet_names[0]
        df = pd.read_excel(excel, sheet_name=sheet_name, header=None)
        return df.values.tolist()

    def _rows_to_dataframe(
        self,
        rows: list[list],
        header_row=None,
        expected_columns=None,
        table_name=None
    ) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        if header_row is not None:
            header_index = int(header_row) - 1
            df.columns = df.iloc[header_index].apply(
                lambda c: '' if pd.isna(c) else str(c)
            )
            df = df.iloc[header_index + 1:]

        df.columns = [
            self._normalize_column_name(col)
            for col in df.columns
        ]
        df.columns = [
            f"coluna_vazia_{i}"
            if str(col).strip() == ""
            else col
            for i, col in enumerate(df.columns)
        ]

        if expected_columns:
            df = self._filter_expected_columns(
                df=df,
                expected_columns=expected_columns,
                table_name=table_name
            )

        return df.reset_index(drop=True)

    def _normalize_column_name(self, column_name: str) -> str:
        return str(column_name).strip().lower().replace('\n', '').replace('  ', ' ')

    def _filter_expected_columns(
        self,
        df: pd.DataFrame,
        expected_columns: list[str],
        table_name: str | None = None
    ) -> pd.DataFrame:
        expected_columns = [
            self._normalize_column_name(col)
            for col in expected_columns
        ]
        df = df.copy()
        df.columns = [
            self._normalize_column_name(col)
            for col in df.columns
        ]
        current_columns = list(df.columns)
        missing_columns = [
            col for col in expected_columns
            if col not in current_columns
        ]
        extra_columns = [
            col for col in current_columns
            if col not in expected_columns
        ]
        if missing_columns:
            logging.warning(
                f"Colunas esperadas ausentes em {table_name}: {missing_columns}"
            )
        if extra_columns:
            logging.warning(
                f"Colunas extras ignoradas em {table_name}: {extra_columns}"
            )
        for col in missing_columns:
            df[col] = None
        return df[expected_columns]

    def extract(self, row: dict) -> pd.DataFrame:
        sheet_name = row.get('table_source')
        header_row = row.get('header_row_source')
        expected_columns = row.get('columns_source')
        table_name = row.get('table_destiny', sheet_name)

        if expected_columns and isinstance(expected_columns, str):
            expected_columns = [c.strip() for c in expected_columns.split(',')]

        if self.mode == 'xlsx':
            rows = self._rows_from_xlsx(sheet_name)
        else:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            rows = worksheet.get_all_values()

        return self._rows_to_dataframe(
            rows=rows,
            header_row=header_row,
            expected_columns=expected_columns,
            table_name=table_name
        )

    def list_sheet_names(self) -> list[str]:
        if self.mode == 'xlsx':
            file_bytes = self._build_drive_service().files().get_media(
                fileId=self.file_id
            ).execute()
            return pd.ExcelFile(
                io.BytesIO(file_bytes), engine='openpyxl'
            ).sheet_names
        return [
            worksheet.title
            for worksheet in self.spreadsheet.worksheets()
        ]