from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return raw


def validate_litellm_otel_callback_config(path: Path) -> dict[str, bool]:
    cfg = _load_yaml(path)
    settings = cfg.get("litellm_settings")
    if not isinstance(settings, dict):
        raise ValueError("litellm_settings is required")
    callbacks = settings.get("callbacks")
    callbacks_present = isinstance(callbacks, list) and "otel" in callbacks
    callback_settings = cfg.get("callback_settings")
    otel_settings = (
        callback_settings.get("otel") if isinstance(callback_settings, dict) else None
    )
    message_logging_disabled = (
        isinstance(otel_settings, dict)
        and otel_settings.get("message_logging") is False
        and settings.get("turn_off_message_logging") is True
    )
    return {
        "callbacks_present": callbacks_present,
        "message_logging_disabled": message_logging_disabled,
    }


def ensure_litellm_otel_callback_present(path: Path) -> None:
    cfg = _load_yaml(path)
    settings = cfg.setdefault("litellm_settings", {})
    if not isinstance(settings, dict):
        raise ValueError("litellm_settings must be a mapping")
    callbacks = settings.setdefault("callbacks", [])
    if not isinstance(callbacks, list):
        raise ValueError("litellm_settings.callbacks must be a list")
    if "otel" not in callbacks:
        callbacks.append("otel")
    settings["turn_off_message_logging"] = True
    callback_settings = cfg.setdefault("callback_settings", {})
    if not isinstance(callback_settings, dict):
        raise ValueError("callback_settings must be a mapping")
    otel_settings = callback_settings.setdefault("otel", {})
    if not isinstance(otel_settings, dict):
        raise ValueError("callback_settings.otel must be a mapping")
    otel_settings["message_logging"] = False
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--config", type=Path, default=Path("infra/litellm/litellm_config.yaml")
    )
    args = parser.parse_args()
    result = validate_litellm_otel_callback_config(args.config)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result)
    return 0 if all(result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
