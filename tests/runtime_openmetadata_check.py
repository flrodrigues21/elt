"""Validate the running OpenMetadata lab through its API.

Run this inside the OpenMetadata ingestion image after the bootstrap.
"""

from __future__ import annotations

import base64
import json
import os
import time
from urllib.parse import quote

import requests

BASE_URL = os.environ.get("OPENMETADATA_URL", "http://openmetadata-server:8585/api").rstrip("/")
ADMIN_USERNAME = "admin@open-metadata.org"
TABLES = {
    "bronze": "elt_bronze.bronze.global.tb_municipios_ibge",
    "silver": "elt_silver.silver.global.tb_municipios_nf",
    "gold": "elt_gold.gold.global.dm_municipios_por_uf",
}


def login(password: str) -> str:
    encoded = base64.b64encode(password.encode()).decode()
    response = requests.post(
        f"{BASE_URL}/v1/users/login",
        json={"email": ADMIN_USERNAME, "password": encoded},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["accessToken"]


def main() -> None:
    password = os.environ["OM_ADMIN_PASSWORD"]
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {login(password)}"

    def get(path: str) -> dict:
        response = session.get(f"{BASE_URL}{path}", timeout=30)
        response.raise_for_status()
        return response.json()

    services = get("/v1/services/databaseServices?limit=100")["data"]
    service_names = [service["name"] for service in services]
    for name in ("elt_control", "elt_bronze", "elt_silver", "elt_gold"):
        assert service_names.count(name) == 1, f"database service {name} is missing or duplicated"

    for service, database in (
        ("elt_control", "elt"),
        ("elt_bronze", "bronze"),
        ("elt_silver", "silver"),
        ("elt_gold", "gold"),
    ):
        db_fqn = f"{service}.{database}"
        assert get(f"/v1/databases/name/{db_fqn}")["fullyQualifiedName"] == db_fqn
        schema_fqn = f"{db_fqn}.global"
        schema = get(f"/v1/databaseSchemas/name/{schema_fqn}")
        assert schema["fullyQualifiedName"] == schema_fqn

    expected = {
        "bronze": (
            9,
            "DataEngineers",
            {"DataSensitivity.Public", "ELTGlossary.CamadaBronze", "ELTGlossary.Municipio"},
        ),
        "silver": (
            10,
            "DataEngineers",
            {
                "DataSensitivity.Public",
                "ELTGlossary.CamadaSilver",
                "ELTGlossary.Municipio",
                "ELTGlossary.UnidadeFederativa",
            },
        ),
        "gold": (
            3,
            "DataOwners",
            {
                "DataSensitivity.Public",
                "ELTGlossary.CamadaGold",
                "ELTGlossary.QuantidadeMunicipios",
                "ELTGlossary.UnidadeFederativa",
            },
        ),
    }
    tables = {}
    for layer, fqn in TABLES.items():
        table = get(f"/v1/tables/name/{quote(fqn, safe='')}?fields=columns,owners,tags")
        tables[layer] = table
        column_count, owner, expected_tags = expected[layer]
        assert table.get("description"), f"{layer} table description is missing"
        assert len(table.get("columns") or []) == column_count
        assert all(column.get("description") for column in table["columns"])
        assert owner in {item.get("name") for item in table.get("owners") or []}
        tags = {item.get("tagFQN") for item in table.get("tags") or []}
        assert expected_tags <= tags
        assert "DataSensitivity.PII" not in tags

    for fqn, expected_tags in (
        (
            "elt_control.elt.global.schedule",
            {"DataSensitivity.Internal", "DataSensitivity.Sensitive"},
        ),
        (
            "elt_control.elt.global.controle_execucao",
            {"DataSensitivity.Internal", "DataSensitivity.Confidential"},
        ),
    ):
        table = get(f"/v1/tables/name/{quote(fqn, safe='')}?fields=owners,tags")
        tags = {item.get("tagFQN") for item in table.get("tags") or []}
        assert expected_tags <= tags
        assert "DataSensitivity.PII" not in tags
        owners = {owner.get("name") for owner in table.get("owners") or []}
        assert "DataEngineers" in owners

    teams = get("/v1/teams?limit=100")["data"]
    team_names = [team["name"] for team in teams]
    for name in ("DataOwners", "DataStewards", "DataEngineers"):
        assert team_names.count(name) == 1, f"team {name} is missing or duplicated"

    glossary = get("/v1/glossaries/name/ELTGlossary?fields=owners")
    assert glossary.get("description")
    assert "DataStewards" in {owner.get("name") for owner in glossary.get("owners") or []}
    terms = (
        "Municipio",
        "UnidadeFederativa",
        "QuantidadeMunicipios",
        "CamadaBronze",
        "CamadaSilver",
        "CamadaGold",
    )
    for name in terms:
        term = get(f"/v1/glossaryTerms/name/ELTGlossary.{name}?fields=owners")
        assert term.get("description")
        assert "DataStewards" in {owner.get("name") for owner in term.get("owners") or []}
    glossaries = get("/v1/glossaries?limit=100")["data"]
    assert [item["name"] for item in glossaries].count("ELTGlossary") == 1

    classification = get("/v1/classifications/name/DataSensitivity")
    assert classification.get("description")
    classifications = get("/v1/classifications?limit=100")["data"]
    assert [item["name"] for item in classifications].count("DataSensitivity") == 1
    for name in ("Public", "Internal", "Sensitive", "Confidential", "PII"):
        tag = get(f"/v1/tags/name/DataSensitivity.{name}")
        assert tag.get("description")

    pipeline = get("/v1/pipelines/name/elt_airflow.elt_municipios_ibge?fields=tasks,service")
    assert pipeline["name"] == "elt_municipios_ibge"
    assert pipeline.get("service", {}).get("name") == "elt_airflow"
    assert pipeline.get("tasks"), "Airflow pipeline has no ingested tasks"

    lineage = get(
        f"/v1/lineage/table/{tables['silver']['id']}?upstreamDepth=1&downstreamDepth=1"
    )
    assert len(lineage.get("upstreamEdges") or []) == 1
    assert len(lineage.get("downstreamEdges") or []) == 1
    lineage_json = json.dumps(lineage, sort_keys=True)
    for fragment in (
        "tb_municipios_ibge.codigo_ibge",
        "tb_municipios_nf.codigo_ibge",
        "tb_municipios_ibge.codigo_uf",
        "tb_municipios_nf.uf",
        "tb_municipios_nf.estado",
        "tb_municipios_ibge.siafi_id",
        "tb_municipios_nf.codigo_siafi",
        "dm_municipios_por_uf.uf",
        "dm_municipios_por_uf.estado",
        "dm_municipios_por_uf.total_municipios",
        "COUNT(*)",
        pipeline["id"],
    ):
        assert fragment in lineage_json, f"lineage fragment not found: {fragment}"

    test_cases = get("/v1/dataQuality/testCases?limit=100&fields=testDefinition")["data"]
    expected_tests = {
        "bronze_municipios_row_count": TABLES["bronze"],
        "silver_nordeste_row_count": TABLES["silver"],
        "gold_ufs_row_count": TABLES["gold"],
    }
    for name, table_fqn in expected_tests.items():
        matches = [test for test in test_cases if test.get("name") == name]
        assert len(matches) == 1, f"test case {name} is missing or duplicated"
        test_case = matches[0]
        assert table_fqn in test_case.get("entityLink", "")
        results = get(
            "/v1/dataQuality/testCases/testCaseResults/"
            f"{quote(test_case['fullyQualifiedName'], safe='')}?startTs=0&endTs={int(time.time() * 1000)}"
        )
        data = results.get("data", results if isinstance(results, list) else [])
        assert data, f"test case {name} has no result"
        latest = max(data, key=lambda result: result["timestamp"])
        assert latest["testCaseStatus"] == "Success"
        assert latest["timestamp"] > 0

    default_login = requests.post(
        f"{BASE_URL}/v1/users/login",
        json={
            "email": ADMIN_USERNAME,
            "password": base64.b64encode(b"admin").decode(),
        },
        timeout=30,
    )
    assert default_login.status_code in (400, 401), "default OpenMetadata password is still valid"

    print("Catalog: 4 services, databases and schemas; 3 governed pipeline tables")
    print("Governance: dictionary, 3 teams, 6 glossary terms, 5 classification tags")
    print("Lineage: 2 table edges with column mappings and Airflow pipeline reference")
    print("Data quality: 3 unique test cases with successful timestamped results")
    print("Authentication: generated password accepted; default password rejected")


if __name__ == "__main__":
    main()
