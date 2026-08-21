-- ============================================================
-- Cria os bancos de dados do ELT + Airflow
-- Executado automaticamente pelo Docker na primeira inicializacao
-- ============================================================

CREATE DATABASE bronze;
CREATE DATABASE silver;
CREATE DATABASE gold;
CREATE DATABASE elt;
CREATE DATABASE airflow;
