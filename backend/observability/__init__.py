from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.trace import Tracer

__all__ = [
    "force_flush_tracing",
    "get_meter",
    "get_tracer",
    "instrument_asyncpg_once",
    "is_otel_disabled",
    "setup_observability",
    "setup_tracing",
    "shutdown_tracing",
]


def setup_tracing() -> None:
    import_module("backend.observability.tracer").setup_tracing()


def setup_observability(*, instrument_asyncpg: bool = True) -> None:
    import_module("backend.observability.tracer").setup_observability(
        instrument_asyncpg=instrument_asyncpg
    )


def get_tracer(name: str) -> "Tracer":
    return cast(
        "Tracer", import_module("backend.observability.tracer").get_tracer(name)
    )


def get_meter(name: str) -> "Meter":
    return cast("Meter", import_module("backend.observability.tracer").get_meter(name))


def shutdown_tracing() -> None:
    import_module("backend.observability.tracer").shutdown_tracing()


def force_flush_tracing(timeout_millis: int = 30000) -> bool:
    return bool(
        import_module("backend.observability.tracer").force_flush_tracing(
            timeout_millis=timeout_millis
        )
    )


def instrument_asyncpg_once() -> None:
    import_module("backend.observability.tracer").instrument_asyncpg_once()


def is_otel_disabled() -> bool:
    return bool(import_module("backend.observability.tracer").is_otel_disabled())
