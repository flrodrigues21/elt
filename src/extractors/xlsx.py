from pathlib import Path
import pandas as pd

from elt.src.extractors.base import BaseExtractor


class XlsxExtractor(BaseExtractor):
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {self.file_path}")

    def extract(self, row: dict) -> pd.DataFrame:
        sheet_name = row.get('table_source')
        header_row = row.get('header_row_source')

        if sheet_name:
            df = pd.read_excel(
                self.file_path,
                sheet_name=sheet_name,
                engine="openpyxl",
                header=header_row - 1 if header_row else 0
            )
        else:
            df = pd.read_excel(
                self.file_path,
                engine="openpyxl",
                header=header_row - 1 if header_row else 0
            )

        return df.reset_index(drop=True)
