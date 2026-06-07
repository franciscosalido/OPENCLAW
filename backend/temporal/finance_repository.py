"""Asyncpg repository for Janus temporal finance memory."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from backend.temporal.finance_models import (
    KronosForecast,
    MarketBar,
    MarketFeature,
    MarketInstrument,
    ModelRun,
    QlibProjectionFormat,
    QlibProjectionManifest,
)


class FinanceRepository:
    """Repository using an injected asyncpg pool wrapper."""

    def __init__(self, client: object) -> None:
        self._pool = cast(asyncpg.Pool, getattr(client, "pool", client))

    async def create_market_instrument(
        self,
        *,
        symbol: str,
        exchange: str,
        asset_class: str,
        currency: str | None = None,
        timezone: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MarketInstrument:
        row = await self._pool.fetchrow(
            """
            INSERT INTO market_instruments(
                symbol,
                exchange,
                asset_class,
                currency,
                timezone,
                metadata
            )
            VALUES($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            symbol,
            exchange,
            asset_class,
            currency,
            timezone,
            dict(metadata or {}),
        )
        return _market_instrument_from_record(_require_row(row))

    async def get_market_instrument(
        self, instrument_id: UUID
    ) -> MarketInstrument | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM market_instruments WHERE instrument_id = $1",
            instrument_id,
        )
        return None if row is None else _market_instrument_from_record(row)

    async def get_market_instrument_by_symbol(
        self,
        *,
        symbol: str,
        exchange: str,
    ) -> MarketInstrument | None:
        row = await self._pool.fetchrow(
            """
            SELECT *
            FROM market_instruments
            WHERE symbol = $1 AND exchange = $2
            """,
            symbol,
            exchange,
        )
        return None if row is None else _market_instrument_from_record(row)

    async def upsert_market_instrument(
        self,
        *,
        symbol: str,
        exchange: str,
        asset_class: str,
        currency: str | None = None,
        timezone: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MarketInstrument:
        row = await self._pool.fetchrow(
            """
            INSERT INTO market_instruments(
                symbol,
                exchange,
                asset_class,
                currency,
                timezone,
                metadata
            )
            VALUES($1, $2, $3, $4, $5, $6)
            ON CONFLICT(symbol, exchange)
            DO UPDATE SET
                asset_class = EXCLUDED.asset_class,
                currency = EXCLUDED.currency,
                timezone = EXCLUDED.timezone,
                metadata = EXCLUDED.metadata
            RETURNING *
            """,
            symbol,
            exchange,
            asset_class,
            currency,
            timezone,
            dict(metadata or {}),
        )
        return _market_instrument_from_record(_require_row(row))

    async def upsert_market_bar(self, bar: MarketBar) -> MarketBar:
        row = await self._pool.fetchrow(
            """
            INSERT INTO market_bars(
                ts,
                instrument_id,
                timeframe,
                open,
                high,
                low,
                close,
                volume,
                amount,
                factor,
                source_id,
                ingested_at,
                schema_version,
                quality_flags,
                lineage_hash,
                metadata
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ON CONFLICT(instrument_id, timeframe, ts)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                factor = EXCLUDED.factor,
                source_id = EXCLUDED.source_id,
                ingested_at = EXCLUDED.ingested_at,
                schema_version = EXCLUDED.schema_version,
                quality_flags = EXCLUDED.quality_flags,
                lineage_hash = EXCLUDED.lineage_hash,
                metadata = EXCLUDED.metadata
            RETURNING *
            """,
            bar.ts,
            bar.instrument_id,
            bar.timeframe,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            bar.amount,
            bar.factor,
            bar.source_id,
            bar.ingested_at,
            bar.schema_version,
            dict(bar.quality_flags),
            bar.lineage_hash,
            dict(bar.metadata),
        )
        return _market_bar_from_record(_require_row(row))

    async def upsert_market_bars(self, bars: Sequence[MarketBar]) -> int:
        for bar in bars:
            await self.upsert_market_bar(bar)
        return len(bars)

    async def get_market_bars_window(
        self,
        *,
        instrument_id: UUID,
        timeframe: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
        limit: int | None = None,
        ascending: bool = True,
    ) -> list[MarketBar]:
        if not timeframe.strip():
            raise ValueError("timeframe cannot be empty")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be > 0")
        ascending_query = """
            SELECT *
            FROM market_bars
            WHERE instrument_id = $1
              AND timeframe = $2
              AND ($3::timestamptz IS NULL OR ts >= $3)
              AND ($4::timestamptz IS NULL OR ts <= $4)
            ORDER BY ts ASC
            LIMIT $5
            """
        descending_query = """
            SELECT *
            FROM market_bars
            WHERE instrument_id = $1
              AND timeframe = $2
              AND ($3::timestamptz IS NULL OR ts >= $3)
              AND ($4::timestamptz IS NULL OR ts <= $4)
            ORDER BY ts DESC
            LIMIT $5
            """
        query = ascending_query if ascending else descending_query
        rows = await self._pool.fetch(
            query,
            instrument_id,
            timeframe,
            start_ts,
            end_ts,
            limit,
        )
        return [_market_bar_from_record(row) for row in rows]

    async def insert_market_feature(self, feature: MarketFeature) -> MarketFeature:
        row = await self._pool.fetchrow(
            """
            INSERT INTO market_features(
                ts,
                instrument_id,
                timeframe,
                feature_name,
                feature_value,
                feature_version,
                source_bar_version,
                source_id,
                ingested_at,
                schema_version,
                lineage_hash,
                metadata
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT(instrument_id, timeframe, ts, feature_name, feature_version)
            DO UPDATE SET
                feature_value = EXCLUDED.feature_value,
                source_bar_version = EXCLUDED.source_bar_version,
                source_id = EXCLUDED.source_id,
                ingested_at = EXCLUDED.ingested_at,
                schema_version = EXCLUDED.schema_version,
                lineage_hash = EXCLUDED.lineage_hash,
                metadata = EXCLUDED.metadata
            RETURNING *
            """,
            feature.ts,
            feature.instrument_id,
            feature.timeframe,
            feature.feature_name,
            feature.feature_value,
            feature.feature_version,
            feature.source_bar_version,
            feature.source_id,
            feature.ingested_at,
            feature.schema_version,
            feature.lineage_hash,
            dict(feature.metadata),
        )
        return _market_feature_from_record(_require_row(row))

    async def create_model_run(self, run: ModelRun) -> ModelRun:
        row = await self._pool.fetchrow(
            """
            INSERT INTO model_runs(
                run_id,
                model_name,
                model_version,
                adapter_name,
                adapter_version,
                input_start_ts,
                input_end_ts,
                created_at,
                source_id,
                ingested_at,
                schema_version,
                lineage_hash,
                params,
                metrics,
                metadata
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
            """,
            run.run_id,
            run.model_name,
            run.model_version,
            run.adapter_name,
            run.adapter_version,
            run.input_start_ts,
            run.input_end_ts,
            run.created_at,
            run.source_id,
            run.ingested_at,
            run.schema_version,
            run.lineage_hash,
            dict(run.params),
            dict(run.metrics),
            dict(run.metadata),
        )
        return _model_run_from_record(_require_row(row))

    async def insert_kronos_forecast(self, forecast: KronosForecast) -> KronosForecast:
        row = await self._pool.fetchrow(
            """
            INSERT INTO kronos_forecasts(
                forecast_ts,
                run_id,
                instrument_id,
                timeframe,
                horizon_step,
                open_pred,
                high_pred,
                low_pred,
                close_pred,
                volume_pred,
                amount_pred,
                quantiles,
                sample_count,
                source_id,
                ingested_at,
                schema_version,
                lineage_hash,
                metadata,
                created_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            ON CONFLICT(run_id, instrument_id, timeframe, forecast_ts, horizon_step)
            DO UPDATE SET
                open_pred = EXCLUDED.open_pred,
                high_pred = EXCLUDED.high_pred,
                low_pred = EXCLUDED.low_pred,
                close_pred = EXCLUDED.close_pred,
                volume_pred = EXCLUDED.volume_pred,
                amount_pred = EXCLUDED.amount_pred,
                quantiles = EXCLUDED.quantiles,
                sample_count = EXCLUDED.sample_count,
                source_id = EXCLUDED.source_id,
                ingested_at = EXCLUDED.ingested_at,
                schema_version = EXCLUDED.schema_version,
                lineage_hash = EXCLUDED.lineage_hash,
                metadata = EXCLUDED.metadata,
                created_at = EXCLUDED.created_at
            RETURNING *
            """,
            forecast.forecast_ts,
            forecast.run_id,
            forecast.instrument_id,
            forecast.timeframe,
            forecast.horizon_step,
            forecast.open_pred,
            forecast.high_pred,
            forecast.low_pred,
            forecast.close_pred,
            forecast.volume_pred,
            forecast.amount_pred,
            dict(forecast.quantiles),
            forecast.sample_count,
            forecast.source_id,
            forecast.ingested_at,
            forecast.schema_version,
            forecast.lineage_hash,
            dict(forecast.metadata),
            forecast.created_at,
        )
        return _kronos_forecast_from_record(_require_row(row))

    async def insert_kronos_forecasts(
        self,
        forecasts: Sequence[KronosForecast],
    ) -> int:
        for forecast in forecasts:
            await self.insert_kronos_forecast(forecast)
        return len(forecasts)

    async def get_latest_kronos_forecast(
        self,
        *,
        instrument_id: UUID,
        timeframe: str,
    ) -> KronosForecast | None:
        row = await self._pool.fetchrow(
            """
            SELECT *
            FROM kronos_forecasts
            WHERE instrument_id = $1 AND timeframe = $2
            ORDER BY forecast_ts DESC, horizon_step DESC
            LIMIT 1
            """,
            instrument_id,
            timeframe,
        )
        return None if row is None else _kronos_forecast_from_record(row)

    async def create_qlib_projection_manifest(
        self,
        manifest: QlibProjectionManifest,
    ) -> QlibProjectionManifest:
        row = await self._pool.fetchrow(
            """
            INSERT INTO qlib_projection_manifests(
                projection_id,
                projection_name,
                projection_version,
                storage_uri,
                format,
                source_query_hash,
                transform_hash,
                checksum,
                row_count,
                start_ts,
                end_ts,
                expires_at,
                source_id,
                ingested_at,
                schema_version,
                lineage_hash,
                metadata,
                created_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            RETURNING *
            """,
            manifest.projection_id,
            manifest.projection_name,
            manifest.projection_version,
            manifest.storage_uri,
            manifest.format,
            manifest.source_query_hash,
            manifest.transform_hash,
            manifest.checksum,
            manifest.row_count,
            manifest.start_ts,
            manifest.end_ts,
            manifest.expires_at,
            manifest.source_id,
            manifest.ingested_at,
            manifest.schema_version,
            manifest.lineage_hash,
            dict(manifest.metadata),
            manifest.created_at,
        )
        return _qlib_projection_manifest_from_record(_require_row(row))

    async def get_qlib_projection_manifest(
        self,
        projection_id: UUID,
    ) -> QlibProjectionManifest | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM qlib_projection_manifests WHERE projection_id = $1",
            projection_id,
        )
        return None if row is None else _qlib_projection_manifest_from_record(row)


def _require_row(row: asyncpg.Record | None) -> asyncpg.Record:
    if row is None:
        raise RuntimeError("database write returned no row")
    return row


def _json_dict(row: asyncpg.Record, field_name: str) -> dict[str, Any]:
    value = row[field_name]
    if value is None:
        return {}
    return dict(value)


def _market_instrument_from_record(row: asyncpg.Record) -> MarketInstrument:
    return MarketInstrument(
        instrument_id=row["instrument_id"],
        symbol=row["symbol"],
        exchange=row["exchange"],
        asset_class=row["asset_class"],
        currency=row["currency"],
        timezone=row["timezone"],
        metadata=_json_dict(row, "metadata"),
        created_at=row["created_at"],
    )


def _market_bar_from_record(row: asyncpg.Record) -> MarketBar:
    return MarketBar(
        ts=row["ts"],
        instrument_id=row["instrument_id"],
        timeframe=row["timeframe"],
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"],
        amount=row["amount"],
        factor=row["factor"],
        source_id=row["source_id"],
        ingested_at=row["ingested_at"],
        schema_version=row["schema_version"],
        quality_flags=_json_dict(row, "quality_flags"),
        lineage_hash=row["lineage_hash"],
        metadata=_json_dict(row, "metadata"),
    )


def _market_feature_from_record(row: asyncpg.Record) -> MarketFeature:
    return MarketFeature(
        ts=row["ts"],
        instrument_id=row["instrument_id"],
        timeframe=row["timeframe"],
        feature_name=row["feature_name"],
        feature_value=row["feature_value"],
        feature_version=row["feature_version"],
        source_bar_version=row["source_bar_version"],
        source_id=row["source_id"],
        ingested_at=row["ingested_at"],
        schema_version=row["schema_version"],
        lineage_hash=row["lineage_hash"],
        metadata=_json_dict(row, "metadata"),
    )


def _model_run_from_record(row: asyncpg.Record) -> ModelRun:
    return ModelRun(
        run_id=row["run_id"],
        model_name=row["model_name"],
        model_version=row["model_version"],
        adapter_name=row["adapter_name"],
        adapter_version=row["adapter_version"],
        input_start_ts=row["input_start_ts"],
        input_end_ts=row["input_end_ts"],
        created_at=row["created_at"],
        source_id=row["source_id"],
        ingested_at=row["ingested_at"],
        schema_version=row["schema_version"],
        lineage_hash=row["lineage_hash"],
        params=_json_dict(row, "params"),
        metrics=_json_dict(row, "metrics"),
        metadata=_json_dict(row, "metadata"),
    )


def _kronos_forecast_from_record(row: asyncpg.Record) -> KronosForecast:
    return KronosForecast(
        forecast_ts=row["forecast_ts"],
        run_id=row["run_id"],
        instrument_id=row["instrument_id"],
        timeframe=row["timeframe"],
        horizon_step=row["horizon_step"],
        open_pred=row["open_pred"],
        high_pred=row["high_pred"],
        low_pred=row["low_pred"],
        close_pred=row["close_pred"],
        volume_pred=row["volume_pred"],
        amount_pred=row["amount_pred"],
        quantiles=_json_dict(row, "quantiles"),
        sample_count=row["sample_count"],
        source_id=row["source_id"],
        ingested_at=row["ingested_at"],
        schema_version=row["schema_version"],
        lineage_hash=row["lineage_hash"],
        metadata=_json_dict(row, "metadata"),
        created_at=row["created_at"],
    )


def _qlib_projection_manifest_from_record(
    row: asyncpg.Record,
) -> QlibProjectionManifest:
    return QlibProjectionManifest(
        projection_id=row["projection_id"],
        projection_name=row["projection_name"],
        projection_version=row["projection_version"],
        storage_uri=row["storage_uri"],
        format=cast(QlibProjectionFormat, row["format"]),
        source_query_hash=row["source_query_hash"],
        transform_hash=row["transform_hash"],
        checksum=row["checksum"],
        row_count=row["row_count"],
        start_ts=row["start_ts"],
        end_ts=row["end_ts"],
        expires_at=row["expires_at"],
        source_id=row["source_id"],
        ingested_at=row["ingested_at"],
        schema_version=row["schema_version"],
        lineage_hash=row["lineage_hash"],
        metadata=_json_dict(row, "metadata"),
        created_at=row["created_at"],
    )
