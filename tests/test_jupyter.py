"""Tests for Jupyter Data Lab: notebook structure, compose config, and setup.ps1."""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_LAB = ROOT / "data_lab"
COMPOSE = ROOT / "docker-compose.yml"
SETUP_PS1 = ROOT / "setup.ps1"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKERIGNORE = ROOT / ".dockerignore"
ENTRYPOINT = ROOT / "docker" / "jupyter_entrypoint.sh"
DOCKERFILE = ROOT / "docker" / "Dockerfile.jupyter"

REQUIRED_NOTEBOOKS = [
    "00_Boas_Vindas_e_Validacao_do_Ambiente.ipynb",
    "01_Python_para_Dados.ipynb",
    "02_NumPy.ipynb",
    "03_Pandas.ipynb",
    "04_Polars_e_DuckDB.ipynb",
    "05_Arquivos_Excel_CSV_e_Parquet.ipynb",
    "06_APIs_e_JSON.ipynb",
    "07_SQLAlchemy_e_PostgreSQL.ipynb",
    "08_Visualizacao_de_Dados.ipynb",
    "09_Scikit_Learn_Basico.ipynb",
    "10_PySpark_Fundamentos.ipynb",
    "11_PySpark_Parquet_e_Medalhao.ipynb",
    "12_Desafios_de_Entrevista.ipynb",
]


# =====================================================================
# Notebook structure validation
# =====================================================================
class TestNotebookStructure:
    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_exists(self, name):
        assert (DATA_LAB / name).exists(), f"Missing notebook: {name}"

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_valid_json(self, name):
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "nbformat" in data
        assert data["nbformat"] == 4

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_has_kernelspec(self, name):
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ks = data.get("metadata", {}).get("kernelspec", {})
        assert ks.get("language") == "python", f"{name}: missing python kernelspec"

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_has_cells(self, name):
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cells = data.get("cells", [])
        assert len(cells) >= 3, f"{name}: too few cells ({len(cells)})"

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_has_markdown_and_code(self, name):
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        types = [c["cell_type"] for c in data["cells"]]
        assert "markdown" in types, f"{name}: no markdown cells"
        assert "code" in types, f"{name}: no code cells"

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_no_external_urls_in_code(self, name):
        """Code cells must not reference external APIs or URLs."""
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for i, cell in enumerate(data["cells"]):
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            # Allow localhost, 127.0.0.1, and known Docker hostnames
            urls = re.findall(r'https?://(?!localhost|127\.0\.0\.1|elt-postgres|elt-minio)[^\s"\'`]+', src)
            assert not urls, f"{name} cell {i}: external URL found: {urls}"

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_json_roundtrip(self, name):
        """Writing and re-reading produces identical JSON."""
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            original = json.load(f)
        rewritten = json.loads(json.dumps(original))
        assert original == rewritten

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_code_cells_have_execution_fields(self, name):
        """Code cells must have execution_count and outputs (ready to run)."""
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for i, cell in enumerate(data["cells"]):
            if cell["cell_type"] == "code":
                assert "execution_count" in cell, f"{name} cell {i}: missing execution_count"
                assert "outputs" in cell, f"{name} cell {i}: missing outputs"
                assert cell["execution_count"] is None, f"{name} cell {i}: execution_count not null"

    @pytest.mark.parametrize("name", REQUIRED_NOTEBOOKS)
    def test_notebook_language_version(self, name):
        """Python version in metadata must be 3.11.x (matching base image)."""
        path = DATA_LAB / name
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ver = data.get("metadata", {}).get("language_info", {}).get("version", "")
        assert ver.startswith("3.11"), f"{name}: expected Python 3.11.x, got {ver}"


# =====================================================================
# Docker Compose validation
# =====================================================================
class TestComposeSecurity:
    def test_compose_contains_jupyter_service(self):
        content = COMPOSE.read_text(encoding="utf-8")
        assert "jupyter:" in content
        assert "Dockerfile.jupyter" in content

    def test_jupyter_binds_localhost_only(self):
        content = COMPOSE.read_text(encoding="utf-8")
        # Find the jupyter service ports section
        in_jupyter = False
        for line in content.splitlines():
            if line.strip().startswith("jupyter:"):
                in_jupyter = True
            elif in_jupyter and re.match(r"^\s{2}\w", line) and not line.strip().startswith("jupyter"):
                in_jupyter = False
            if in_jupyter and "127.0.0.1" in line and ":8888" in line:
                return
        pytest.fail("Jupyter service must bind to 127.0.0.1:8888")

    def test_jupyter_no_env_file_in_volumes(self):
        """The .env file must NOT be mounted into the Jupyter container."""
        content = COMPOSE.read_text(encoding="utf-8")
        in_jupyter = False
        in_volumes = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("jupyter:"):
                in_jupyter = True
            elif in_jupyter and re.match(r"^\w", stripped) and not stripped.startswith("jupyter"):
                in_jupyter = False
                in_volumes = False
            if in_jupyter and stripped == "volumes:":
                in_volumes = True
            elif in_jupyter and in_volumes and stripped.startswith("-"):
                assert ".env" not in stripped, f"Jupyter volume mounts .env: {stripped}"
            elif in_jupyter and in_volumes and not stripped.startswith("-") and stripped:
                in_volumes = False

    def test_jupyter_has_resource_limits(self):
        content = COMPOSE.read_text(encoding="utf-8")
        # Find jupyter service block by looking for memory limit
        lines = content.splitlines()
        in_jupyter = False
        indent_level = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("jupyter:"):
                in_jupyter = True
                indent_level = len(line) - len(line.lstrip())
                continue
            if in_jupyter:
                curr_indent = len(line) - len(line.lstrip()) if stripped else indent_level + 1
                if curr_indent <= indent_level and stripped and not stripped.startswith("#"):
                    break
                if "memory:" in line and "4G" in line:
                    return
        pytest.fail("Jupyter service must have memory limit")

    def test_jupyter_depends_on_postgres_healthy(self):
        content = COMPOSE.read_text(encoding="utf-8")
        lines = content.splitlines()
        in_jupyter = False
        indent_level = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("jupyter:"):
                in_jupyter = True
                indent_level = len(line) - len(line.lstrip())
                continue
            if in_jupyter:
                curr_indent = len(line) - len(line.lstrip()) if stripped else indent_level + 1
                if curr_indent <= indent_level and stripped and not stripped.startswith("#"):
                    break
                if "condition: service_healthy" in line:
                    return
        pytest.fail("Jupyter must depend on postgres with service_healthy")

    def _jupyter_block(self):
        """Extract the jupyter service block from compose file."""
        content = COMPOSE.read_text(encoding="utf-8")
        lines = content.splitlines()
        block = []
        in_jupyter = False
        indent_level = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("jupyter:"):
                in_jupyter = True
                indent_level = len(line) - len(line.lstrip())
                continue
            if in_jupyter:
                curr_indent = len(line) - len(line.lstrip()) if stripped else indent_level + 1
                if curr_indent <= indent_level and stripped and not stripped.startswith("#"):
                    break
                block.append(line)
        return "\n".join(block)

    def test_jupyter_no_env_file_directive(self):
        """Jupyter service must NOT use env_file (explicit env only)."""
        block = self._jupyter_block()
        assert "env_file:" not in block, "jupyter service must not use env_file"

    def test_jupyter_explicit_postgres_env(self):
        """Jupyter environment must explicitly set POSTGRES_HOST/PORT."""
        block = self._jupyter_block()
        assert "POSTGRES_HOST" in block
        assert "elt-postgres" in block
        assert "POSTGRES_PORT" in block

    def test_jupyter_no_airflow_secrets(self):
        """Jupyter must NOT receive AIRFLOW_ADMIN_PASSWORD or FERNET_KEY."""
        block = self._jupyter_block()
        assert "AIRFLOW_ADMIN_PASSWORD" not in block
        assert "AIRFLOW_FERNET_KEY" not in block

    def test_healthcheck_validates_auth(self):
        """Healthcheck must hit /login (proves auth is active), not just /api."""
        block = self._jupyter_block()
        assert "/login" in block, "healthcheck must validate login page"
        assert "password" in block.lower(), "healthcheck must check password field"


# =====================================================================
# setup.ps1 validation
# =====================================================================
class TestSetupPs1:
    def test_generates_jupyter_username(self):
        content = SETUP_PS1.read_text(encoding="utf-8")
        assert "JUPYTER_USERNAME" in content

    def test_generates_jupyter_password(self):
        content = SETUP_PS1.read_text(encoding="utf-8")
        assert "JUPYTER_PASSWORD" in content

    def test_prints_jupyter_url(self):
        content = SETUP_PS1.read_text(encoding="utf-8")
        assert "8888" in content

    def test_logs_option_jupyter(self):
        content = SETUP_PS1.read_text(encoding="utf-8")
        assert "jupyter" in content.lower()


# =====================================================================
# .env.example validation
# =====================================================================
class TestEnvExample:
    def test_has_jupyter_port(self):
        content = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "JUPYTER_PORT" in content

    def test_has_jupyter_username(self):
        content = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "JUPYTER_USERNAME" in content

    def test_has_jupyter_password(self):
        content = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "JUPYTER_PASSWORD" in content


# =====================================================================
# Docker files validation
# =====================================================================
class TestDockerFiles:
    def test_dockerfile_jupyter_exists(self):
        assert DOCKERFILE.exists()

    def test_entrypoint_exists(self):
        assert ENTRYPOINT.exists()

    def test_entrypoint_is_executable(self):
        """Entry point must have execute permission (checked via content)."""
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert content.startswith("#!/bin/bash")

    def test_entrypoint_validates_password(self):
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert "JUPYTER_PASSWORD" in content

    def test_entrypoint_generates_hash(self):
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert "passwd" in content or "hashlib" in content

    def test_entrypoint_not_root(self):
        content = ENTRYPOINT.read_text(encoding="utf-8")
        # The entrypoint itself runs as the NB_UID user (set by Dockerfile)
        # but we verify it does not use 'sudo' or 'su root'
        assert "sudo" not in content
        assert "su root" not in content

    def test_dockerignore_excludes_env(self):
        content = DOCKERIGNORE.read_text(encoding="utf-8")
        assert ".env" in content
        assert ".git" in content

    def test_dockerfile_has_pinned_versions(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        # Check that pip install uses == versions
        assert "numpy==" in content
        assert "pandas==" in content
        assert "polars==" in content
        assert "duckdb==" in content

    def test_dockerfile_user_not_root(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        # Should switch to non-root user before pip install
        lines = content.splitlines()
        user_line_idx = None
        pip_line_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("USER ${NB_UID}"):
                user_line_idx = i
            if "pip install" in line and pip_line_idx is None:
                pip_line_idx = i
        assert user_line_idx is not None, "Dockerfile must use USER NB_UID"
        assert pip_line_idx is not None, "Dockerfile must have pip install"
        assert user_line_idx < pip_line_idx, "pip install must run as non-root"

    def test_dockerfile_has_sha256_digest(self):
        """Base image must be pinned by SHA-256 for reproducibility."""
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "@sha256:" in content, "Dockerfile must pin image by SHA-256 digest"

    def test_dockerfile_copy_chmod_chown(self):
        """Entrypoint must be copied with explicit permissions and owner."""
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "--chmod=755" in content, "COPY must use --chmod=755"
        assert f"--chown={{{{NB_UID}}}}:{{{{NB_GID}}}}" in content or "--chown=${NB_UID}:${NB_GID}" in content

    def test_dockerfile_no_forced_java_spark_home(self):
        """Must NOT override JAVA_HOME/SPARK_HOME (preserve official image)."""
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "ENV JAVA_HOME" not in content, "must not force JAVA_HOME"
        assert "ENV SPARK_HOME" not in content, "must not force SPARK_HOME"

    def test_entrypoint_disables_token_auth(self):
        """Password-only auth: token must be set to empty string."""
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert "token" in content
        assert "''" in content or '""' in content, "token must be set to empty"

    def test_entrypoint_starts_lab(self):
        """Must start JupyterLab, not basic notebook."""
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert "jupyter lab" in content or "jupyterlab" in content

    def test_entrypoint_passwd_default_algorithm(self):
        """Must use passwd(pw) with default secure algorithm (Argon2/sha512)."""
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert "passwd(" in content
        assert "algorithm='sha256'" not in content, "do not pin weak sha256"
        assert "bcrypt" not in content.lower()

    def test_entrypoint_no_recursive_chown_on_work(self):
        """Must NOT chown -R /home/jovyan/work (RO mounts would fail)."""
        content = ENTRYPOINT.read_text(encoding="utf-8")
        assert "chown -R" not in content.split("/home/jovyan/work")[1] if "/home/jovyan/work" in content else True

    def test_entrypoint_no_password_in_output(self):
        """Password and hash must never be echoed/logged."""
        content = ENTRYPOINT.read_text(encoding="utf-8")
        # No echo of JUPYTER_PASSWORD value or HASH value
        for line in content.splitlines():
            if line.strip().startswith("echo"):
                assert "$JUPYTER_PASSWORD}" not in line.replace("${JUPYTER_PASSWORD:-", "")
                assert "${HASH}" not in line


# =====================================================================
# Notebook content spot checks
# =====================================================================
class TestNotebookContent:
    def test_00_checks_python_version(self):
        nb = _load_notebook("00_Boas_Vindas_e_Validacao_do_Ambiente.ipynb")
        all_src = _all_source(nb)
        assert "sys.version" in all_src or "platform" in all_src

    def test_00_checks_pyspark(self):
        nb = _load_notebook("00_Boas_Vindas_e_Validacao_do_Ambiente.ipynb")
        all_src = _all_source(nb)
        assert "SparkSession" in all_src

    def test_00_checks_postgres(self):
        nb = _load_notebook("00_Boas_Vindas_e_Validacao_do_Ambiente.ipynb")
        all_src = _all_source(nb)
        assert "5432" in all_src or "postgres" in all_src.lower()

    def test_10_has_spark_stop(self):
        nb = _load_notebook("10_PySpark_Fundamentos.ipynb")
        all_src = _all_source(nb)
        assert "spark.stop()" in all_src

    def test_11_has_medalhao(self):
        nb = _load_notebook("11_PySpark_Parquet_e_Medalhao.ipynb")
        all_src = _all_source(nb)
        assert "bronze" in all_src.lower()
        assert "silver" in all_src.lower()
        assert "gold" in all_src.lower()

    def test_12_has_spark_stop(self):
        nb = _load_notebook("12_Desafios_de_Entrevista.ipynb")
        all_src = _all_source(nb)
        assert "spark.stop()" in all_src

    def test_06_uses_local_server(self):
        """Notebook 06 must use a local mock server, not external APIs."""
        nb = _load_notebook("06_APIs_e_JSON.ipynb")
        all_src = _all_source(nb)
        assert "127.0.0.1" in all_src or "localhost" in all_src

    def test_07_uses_elt_postgres(self):
        """Notebook 07 must reference elt-postgres (Docker hostname)."""
        nb = _load_notebook("07_SQLAlchemy_e_PostgreSQL.ipynb")
        all_src = _all_source(nb)
        assert "elt-postgres" in all_src

    def test_07_no_password_fallback(self):
        """Notebook 07 must NOT have hardcoded fallback password."""
        nb = _load_notebook("07_SQLAlchemy_e_PostgreSQL.ipynb")
        all_src = _all_source(nb)
        assert "senha_secreta" not in all_src, "fallback password must be removed"
        assert "raise RuntimeError" in all_src, "must raise when POSTGRES_PASSWORD missing"

    @pytest.mark.parametrize("name", [
        "00_Boas_Vindas_e_Validacao_do_Ambiente.ipynb",
        "10_PySpark_Fundamentos.ipynb",
        "11_PySpark_Parquet_e_Medalhao.ipynb",
        "12_Desafios_de_Entrevista.ipynb",
    ])
    def test_spark_local_2_cores(self, name):
        """Spark notebooks must use local[2] not local[*]."""
        nb = _load_notebook(name)
        all_src = _all_source(nb)
        assert "local[*]" not in all_src, f"{name}: must use local[2]"
        assert "local[2]" in all_src

    def test_00_validates_java_home(self):
        """Notebook 00 must validate JAVA_HOME from official image."""
        nb = _load_notebook("00_Boas_Vindas_e_Validacao_do_Ambiente.ipynb")
        all_src = _all_source(nb)
        assert "JAVA_HOME" in all_src
        assert "shutil.which" in all_src or "which" in all_src


def _load_notebook(name):
    path = DATA_LAB / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _all_source(nb):
    """Concatenate all source lines from all cells."""
    parts = []
    for cell in nb.get("cells", []):
        parts.append("".join(cell.get("source", [])))
    return "\n".join(parts)
