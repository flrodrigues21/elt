"""
DAG Airflow generica para o framework ELT.

Gera dinamicamente uma DAG por projeto com base na coluna schedule_cron
da tabela global.schedule.

Funcionamento:
  1. Le a tabela schedule e agrupa steps por projeto
  2. Para cada projeto com schedule_cron preenchido, cria uma DAG
  3. Cada DAG executa bronze -> silver -> gold apenas para aquele projeto
  4. A DAG elt_pipeline (geral) continua existindo para execucao manual
     ou para projetos sem schedule_cron
"""

from datetime import datetime, timedelta
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator

from elt.controller.dags import enviar_relatorio
from elt.controller.load_bronze import load_bronze
from elt.controller.load_silver import load_silver
from elt.controller.load_gold import load_gold
from elt.src.schedule.schedule_table import load_schedule_table

task_logger = logging.getLogger("airflow.task")

default_args = {
    'owner': 'elt',
    'retries': 1,
    'retry_delay': timedelta(seconds=30),
    'on_failure_callback': lambda context: enviar_relatorio(
        texto_relatorio="Erro na execucao da DAG ELT.",
        variavel_email='emails_alerta',
        modo=2,
        context=context
    )
}


def _build_dag(dag_id: str, schedule: str, projeto: str | None = None):
    """Monta uma DAG com os steps de bronze, silver e gold."""

    with DAG(
        dag_id=dag_id,
        description=f"Pipeline ELT - {projeto or 'todos os projetos'}",
        default_args=default_args,
        schedule=schedule,
        catchup=False,
        max_active_runs=1,
        tags=["dados", "elt", projeto] if projeto else ["dados", "elt"],
    ) as dag:

        task_load_bronze = PythonOperator(
            task_id="load_bronze",
            python_callable=load_bronze,
            op_kwargs={"projeto": projeto},
        )

        task_load_silver = PythonOperator(
            task_id="load_silver",
            python_callable=load_silver,
            op_kwargs={"projeto": projeto},
        )

        task_load_gold = PythonOperator(
            task_id="load_gold",
            python_callable=load_gold,
            op_kwargs={"projeto": projeto},
        )

        task_load_bronze >> task_load_silver >> task_load_gold

    return dag


# ============================================================
# DAG GERAL (elt_pipeline) - executa todos os projetos
# ============================================================
_build_dag(
    dag_id="elt_pipeline",
    schedule='45 8 * * 1-5',
    projeto=None,
)

# ============================================================
# DAGs DINAMICAS - uma por projeto com schedule_cron preenchido
# ============================================================
try:
    df_schedule = load_schedule_table()
    projetos = (
        df_schedule[df_schedule['schedule_cron'].notna()]
        .groupby('projeto')['schedule_cron']
        .first()
        .to_dict()
    )

    for projeto, cron in projetos.items():
        dag_id = f"elt_{projeto}"
        _build_dag(dag_id=dag_id, schedule=cron, projeto=projeto)
        task_logger.info(f"DAG {dag_id} criada com schedule {cron}")

except Exception as e:
    task_logger.warning(f"Nao foi possivel gerar DAGs dinamicas: {e}")
