"""
SCD Tipo 2 - Controle historico de registros.

Uso:
    from elt.src.historics.history import HistoricoRegistros

    config = {
        "staging_table": "contratos",
        "main_table": "main_contratos",
        "log_table": "log_registros",
        "unique_key": ["n do instrumento", "sei dos instrumentos contratuais"],
        "key_treatments": {
            "sei dos instrumentos contratuais": "remove_ponto_inicial_upper",
        },
    }

    historico = HistoricoRegistros(postgres, schema, config)
    output = historico.sincronizar()
"""

import hashlib
import json
import logging

import pandas as pd

logger = logging.getLogger(__name__)


class HistoricoRegistros:
    def __init__(self, postgres, schema: str, config: dict):
        self.postgres = postgres
        self.schema = schema
        self.config = config

        self.staging_table = config["staging_table"]
        self.main_table = config["main_table"]
        self.log_table = config.get("log_table", "log_registros")
        self.unique_key = config["unique_key"]
        self.key_treatments = config.get("key_treatments", {})

    def sincronizar(self) -> dict:
        logger.info(
            f"Sincronizando {self.schema}.{self.staging_table} "
            f"\u2192 {self.schema}.{self.main_table}"
        )

        self._criar_tabelas_historico()
        self._garantir_unique_chave_unica()

        df_fonte = self.postgres.read_table(
            self.staging_table,
            self.schema,
        )

        if df_fonte.empty:
            logger.warning(
                f"Tabela {self.schema}.{self.staging_table} vazia. "
                "Nada a sincronizar."
            )
            return self._resultado_vazio()

        df_fonte = self._preparar_dataframe_fonte(df_fonte)
        df_main = self._ler_main_table()

        if df_main.empty:
            return self._primeira_carga(df_fonte)

        return self._sincronizacao_incremental(df_fonte, df_main)

    def _resultado_vazio(self) -> dict:
        return {
            "inseridos": 0,
            "alterados": 0,
            "excluidos": 0,
            "inalterados": 0,
        }

    def _quote_ident(self, nome: str) -> str:
        return '"' + nome.replace('"', '""') + '"'

    def _normalizar_valor_chave(self, valor):
        if pd.isna(valor):
            return None
        valor = str(valor).strip()
        if valor == "" or valor == "-":
            return None
        return valor

    def _aplicar_tratamento_especifico(self, coluna: str, valor):
        if valor is None:
            return None
        tratamento = self.key_treatments.get(coluna)
        if tratamento == "remove_ponto_inicial_upper":
            valor = valor.upper()
            if valor.startswith("."):
                valor = valor[1:]
            return valor
        return valor

    def _gerar_chave_unica_linha(self, linha: pd.Series) -> str:
        valores = []
        for coluna in self.unique_key:
            valor = linha[coluna]
            valor = self._normalizar_valor_chave(valor)
            valor = self._aplicar_tratamento_especifico(coluna, valor)
            if valor is not None:
                valores.append(str(valor))
        return "|".join(valores)

    def _calcular_hash_linha(self, linha: pd.Series) -> str:
        valores = "|".join(
            str(v).strip() if pd.notna(v) else ""
            for v in linha.values
        )
        return hashlib.md5(valores.encode("utf-8")).hexdigest()

    def _preparar_dataframe_fonte(self, df_fonte: pd.DataFrame) -> pd.DataFrame:
        df_fonte = df_fonte.copy()
        df_fonte["chave_unica"] = df_fonte.apply(
            self._gerar_chave_unica_linha, axis=1
        )
        colunas_dados = [
            col for col in df_fonte.columns
            if col != "chave_unica"
        ]
        df_fonte["hash_registro"] = df_fonte[colunas_dados].apply(
            self._calcular_hash_linha, axis=1
        )
        return df_fonte

    def _ler_main_table(self) -> pd.DataFrame:
        try:
            return self.postgres.read_table(
                self.main_table, self.schema
            )
        except Exception as e:
            logger.warning(
                f"Nao foi possivel ler {self.schema}.{self.main_table}. "
                f"Sera considerada primeira carga. Erro: {e}"
            )
            return pd.DataFrame()

    def _criar_tabelas_historico(self):
        query_cols = f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = '{self.schema}'
              AND table_name = '{self.staging_table}'
            ORDER BY ordinal_position
        """
        try:
            df_cols = pd.read_sql(query_cols, self.postgres.engine)
        except Exception as e:
            logger.exception(
                f"Erro ao consultar metadados da tabela "
                f"{self.schema}.{self.staging_table}"
            )
            raise e

        if df_cols.empty:
            raise ValueError(
                f"Tabela {self.schema}.{self.staging_table} "
                "nao encontrada no banco."
            )

        colunas_dados = []
        for _, row in df_cols.iterrows():
            col_name = row["column_name"]
            col_type = row["data_type"]
            nullable = "" if row["is_nullable"] == "YES" else "NOT NULL"
            default = (
                f"DEFAULT {row['column_default']}"
                if row["column_default"]
                else ""
            )
            colunas_dados.append(
                f"{self._quote_ident(col_name)} {col_type} {nullable} {default}"
            )
        cols_sql = ",\n    ".join(colunas_dados)

        self.postgres.execute_script(
            f"""
            CREATE TABLE IF NOT EXISTS {self._quote_ident(self.schema)}.{self._quote_ident(self.main_table)} (
                sk SERIAL PRIMARY KEY,
                chave_unica TEXT NOT NULL UNIQUE,
                hash_registro TEXT NOT NULL,
                dt_criacao TIMESTAMP NOT NULL,
                dt_alteracao TIMESTAMP,
                status_registro TEXT NOT NULL DEFAULT 'inserido',
                {cols_sql}
            );
            """,
            message=f"Tabela {self.schema}.{self.main_table} criada/verificada",
        )

        self.postgres.execute_script(
            f"""
            CREATE TABLE IF NOT EXISTS {self._quote_ident(self.schema)}.{self._quote_ident(self.log_table)} (
                sk SERIAL PRIMARY KEY,
                dt_log TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                nome_tabela TEXT NOT NULL,
                sk_main INT NOT NULL,
                sk_log INT NOT NULL,
                chave_unica TEXT NOT NULL,
                status_registro TEXT,
                hash_registro TEXT,
                registro JSONB NOT NULL
            );
            """,
            message=f"Tabela {self.schema}.{self.log_table} criada/verificada",
        )

        self._criar_indices_log()

    def _criar_indices_log(self):
        self.postgres.execute_script(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.log_table}_nome_tabela_sk_main
            ON {self._quote_ident(self.schema)}.{self._quote_ident(self.log_table)}
            (nome_tabela, sk_main);
            """
        )
        self.postgres.execute_script(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.log_table}_chave_unica
            ON {self._quote_ident(self.schema)}.{self._quote_ident(self.log_table)}
            (chave_unica);
            """
        )
        self.postgres.execute_script(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.log_table}_registro_gin
            ON {self._quote_ident(self.schema)}.{self._quote_ident(self.log_table)}
            USING GIN (registro);
            """
        )

    def _garantir_unique_chave_unica(self):
        index_name = f"idx_{self.main_table}_chave_unica_unique"
        self.postgres.execute_script(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {self._quote_ident(index_name)}
            ON {self._quote_ident(self.schema)}.{self._quote_ident(self.main_table)} (chave_unica);
            """,
            message=f"Indice unique em {self.schema}.{self.main_table}.chave_unica criado/verificado",
        )

    def _primeira_carga(self, df_fonte: pd.DataFrame) -> dict:
        agora = pd.Timestamp.now()
        df_main_novo = df_fonte.copy()
        df_main_novo["dt_criacao"] = agora
        df_main_novo["dt_alteracao"] = None
        df_main_novo["status_registro"] = "inserido"
        self._upsert_main(df_main_novo)
        return {
            "inseridos": len(df_main_novo),
            "alterados": 0,
            "excluidos": 0,
            "inalterados": 0,
        }

    def _sincronizacao_incremental(
        self,
        df_fonte: pd.DataFrame,
        df_main: pd.DataFrame,
    ) -> dict:
        resultados = self._resultado_vazio()
        df_main_ativos = df_main[
            df_main["status_registro"] != "excluido"
        ].copy()

        chaves_fonte = set(df_fonte["chave_unica"])
        chaves_main = set(df_main_ativos["chave_unica"])

        chaves_novas = chaves_fonte - chaves_main
        chaves_excluidas = chaves_main - chaves_fonte
        chaves_comuns = chaves_fonte & chaves_main

        self._inserir_novos(df_fonte, chaves_novas, resultados)
        self._marcar_excluidos(
            df_main=df_main_ativos,
            chaves_excluidas=chaves_excluidas,
            resultados=resultados,
        )
        self._processar_alterados_e_inalterados(
            df_fonte=df_fonte,
            df_main=df_main_ativos,
            chaves_comuns=chaves_comuns,
            resultados=resultados,
        )

        logger.info(f"Sincronizacao concluida: {resultados}")
        return resultados

    def _inserir_novos(
        self,
        df_fonte: pd.DataFrame,
        chaves_novas: set,
        resultados: dict,
    ):
        if not chaves_novas:
            return
        agora = pd.Timestamp.now()
        df_novos = df_fonte[
            df_fonte["chave_unica"].isin(chaves_novas)
        ].copy()
        df_novos["dt_criacao"] = agora
        df_novos["dt_alteracao"] = None
        df_novos["status_registro"] = "inserido"
        self._upsert_main(df_novos)
        resultados["inseridos"] = len(df_novos)
        logger.info(f"Novos: {len(df_novos)}")

    def _marcar_excluidos(
        self,
        df_main: pd.DataFrame,
        chaves_excluidas: set,
        resultados: dict,
    ):
        if not chaves_excluidas:
            return
        df_excluidos = df_main[
            (df_main["chave_unica"].isin(chaves_excluidas))
            & (df_main["status_registro"] != "excluido")
        ].copy()
        if df_excluidos.empty:
            return
        df_excluidos = df_excluidos.set_index("chave_unica")
        self._registrar_log(
            df_comum_main=df_excluidos,
            chaves_alteradas=set(df_excluidos.index),
        )
        for chave in df_excluidos.index:
            self.postgres.execute_script(
                query=f"""
                    UPDATE {self._quote_ident(self.schema)}.{self._quote_ident(self.main_table)}
                    SET status_registro = 'excluido',
                        dt_alteracao = :dt_alteracao
                    WHERE chave_unica = :chave
                      AND status_registro <> 'excluido'
                """,
                params={
                    'chave': chave,
                    'dt_alteracao': pd.Timestamp.now()
                },
            )
        resultados["excluidos"] = len(df_excluidos)
        logger.info(f"Excluidos: {len(df_excluidos)}")

    def _processar_alterados_e_inalterados(
        self,
        df_fonte: pd.DataFrame,
        df_main: pd.DataFrame,
        chaves_comuns: set,
        resultados: dict,
    ):
        if not chaves_comuns:
            return
        df_comum_fonte = df_fonte[
            df_fonte["chave_unica"].isin(chaves_comuns)
        ].copy()
        df_comum_main = df_main[
            df_main["chave_unica"].isin(chaves_comuns)
        ].copy()
        df_comparacao = df_comum_fonte[
            ["chave_unica", "hash_registro"]
        ].merge(
            df_comum_main[["chave_unica", "hash_registro"]],
            on="chave_unica",
            how="inner",
            suffixes=("_fonte", "_main"),
        )
        df_alterados = df_comparacao[
            df_comparacao["hash_registro_fonte"]
            != df_comparacao["hash_registro_main"]
        ]
        chaves_alteradas = set(df_alterados["chave_unica"])
        chaves_inalteradas = chaves_comuns - chaves_alteradas
        resultados["inalterados"] = len(chaves_inalteradas)
        if not chaves_alteradas:
            return
        df_comum_fonte = df_comum_fonte.set_index("chave_unica")
        df_comum_main = df_comum_main.set_index("chave_unica")
        self._registrar_log(
            df_comum_main=df_comum_main,
            chaves_alteradas=chaves_alteradas,
        )
        self._atualizar_alterados_na_main(
            df_comum_fonte=df_comum_fonte,
            df_comum_main=df_comum_main,
            chaves_alteradas=chaves_alteradas,
        )
        resultados["alterados"] = len(chaves_alteradas)
        logger.info(f"Alterados: {len(chaves_alteradas)}")

    def _serializar_registro(self, registro: dict) -> str:
        registro_limpo = {}
        for chave, valor in registro.items():
            if pd.isna(valor):
                registro_limpo[chave] = None
            elif isinstance(valor, pd.Timestamp):
                registro_limpo[chave] = valor.isoformat()
            else:
                registro_limpo[chave] = valor
        return json.dumps(registro_limpo, ensure_ascii=False, default=str)

    def _registrar_log(self, df_comum_main, chaves_alteradas: set):
        agora = pd.Timestamp.now()
        df_base_log = df_comum_main.loc[
            df_comum_main.index.isin(chaves_alteradas)
        ].reset_index()
        if df_base_log.empty:
            return
        registros_log = []
        for _, row in df_base_log.iterrows():
            registro = row.to_dict()
            if "sk" not in registro:
                raise ValueError(
                    f"Coluna sk nao encontrada em {self.main_table}"
                )
            sk_main = int(registro["sk"])
            chave_unica = registro.get("chave_unica")
            status_registro = registro.get("status_registro")
            hash_registro = registro.get("hash_registro")

            query_sk_log = f"""
                SELECT COALESCE(MAX(sk_log) + 1, 1) AS proximo_sk_log
                FROM {self._quote_ident(self.schema)}.{self._quote_ident(self.log_table)}
                WHERE nome_tabela = %(nome_tabela)s
                  AND sk_main = %(sk_main)s
            """
            df_sk_log = pd.read_sql(
                query_sk_log,
                self.postgres.engine,
                params={
                    "nome_tabela": self.main_table,
                    "sk_main": sk_main,
                },
            )
            sk_log = int(df_sk_log.loc[0, "proximo_sk_log"])
            registros_log.append({
                "dt_log": agora,
                "nome_tabela": self.main_table,
                "sk_main": sk_main,
                "sk_log": sk_log,
                "chave_unica": chave_unica,
                "status_registro": status_registro,
                "hash_registro": hash_registro,
                "registro": self._serializar_registro(registro),
            })
        df_log = pd.DataFrame(registros_log)
        self.postgres.write_dataframe(
            df_log, self.log_table, self.schema, "append"
        )

    def _atualizar_alterados_na_main(
        self,
        df_comum_fonte, df_comum_main, chaves_alteradas: set
    ):
        if not chaves_alteradas:
            return
        agora = pd.Timestamp.now()
        df_alterados = df_comum_fonte.loc[
            df_comum_fonte.index.isin(chaves_alteradas)
        ].copy()
        df_alterados = df_alterados.reset_index()
        df_alterados["dt_criacao"] = (
            df_comum_main.loc[
                df_alterados["chave_unica"], "dt_criacao"
            ].values
        )
        df_alterados["dt_alteracao"] = agora
        df_alterados["status_registro"] = "alterado"
        self._upsert_main(df_alterados)

    def _upsert_main(self, df: pd.DataFrame):
        if df.empty:
            return
        df = df.copy()
        colunas_ignoradas_insert = ["sk"]
        colunas_ignoradas_update = ["sk", "chave_unica", "dt_criacao"]
        colunas_insert = [
            col for col in df.columns
            if col not in colunas_ignoradas_insert
        ]
        colunas_update = [
            col for col in colunas_insert
            if col not in colunas_ignoradas_update
        ]
        colunas_insert_sql = ", ".join(
            self._quote_ident(col) for col in colunas_insert
        )
        placeholders_sql = ", ".join(
            f":p{i}" for i in range(len(colunas_insert))
        )
        update_sql = ", ".join(
            f"{self._quote_ident(col)} = EXCLUDED.{self._quote_ident(col)}"
            for col in colunas_update
        )
        query = f"""
            INSERT INTO {self._quote_ident(self.schema)}.{self._quote_ident(self.main_table)} (
                {colunas_insert_sql}
            )
            VALUES (
                {placeholders_sql}
            )
            ON CONFLICT (chave_unica)
            DO UPDATE SET
                {update_sql}
        """
        for _, row in df.iterrows():
            params = {f"p{i}": row[col] for i, col in enumerate(colunas_insert)}
            self.postgres.execute_script(query=query, params=params)
