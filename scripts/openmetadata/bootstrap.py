"""Populate OpenMetadata with the ELT lab catalog and governance metadata."""

from __future__ import annotations

import base64
import os
import time
import warnings
from typing import Any
from urllib.parse import quote

import psycopg2
import requests
from metadata.workflow.metadata import MetadataWorkflow
from sqlalchemy.exc import SAWarning

warnings.filterwarnings("ignore", category=SAWarning)


OPENMETADATA_URL = os.environ.get("OPENMETADATA_URL", "http://openmetadata-server:8585/api").rstrip(
    "/"
)
ADMIN_USERNAME = "admin@open-metadata.org"
POSTGRES_HOST = os.environ.get("ELT_POSTGRES_HOST", "elt-postgres")
POSTGRES_PORT = int(os.environ.get("ELT_POSTGRES_PORT", "5432"))


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


POSTGRES_USER = required_env("ELT_POSTGRES_USER")
POSTGRES_PASSWORD = required_env("ELT_POSTGRES_PASSWORD")


def login() -> str:
    password = base64.b64encode(required_env("OM_ADMIN_PASSWORD").encode("utf-8")).decode("ascii")
    response = requests.post(
        f"{OPENMETADATA_URL}/v1/users/login",
        json={"email": ADMIN_USERNAME, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["accessToken"]


TOKEN = login()
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {TOKEN}"})


def api(
    method: str,
    path: str,
    *,
    payload: Any | None = None,
    expected: tuple[int, ...] = (200, 201),
) -> Any:
    headers = {}
    if method == "PATCH":
        headers["Content-Type"] = "application/json-patch+json"
    response = SESSION.request(
        method,
        f"{OPENMETADATA_URL}{path}",
        json=payload,
        headers=headers,
        timeout=60,
    )
    if response.status_code not in expected:
        detail = response.text[:1000]
        raise RuntimeError(f"{method} {path} returned {response.status_code}: {detail}")
    return response.json() if response.content else None


def get_by_name(endpoint: str, name: str, fields: str | None = None) -> dict | None:
    path = f"/v1/{endpoint}/name/{quote(name, safe='')}"
    if fields:
        path += f"?fields={quote(fields, safe=',')}"
    response = SESSION.get(f"{OPENMETADATA_URL}{path}", timeout=30)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise RuntimeError(f"GET {path} returned {response.status_code}: {response.text[:1000]}")
    return response.json()


def ensure_entity(endpoint: str, name: str, payload: dict) -> dict:
    entity = get_by_name(endpoint, name)
    if entity:
        return entity
    print(f"Creating {endpoint}: {name}")
    return api("POST", f"/v1/{endpoint}", payload=payload)


def run_workflow(label: str, config: dict) -> None:
    print(f"Running ingestion: {label}")
    workflow = MetadataWorkflow.create(config)
    try:
        workflow.execute()
        workflow.print_status()
        workflow.raise_from_status()
    finally:
        workflow.stop()


def server_config() -> dict:
    return {
        "hostPort": OPENMETADATA_URL,
        "authProvider": "openmetadata",
        "securityConfig": {"jwtToken": TOKEN},
        "storeServiceConnection": True,
    }


def ingest_databases() -> None:
    for database in ("elt", "bronze", "silver", "gold"):
        service_name = f"elt_{'control' if database == 'elt' else database}"
        config = {
            "source": {
                "type": "postgres",
                "serviceName": service_name,
                "serviceConnection": {
                    "config": {
                        "type": "Postgres",
                        "hostPort": f"{POSTGRES_HOST}:{POSTGRES_PORT}",
                        "username": POSTGRES_USER,
                        "authType": {"password": POSTGRES_PASSWORD},
                        "database": database,
                        "schemaFilterPattern": {"includes": ["^global$"]},
                    }
                },
                "sourceConfig": {
                    "config": {
                        "type": "DatabaseMetadata",
                        "markDeletedTables": True,
                        "includeTables": True,
                        "includeViews": True,
                        "overrideMetadata": False,
                    }
                },
            },
            "sink": {"type": "metadata-rest", "config": {}},
            "workflowConfig": {
                "loggerLevel": "ERROR",
                "openMetadataServerConfig": server_config(),
            },
        }
        run_workflow(service_name, config)


def ingest_airflow() -> None:
    config = {
        "source": {
            "type": "airflow",
            "serviceName": "elt_airflow",
            "serviceConnection": {
                "config": {
                    "type": "Airflow",
                    "hostPort": os.environ.get(
                        "ELT_AIRFLOW_URL", "http://elt-airflow-webserver:8080"
                    ),
                    "numberOfStatus": 10,
                    "connection": {
                        "type": "Postgres",
                        "hostPort": f"{POSTGRES_HOST}:{POSTGRES_PORT}",
                        "username": POSTGRES_USER,
                        "authType": {"password": POSTGRES_PASSWORD},
                        "database": "airflow",
                    },
                }
            },
            "sourceConfig": {
                "config": {
                    "type": "PipelineMetadata",
                    "includeLineage": True,
                    "includeOwners": True,
                    "includeUnDeployedPipelines": True,
                    "lineageInformation": {
                        "dbServiceNames": [
                            "elt_control",
                            "elt_bronze",
                            "elt_silver",
                            "elt_gold",
                        ]
                    },
                }
            },
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "ERROR",
            "openMetadataServerConfig": server_config(),
        },
    }
    run_workflow("elt_airflow", config)


def ensure_governance_entities() -> dict[str, dict]:
    teams = {}
    for name, display_name, description in (
        ("DataOwners", "Data Owners", "Responsaveis pelos produtos e regras de dados."),
        ("DataStewards", "Data Stewards", "Responsaveis pelo catalogo e glossario."),
        ("DataEngineers", "Data Engineers", "Responsaveis pelos pipelines ELT."),
    ):
        teams[name] = ensure_entity(
            "teams",
            name,
            {
                "name": name,
                "displayName": display_name,
                "description": description,
                "teamType": "Group",
            },
        )

    ensure_entity(
        "classifications",
        "DataSensitivity",
        {
            "name": "DataSensitivity",
            "displayName": "Sensibilidade dos Dados",
            "description": "Classificacao demonstrativa por nivel de sensibilidade.",
        },
    )
    tag_descriptions = {
        "Public": "Dados publicos sem restricao de acesso.",
        "Internal": "Dados destinados ao uso interno.",
        "Sensitive": "Dados que exigem controles adicionais.",
        "Confidential": "Dados restritos a pessoas autorizadas.",
        "PII": "Dados pessoais identificaveis; aplicar somente quando houver PII real.",
    }
    for name, description in tag_descriptions.items():
        ensure_entity(
            "tags",
            f"DataSensitivity.{name}",
            {
                "name": name,
                "classification": "DataSensitivity",
                "description": description,
            },
        )

    glossary = ensure_entity(
        "glossaries",
        "ELTGlossary",
        {
            "name": "ELTGlossary",
            "displayName": "Glossario do ELT Lab",
            "description": "Conceitos de negocio e das camadas do pipeline demonstrativo.",
            "owners": [{"id": teams["DataStewards"]["id"], "type": "team"}],
        },
    )
    terms = {
        "Municipio": "Unidade politico-administrativa local do Brasil.",
        "UnidadeFederativa": "Estado ou Distrito Federal identificado pela sigla UF.",
        "QuantidadeMunicipios": "Contagem de municipios agrupada por unidade federativa.",
        "CamadaBronze": "Dados brutos preservados como recebidos da fonte.",
        "CamadaSilver": "Dados limpos, padronizados e filtrados para analise.",
        "CamadaGold": "Dados agregados e prontos para consumo analitico.",
    }
    for name, description in terms.items():
        ensure_entity(
            "glossaryTerms",
            f"ELTGlossary.{name}",
            {
                "name": name,
                "glossary": glossary["fullyQualifiedName"],
                "description": description,
                "owners": [{"id": teams["DataStewards"]["id"], "type": "team"}],
            },
        )
    return teams


TABLES = {
    "bronze": "elt_bronze.bronze.global.tb_municipios_ibge",
    "silver": "elt_silver.silver.global.tb_municipios_nf",
    "gold": "elt_gold.gold.global.dm_municipios_por_uf",
    "schedule": "elt_control.elt.global.schedule",
    "execution": "elt_control.elt.global.controle_execucao",
}


TABLE_METADATA = {
    "bronze": {
        "description": (
            "Dados brutos de municipios brasileiros obtidos do CSV publico do projeto "
            "Municipios-Brasileiros. Fonte do pipeline demonstrativo."
        ),
        "owner": "DataEngineers",
        "tags": ["DataSensitivity.Public", "ELTGlossary.CamadaBronze", "ELTGlossary.Municipio"],
        "columns": {
            "codigo_ibge": "Codigo oficial do municipio no IBGE.",
            "nome": "Nome oficial do municipio.",
            "latitude": "Latitude aproximada da sede municipal.",
            "longitude": "Longitude aproximada da sede municipal.",
            "capital": "Indicador de capital estadual.",
            "codigo_uf": "Codigo numerico da unidade federativa.",
            "siafi_id": "Codigo do municipio no SIAFI.",
            "ddd": "Codigo de discagem direta a distancia.",
            "fuso_horario": "Fuso horario IANA do municipio.",
        },
    },
    "silver": {
        "description": (
            "Municipios da regiao Nordeste filtrados e enriquecidos com sigla e nome "
            "da unidade federativa."
        ),
        "owner": "DataEngineers",
        "tags": [
            "DataSensitivity.Public",
            "ELTGlossary.CamadaSilver",
            "ELTGlossary.Municipio",
            "ELTGlossary.UnidadeFederativa",
        ],
        "columns": {
            "codigo_ibge": "Codigo oficial do municipio no IBGE.",
            "nome": "Nome oficial do municipio.",
            "codigo_uf": "Codigo numerico da unidade federativa.",
            "uf": "Sigla de duas letras da unidade federativa.",
            "estado": "Nome da unidade federativa.",
            "latitude": "Latitude aproximada da sede municipal.",
            "longitude": "Longitude aproximada da sede municipal.",
            "codigo_siafi": "Codigo do municipio no SIAFI.",
            "ddd": "Codigo de discagem direta a distancia.",
            "fuso_horario": "Fuso horario IANA do municipio.",
        },
    },
    "gold": {
        "description": "Agregacao analitica da quantidade de municipios por UF do Nordeste.",
        "owner": "DataOwners",
        "tags": [
            "DataSensitivity.Public",
            "ELTGlossary.CamadaGold",
            "ELTGlossary.QuantidadeMunicipios",
            "ELTGlossary.UnidadeFederativa",
        ],
        "columns": {
            "uf": "Sigla de duas letras da unidade federativa.",
            "estado": "Nome da unidade federativa.",
            "total_municipios": "Quantidade de municipios da unidade federativa.",
        },
    },
    "schedule": {
        "description": "Configuracao interna dos jobs executados pelo framework ELT.",
        "owner": "DataEngineers",
        "tags": ["DataSensitivity.Internal", "DataSensitivity.Sensitive"],
        "columns": {},
    },
    "execution": {
        "description": "Historico tecnico de execucoes, status e erros dos jobs ELT.",
        "owner": "DataEngineers",
        "tags": ["DataSensitivity.Internal", "DataSensitivity.Confidential"],
        "columns": {},
    },
}


def tag_label(tag_fqn: str) -> dict:
    return {
        "tagFQN": tag_fqn,
        "source": "Glossary" if tag_fqn.startswith("ELTGlossary.") else "Classification",
        "labelType": "Manual",
        "state": "Confirmed",
    }


def apply_table_metadata(teams: dict[str, dict]) -> dict[str, dict]:
    tables = {}
    for key, fqn in TABLES.items():
        table = get_by_name("tables", fqn, "columns,owners,tags")
        if not table:
            raise RuntimeError(f"Catalog table not found after ingestion: {fqn}")
        metadata = TABLE_METADATA[key]
        current_tags = {tag["tagFQN"]: tag for tag in table.get("tags") or []}
        for tag in metadata["tags"]:
            current_tags[tag] = tag_label(tag)
        operations = [
            {"op": "add", "path": "/description", "value": metadata["description"]},
            {
                "op": "add",
                "path": "/owners",
                "value": [{"id": teams[metadata["owner"]]["id"], "type": "team"}],
            },
            {"op": "add", "path": "/tags", "value": list(current_tags.values())},
        ]
        for index, column in enumerate(table.get("columns") or []):
            description = metadata["columns"].get(column["name"])
            if description:
                operations.append(
                    {
                        "op": "add",
                        "path": f"/columns/{index}/description",
                        "value": description,
                    }
                )
        print(f"Updating table governance: {fqn}")
        api(
            "PATCH",
            f"/v1/tables/{table['id']}?changeSource=Manual",
            payload=operations,
        )
        tables[key] = get_by_name("tables", fqn, "columns,owners,tags")
    return tables


def column_fqn(table_key: str, column: str) -> str:
    return f"{TABLES[table_key]}.{column}"


def add_lineage(
    source: dict,
    destination: dict,
    query: str,
    columns: list[tuple[list[str], str, str | None]],
    pipeline: dict | None,
) -> None:
    details: dict[str, Any] = {
        "sqlQuery": query,
        "source": "PipelineLineage" if pipeline else "Manual",
        "description": "Lineage real do pipeline municipios_ibge.",
        "columnsLineage": [
            {
                "fromColumns": from_columns,
                "toColumn": to_column,
                **({"function": function} if function else {}),
            }
            for from_columns, to_column, function in columns
        ],
    }
    if pipeline:
        details["pipeline"] = {"id": pipeline["id"], "type": "pipeline"}
    api(
        "PUT",
        "/v1/lineage",
        payload={
            "edge": {
                "fromEntity": {"id": source["id"], "type": "table"},
                "toEntity": {"id": destination["id"], "type": "table"},
                "lineageDetails": details,
            }
        },
    )


def configure_lineage(tables: dict[str, dict]) -> None:
    pipeline = get_by_name("pipelines", "elt_airflow.elt_municipios_ibge")
    direct_columns = [
        "codigo_ibge",
        "nome",
        "codigo_uf",
        "latitude",
        "longitude",
        "ddd",
        "fuso_horario",
    ]
    bronze_to_silver = [
        ([column_fqn("bronze", name)], column_fqn("silver", name), None) for name in direct_columns
    ]
    bronze_to_silver.extend(
        [
            ([column_fqn("bronze", "codigo_uf")], column_fqn("silver", "uf"), "CASE codigo_uf"),
            ([column_fqn("bronze", "codigo_uf")], column_fqn("silver", "estado"), "CASE codigo_uf"),
            ([column_fqn("bronze", "siafi_id")], column_fqn("silver", "codigo_siafi"), "rename"),
        ]
    )
    add_lineage(
        tables["bronze"],
        tables["silver"],
        "SELECT ... FROM global.tb_municipios_ibge WHERE codigo_uf IN (21..29)",
        bronze_to_silver,
        pipeline,
    )
    add_lineage(
        tables["silver"],
        tables["gold"],
        (
            "SELECT uf, estado, COUNT(*) AS total_municipios "
            "FROM global.tb_municipios_nf GROUP BY uf, estado"
        ),
        [
            ([column_fqn("silver", "uf")], column_fqn("gold", "uf"), None),
            ([column_fqn("silver", "estado")], column_fqn("gold", "estado"), None),
            (
                [column_fqn("silver", "codigo_ibge")],
                column_fqn("gold", "total_municipios"),
                "COUNT(*)",
            ),
        ],
        pipeline,
    )


def scalar(database: str, sql: str) -> int:
    with (
        psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=database,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(sql)
        return int(cursor.fetchone()[0])


def ensure_test_case(payload: dict) -> dict:
    existing = api(
        "GET",
        "/v1/dataQuality/testCases?limit=100&fields=testDefinition",
    ).get("data", [])
    for test_case in existing:
        if test_case.get("name") == payload["name"]:
            return test_case
    print(f"Creating quality test: {payload['name']}")
    return api("POST", "/v1/dataQuality/testCases", payload=payload)


def publish_test_result(test_case: dict, actual: int, minimum: int, maximum: int) -> None:
    success = minimum <= actual <= maximum
    test_fqn = test_case["fullyQualifiedName"]
    api(
        "POST",
        f"/v1/dataQuality/testCases/testCaseResults/{quote(test_fqn, safe='')}",
        payload={
            "timestamp": int(time.time() * 1000),
            "testCaseStatus": "Success" if success else "Failed",
            "result": f"Observed row count {actual}; expected between {minimum} and {maximum}.",
            "testResultValue": [
                {
                    "name": "rowCount",
                    "value": str(actual),
                    "predictedValue": f"{minimum}..{maximum}",
                }
            ],
            "minBound": minimum,
            "maxBound": maximum,
        },
    )
    if not success:
        raise RuntimeError(f"Quality test failed for {test_fqn}: row count {actual}")


def configure_quality() -> None:
    checks = (
        ("bronze_municipios_row_count", "bronze", "bronze", 5500, 6000),
        ("silver_nordeste_row_count", "silver", "silver", 1700, 1900),
        ("gold_ufs_row_count", "gold", "gold", 9, 9),
    )
    for name, table_key, database, minimum, maximum in checks:
        test_case = ensure_test_case(
            {
                "name": name,
                "description": "Valida o volume esperado em cada camada do pipeline demonstrativo.",
                "testDefinition": "tableRowCountToBeBetween",
                "entityLink": f"<#E::table::{TABLES[table_key]}>",
                "parameterValues": [
                    {"name": "minValue", "value": str(minimum)},
                    {"name": "maxValue", "value": str(maximum)},
                ],
            }
        )
        table_name = TABLES[table_key].rsplit(".", 1)[1]
        actual = scalar(database, f"SELECT COUNT(*) FROM global.{table_name}")
        publish_test_result(test_case, actual, minimum, maximum)


def main() -> None:
    ingest_databases()
    ingest_airflow()
    teams = ensure_governance_entities()
    tables = apply_table_metadata(teams)
    configure_lineage(tables)
    configure_quality()
    print("OpenMetadata bootstrap completed successfully")


if __name__ == "__main__":
    main()
