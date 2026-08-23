# Data Lab

JupyterLab notebooks para explorar e aprender conceitos de dados com o stack do ELT Lab.

## Como acessar

1. Suba o ambiente: `.\setup.ps1`
2. Abra http://localhost:8888
3. Use a senha gerada no arquivo `.env` (`JUPYTER_PASSWORD`)
4. Navegue ate a pasta `Data Lab` no JupyterLab

## Estrutura

```
Data Lab/
+-- datasets/                    # Datasets gerados pelos notebooks
+-- 00_Boas_Vindas_...ipynb      # Validacao do ambiente
+-- 01_Python_para_Dados.ipynb   # Python basico para dados
+-- 02_NumPy.ipynb               # Arrays e operacoes numericas
+-- 03_Pandas.ipynb              # DataFrames e manipulacao
+-- 04_Polars_e_DuckDB.ipynb     # Alternativas modernas ao Pandas
+-- 05_Arquivos_...ipynb         # CSV, Excel, Parquet
+-- 06_APIs_e_JSON.ipynb         # Consumo de APIs REST
+-- 07_SQLAlchemy_e_PostgreSQL.ipynb  # Conexao com PostgreSQL
+-- 08_Visualizacao_de_Dados.ipynb    # Matplotlib, Seaborn, Plotly
+-- 09_Scikit_Learn_Basico.ipynb      # ML supervisionado basico
+-- 10_PySpark_Fundamentos.ipynb      # PySpark do zero
+-- 11_PySpark_Parquet_e_Medalhao.ipynb  # Bronze/Silver/Gold com Spark
+-- 12_Desafios_de_Entrevista.ipynb   # Exercicios para entrevistas
```

## Notas

- Todos os notebooks funcionam **offline** (sem internet)
- Dados sao sinteticos e gerados dentro dos notebooks
- Nenhum dado real ou credencial e incluido
- O diretorio `ELT/` no JupyterLab e **somente leitura** (codigo-fonte do projeto)
- O diretorio `Data Lab/` e **gravavel** (para seus exercicios)
