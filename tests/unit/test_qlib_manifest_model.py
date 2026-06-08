from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.quant.qlib_projection.manifest import QlibProjectionManifest


NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def _manifest(**overrides: object) -> QlibProjectionManifest:
    values: dict[str, object] = {
        "projection_id": uuid4(),
        "projection_name": "daily-bars",
        "projection_version": "projection-v1",
        "format": "qlib_bin",
        "source_query_hash": "query",
        "transform_hash": "transform",
        "row_count": 10,
        "start_ts": NOW,
        "end_ts": NOW + timedelta(days=1),
        "expires_at": NOW + timedelta(days=7),
        "ingested_at": NOW,
        "schema_version": "qlib-projection-manifest-v1",
        "metadata": {},
        "created_at": NOW,
    }
    values.update(overrides)
    return QlibProjectionManifest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("projection_format", ["qlib_bin", "parquet", "csv", "pandas"])
def test_qlib_projection_formats_are_accepted(projection_format: str) -> None:
    assert _manifest(format=projection_format).format == projection_format


def test_qlib_projection_invalid_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="format"):
        _manifest(format="duckdb")


@pytest.mark.parametrize(
    "field",
    ["projection_name", "projection_version", "source_query_hash", "transform_hash"],
)
def test_qlib_projection_required_strings(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _manifest(**{field: " "})


def test_qlib_projection_time_window_and_expiry_validation() -> None:
    with pytest.raises(ValueError, match="end_ts"):
        _manifest(end_ts=NOW - timedelta(days=1))
    with pytest.raises(ValueError, match="expires_at"):
        _manifest(expires_at=datetime(2026, 6, 5))
