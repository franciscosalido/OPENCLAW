from __future__ import annotations

from pathlib import Path

import yaml

from backend.observability.lite_llm import (
    ensure_litellm_otel_callback_present,
    validate_litellm_otel_callback_config,
)


CONFIG = Path("infra/litellm/litellm_config.yaml")


def test_litellm_config_has_otel_callback_with_message_logging_disabled() -> None:
    validation = validate_litellm_otel_callback_config(CONFIG)

    assert validation == {
        "callbacks_present": True,
        "message_logging_disabled": True,
    }


def test_ensure_litellm_otel_callback_present_is_explicit_edit(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({"litellm_settings": {"turn_off_message_logging": True}}),
        encoding="utf-8",
    )

    ensure_litellm_otel_callback_present(path)

    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert cfg["litellm_settings"]["callbacks"] == ["otel"]
    assert cfg["callback_settings"]["otel"]["message_logging"] is False
