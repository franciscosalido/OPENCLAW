from __future__ import annotations

from infra.litellm.version_fingerprint import build_version_fingerprint, sanitize_dsn


def test_fingerprint_sanitizes_dsn() -> None:
    sanitized = sanitize_dsn("postgresql://user:secret@127.0.0.1:5432/quimera")

    assert sanitized == "postgresql://user:***@127.0.0.1:5432/quimera"
    assert "secret" not in sanitized


def test_fingerprint_tolerates_unavailable_services() -> None:
    def command_runner(_command: list[str], _timeout: float) -> tuple[int, str, str]:
        return 127, "", "missing"

    def http_getter(_url: str, _timeout: float) -> tuple[int | None, str]:
        return None, "ConnectError"

    fingerprint = build_version_fingerprint(
        env={"LITELLM_MASTER_KEY": "local-dev-key"},
        command_runner=command_runner,
        http_getter=http_getter,
    )

    assert fingerprint.schema_version == "quimera-litellm-version-fingerprint-v1"
    assert fingerprint.values["python"]
    assert fingerprint.values["python_version"]
    assert fingerprint.values["python_executable"]
    assert fingerprint.values["docker_compose"] is None
    assert any(warning["component"] == "ollama" for warning in fingerprint.warnings)
    assert any(warning["component"] == "qdrant_ready" for warning in fingerprint.warnings)


def test_fingerprint_contains_package_versions_when_installed() -> None:
    fingerprint = build_version_fingerprint(env={"LITELLM_MASTER_KEY": "local-dev-key"})

    assert "pydantic" in fingerprint.values
    assert "httpx" in fingerprint.values
    assert "litellm" in fingerprint.values


def test_python_version_does_not_depend_on_command_runner_failure() -> None:
    def command_runner(_command: list[str], _timeout: float) -> tuple[int, str, str]:
        return 127, "", "forced failure"

    fingerprint = build_version_fingerprint(
        env={"LITELLM_MASTER_KEY": "local-dev-key"},
        command_runner=command_runner,
        http_getter=lambda _url, _timeout: (None, "offline"),
    )

    assert isinstance(fingerprint.values["python_version"], str)
    assert fingerprint.values["python_version"]
