"""Validation for the unified OpenMetadata deployment."""

import importlib.util
import pathlib
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"
LEGACY_COMPOSE = ROOT / "docker-compose.openmetadata.yml"
PASSWORD_INIT = ROOT / "scripts" / "openmetadata" / "initialize_password.py"
MANAGE_SCRIPT = ROOT / "scripts" / "openmetadata" / "manage.ps1"
SETUP_SCRIPT = ROOT / "setup.ps1"
AIRFLOW_IGNORE = ROOT / ".airflowignore"
SAMPLE_DATA = ROOT / "sql" / "init" / "004_sample_data.sql"


def load_password_module():
    spec = importlib.util.spec_from_file_location("initialize_password", PASSWORD_INIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUnifiedCompose:
    def test_uses_single_elt_project(self):
        content = COMPOSE.read_text(encoding="utf-8")
        assert content.startswith("name: elt")

    def test_openmetadata_is_in_main_compose(self):
        content = COMPOSE.read_text(encoding="utf-8")
        assert "openmetadata-server:" in content
        assert "openmetadata-security-init:" in content

    def test_legacy_compose_is_removed(self):
        assert not LEGACY_COMPOSE.exists()

    def test_single_env_template_has_openmetadata_secrets(self):
        content = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "OM_DB_PASSWORD=" in content
        assert "OM_ADMIN_PASSWORD=" in content
        assert ".env.openmetadata" not in content

    def test_host_port_is_not_used_for_internal_openmetadata_urls(self):
        content = COMPOSE.read_text(encoding="utf-8")
        assert '"127.0.0.1:${OPENMETADATA_PORT:-8585}:8585"' in content
        assert "http://localhost:${OPENMETADATA_PORT" not in content
        assert "http://openmetadata-server:8585/api" in content

    def test_admin_username_is_not_exposed_as_configurable(self):
        compose = COMPOSE.read_text(encoding="utf-8")
        env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "OM_ADMIN_USERNAME" not in compose
        assert "OM_ADMIN_USERNAME" not in env_example

    def test_airflow_does_not_receive_the_entire_env_file(self):
        content = COMPOSE.read_text(encoding="utf-8")
        assert "env_file:" not in content

    def test_host_scripts_read_configured_openmetadata_port(self):
        manage = MANAGE_SCRIPT.read_text(encoding="utf-8")
        setup = SETUP_SCRIPT.read_text(encoding="utf-8")
        assert 'Get-EnvValue "OPENMETADATA_PORT" "8585"' in manage
        assert 'Get-EnvValue $envFile "OPENMETADATA_PORT" "8585"' in setup

    def test_setup_checks_native_command_failures(self):
        content = SETUP_SCRIPT.read_text(encoding="utf-8")
        assert 'Assert-ExitCode $composeExitCode "docker compose up"' in content
        assert 'Assert-ExitCode $LASTEXITCODE "docker compose build"' in content

    def test_openmetadata_scripts_are_not_parsed_as_dags(self):
        content = AIRFLOW_IGNORE.read_text(encoding="utf-8")
        assert "scripts/openmetadata/" in content.splitlines()

    def test_external_runtime_images_are_digest_pinned(self):
        content = COMPOSE.read_text(encoding="utf-8")
        image_lines = [
            line.strip() for line in content.splitlines() if line.strip().startswith("image:")
        ]
        assert image_lines
        assert all("@sha256:" in line for line in image_lines)

    def test_sample_dataset_is_pinned_to_a_commit(self):
        content = SAMPLE_DATA.read_text(encoding="utf-8")
        assert "/Municipios-Brasileiros/main/" not in content
        assert "/975a51d6f2e7a9ee22a734a42ebd624263812f0c/" in content

    def test_setup_detects_legacy_openmetadata_project(self):
        content = SETUP_SCRIPT.read_text(encoding="utf-8")
        assert "com.docker.compose.project=elt-openmetadata" in content

    def test_setup_updates_existing_volume_to_the_pinned_dataset(self):
        content = SETUP_SCRIPT.read_text(encoding="utf-8")
        assert "975a51d6f2e7a9ee22a734a42ebd624263812f0c/csv/municipios.csv" in content
        assert "UPDATE global.schedule SET url=" in content


class TestPasswordInitialization:
    def test_rejects_default_admin_password(self):
        module = load_password_module()
        with patch.object(module, "ADMIN_PASSWORD", "admin"):
            try:
                module.main()
            except RuntimeError as exc:
                assert "must not use" in str(exc)
            else:
                raise AssertionError("default password should be rejected")

    def test_keeps_already_configured_password(self):
        module = load_password_module()
        with (
            patch.object(module, "ADMIN_PASSWORD", "Generated1!Password"),
            patch.object(module, "login", return_value="token") as login,
            patch.object(module.requests, "put") as put,
        ):
            module.main()
        login.assert_called_once_with("Generated1!Password")
        put.assert_not_called()

    def test_rotates_initial_password(self):
        module = load_password_module()
        response = Mock()
        response.raise_for_status.return_value = None
        with (
            patch.object(module, "ADMIN_PASSWORD", "Generated1!Password"),
            patch.object(module, "login", side_effect=[None, "old-token", "new-token"]),
            patch.object(module.requests, "put", return_value=response) as put,
        ):
            module.main()
        payload = put.call_args.kwargs["json"]
        assert payload["oldPassword"] == "admin"
        assert payload["newPassword"] == "Generated1!Password"
        assert payload["requestType"] == "SELF"
