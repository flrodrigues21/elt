import datetime
import logging
import os
import traceback

from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.providers.smtp.operators.smtp import EmailOperator


def enviar_relatorio(texto_relatorio, variavel_email, modo, context):
    task_instance = context.get('task_instance')
    dag_id = context.get('dag').dag_id
    task_id = context.get('task').task_id
    execution_date = datetime.datetime.now()
    log_url = task_instance.log_url
    airflow_host = os.environ.get('AIRFLOW_WEBSERVER_HOST', 'localhost')
    log_url = log_url.replace('localhost', airflow_host)

    exc = context.get('exception')
    if exc:
        exception_message = ''.join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    else:
        exception_message = traceback.format_exc()

    if modo == 1:
        html_body = f"""
        <html>
            <head>
                <title>Relatorio de Execucao</title>
                <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; background-color: #f9f9f9; color: #333; }}
                    .container {{ background-color: #fff; padding: 30px; border-radius: 8px;
                                  margin: 50px auto; width: 80%; max-width: 800px; }}
                    h1 {{ color: #e74c3c; font-size: 2rem; }}
                    .error-message {{ background-color: #f4f4f4; padding: 10px; border-radius: 5px;
                                      white-space: pre-wrap; font-family: monospace; color: #e74c3c; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Relatorio de execucao</h1>
                    <p>Referencia: {execution_date}</p>
                    <p>DAG: {dag_id}</p>
                    <pre class="error-message">{texto_relatorio}</pre>
                    <p><a href="{log_url}">Logs da tarefa</a></p>
                </div>
            </body>
        </html>
        """
        subject = f"[Airflow] Relatorio da DAG: {dag_id}"
    else:
        html_body = f"""
        <html>
            <head>
                <title>Erro na Execucao</title>
                <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; background-color: #f9f9f9; color: #333; }}
                    .container {{ background-color: #fff; padding: 30px; border-radius: 8px;
                                  margin: 50px auto; width: 80%; max-width: 800px; }}
                    h1 {{ color: #e74c3c; }}
                    .error-message {{ background-color: #f4f4f4; padding: 10px; border-radius: 5px;
                                      white-space: pre-wrap; font-family: monospace; color: #e74c3c; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Erro na Execucao da DAG</h1>
                    <p>Referencia: {execution_date}</p>
                    <p>DAG: {dag_id}</p>
                    <p>Tarefa: {task_id}</p>
                    <pre class="error-message">{exception_message}</pre>
                    <p><a href="{log_url}">Logs da tarefa</a></p>
                </div>
            </body>
        </html>
        """
        subject = f"[Airflow] Erro: {dag_id} - {task_id}"

    email_list = Variable.get(
        variavel_email, default_var='[]', deserialize_json=True
    )

    try:
        email = EmailOperator(
            task_id='enviar_email',
            to=email_list,
            subject=subject,
            html_content=html_body,
            conn_id="smtp_default",
        )
        email.execute(context=context)
        logging.info("Email enviado com sucesso")
    except Exception as e:
        logging.error(f"Erro ao enviar email: {e}")
