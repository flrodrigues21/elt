"""
Extrator generico para FTP DATASUS (arquivos .dbc).

Baixa arquivos DBC de um tema FTP, converte para DataFrame e retorna.

Configuracao via schedule (coluna config - JSONB):
{
    "ftp_host": "ftp.datasus.gov.br",
    "ftp_base": "dissemin/publicos/CNES/200508_/Dados",
    "theme": "ST",
    "ano_mes": "2604",
    "ufs": ["PE", "BA", "CE", "MA", "PB", "PI", "RN", "SE", "AL"],
    "max_workers": 5,
    "encoding": "latin-1"
}
"""

import ftplib
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

from elt.src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

UFS_BRASIL = sorted([
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
])


class FTPDatasusExtractor(BaseExtractor):
    def __init__(self, config: dict):
        self.ftp_host = config.get("ftp_host", "ftp.datasus.gov.br")
        self.ftp_base = config.get("ftp_base", "dissemin/publicos/CNES/200508_/Dados")
        self.theme = config.get("theme", "ST")
        self.ano_mes = config.get("ano_mes", "2604")
        self.ufs = config.get("ufs", UFS_BRASIL)
        self.max_workers = int(config.get("max_workers", 5))
        self.encoding = config.get("encoding", "latin-1")

    def _listar_arquivos(self) -> list[str]:
        arquivos = []
        with ftplib.FTP(self.ftp_host) as ftp:
            ftp.login()
            raw = []
            ftp.dir(f"{self.ftp_base}/{self.theme}/", raw.append)
            for linha in raw:
                nome = linha.split()[-1]
                if nome.endswith(".dbc") and self.ano_mes in nome:
                    arquivos.append(nome)
        return sorted(arquivos)

    def _baixar_dbc(self, filename: str) -> str:
        tmp = os.path.join(tempfile.gettempdir(), filename)
        with ftplib.FTP(self.ftp_host) as ftp:
            ftp.login()
            with open(tmp, "wb") as f:
                ftp.retrbinary(
                    f"RETR {self.ftp_base}/{self.theme}/{filename}",
                    f.write
                )
        return tmp

    def _dbc_para_dataframe(self, dbc_path: str) -> pd.DataFrame:
        from dbfread import DBF
        from pyreaddbc.readdbc import dbc2dbf

        dbf_path = dbc_path.replace(".dbc", ".dbf")
        try:
            dbc2dbf(dbc_path, dbf_path)
            dbf = DBF(dbf_path, encoding=self.encoding)
            df = pd.DataFrame(list(dbf))
            return df
        finally:
            for p in [dbf_path]:
                if os.path.exists(p):
                    os.remove(p)

    def _processar_uf(self, uf_sigla: str) -> Optional[pd.DataFrame]:
        filename = f"{self.theme}{uf_sigla}{self.ano_mes}.dbc"
        try:
            dbc_path = self._baixar_dbc(filename)
            df = self._dbc_para_dataframe(dbc_path)
            os.remove(dbc_path)
            logger.info(f"  {uf_sigla}: {len(df)} registros")
            return df
        except Exception as e:
            logger.error(f"  {uf_sigla}: ERRO - {e}")
            return None

    def extract(self, row: dict) -> pd.DataFrame:
        config = row.get("config")
        if config and isinstance(config, dict):
            self.ftp_host = config.get("ftp_host", self.ftp_host)
            self.ftp_base = config.get("ftp_base", self.ftp_base)
            self.theme = config.get("theme", self.theme)
            self.ano_mes = config.get("ano_mes", self.ano_mes)
            self.ufs = config.get("ufs", self.ufs)
            self.max_workers = int(config.get("max_workers", self.max_workers))
            self.encoding = config.get("encoding", self.encoding)

        # Suporte via colunas diretas da schedule
        url = row.get("url", "")
        if url and not config:
            self.ftp_host = url.replace("ftp://", "").split("/")[0]

        logger.info(
            f"FTP {self.theme} para {len(self.ufs)} UFs "
            f"(ano_mes={self.ano_mes}, workers={self.max_workers})..."
        )

        partes = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futuros = {
                executor.submit(self._processar_uf, uf): uf
                for uf in self.ufs
            }
            for futuro in as_completed(futuros):
                uf = futuros[futuro]
                try:
                    df = futuro.result()
                    if df is not None and len(df) > 0:
                        df["UF_SIGLA"] = uf
                        partes.append(df)
                except Exception as e:
                    logger.error(f"  !! {uf} falhou: {e}")

        if not partes:
            raise ValueError("Nenhum dado foi baixado do FTP")

        df_final = pd.concat(partes, ignore_index=True)
        logger.info(
            f"Total: {len(df_final)} registros, {len(df_final.columns)} colunas"
        )
        return df_final
