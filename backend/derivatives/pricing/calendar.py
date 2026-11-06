"""Calendarios oficiais 3.0.0 (DL-PR02): carga JSON estrita, cobertura com recusa
do desconhecido e contagem de dias uteis por bissecao. Sem rede, sem relogio."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger

from config.derivatives_config_model import Conventions, IntervalConvention

EXPECTED_SCHEMA_VERSION = "3.0.0"
SHA256SUMS_NAME = "SHA256SUMS"


class CalendarId(StrEnum):
    """Identidades de calendario consumidas pelo Laboratorio (demais sao ignoradas)."""

    B3_LISTED_TRADING = "B3_LISTED_TRADING"
    BR_ANBIMA_BUSINESS = "BR_ANBIMA_BUSINESS"


class CalendarError(ValueError):
    """Bundle de calendario invalido ou fora do contrato 3.0.0."""


class CalendarCoverageError(CalendarError):
    """Data fora da cobertura confirmada; o desconhecido e recusado, nunca inferido."""


class CalendarIntegrityError(CalendarError):
    """Bytes do bundle divergem do checksum esperado."""


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    """Calendario imutavel de uma identidade: dias abertos e cobertura confirmada."""

    calendar_id: CalendarId
    version_ids: tuple[str, ...]
    coverage_years: frozenset[int]
    open_days: frozenset[date]
    closed_weekdays: frozenset[date]
    source_sha256: tuple[str, ...]


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CalendarError(f"chave JSON duplicada no bundle: {key!r}")
        out[key] = value
    return out


def _reject_constant(token: str) -> Any:
    raise CalendarError(f"constante JSON proibida no bundle: {token}")


def _calendar_day_rows(bundle: Mapping[str, Any], name: str) -> list[Any]:
    data = bundle.get("data")
    if not isinstance(data, Mapping):
        raise CalendarError(f"{name}: secao 'data' ausente ou invalida")
    rows = data.get("calendar_day")
    if not isinstance(rows, list):
        raise CalendarError(f"{name}: 'data.calendar_day' ausente ou invalida")
    return rows


def load_calendar_bundle(path: Path, *, expected_year: int, expected_sha256: str | None = None) -> dict[str, Any]:
    """Carrega um bundle 3.0.0 com JSON estrito, ano e checksum conferidos."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise CalendarIntegrityError(f"{path.name}: sha256 {digest} difere do esperado {expected_sha256}")
    try:
        bundle = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise CalendarError(f"{path.name} nao e JSON estrito: {exc}") from exc
    if not isinstance(bundle, dict):
        raise CalendarError(f"{path.name}: bundle deve ser um objeto JSON")
    schema = bundle.get("schema_version")
    if schema != EXPECTED_SCHEMA_VERSION:
        raise CalendarError(f"{path.name}: schema_version {schema!r} != {EXPECTED_SCHEMA_VERSION!r}")
    if bundle.get("year") != expected_year:
        raise CalendarError(f"{path.name}: year {bundle.get('year')!r} != esperado {expected_year}")
    known = {member.value for member in CalendarId}
    rows = _calendar_day_rows(bundle, path.name)
    unused = sorted({str(row.get("calendar_id")) for row in rows} - known)
    logger.info("calendario {}: unused_calendar_ids={}", path.name, unused)
    bundle["_source_sha256"] = digest
    return bundle


def build_calendar(bundles: Sequence[Mapping[str, Any]], calendar_id: CalendarId) -> TradingCalendar:
    """Constroi o calendario de uma identidade; ano com qualquer ``unknown`` fica fora."""
    open_days: set[date] = set()
    closed_weekdays: set[date] = set()
    coverage: set[int] = set()
    version_ids: list[str] = []
    shas: list[str] = []
    for bundle in bundles:
        name = str(bundle.get("bundle_id", "<bundle>"))
        year = int(bundle["year"])
        rows = [row for row in _calendar_day_rows(bundle, name) if row.get("calendar_id") == calendar_id.value]
        data = bundle["data"]
        projection = data.get("calendar_day_projection")
        if isinstance(projection, list) and projection:
            logger.info("calendario {}: {} linhas de projecao lidas e ignoradas", name, len(projection))
        version_ids.extend(
            str(v.get("version_id")) for v in data.get("calendar_version", []) if v.get("calendar_id") == calendar_id.value
        )
        sha = bundle.get("_source_sha256")
        if isinstance(sha, str):
            shas.append(sha)
        if not rows:
            continue
        if any(row.get("day_status") == "unknown" for row in rows):
            logger.info("calendario {}: ano {} inteiro desconhecido para {}; fora da cobertura", name, year, calendar_id.value)
            continue
        for row in rows:
            status = row.get("day_status")
            day = date.fromisoformat(str(row.get("calendar_date")))
            if status == "open":
                open_days.add(day)
            elif status == "closed":
                if row.get("is_weekend") is False:
                    closed_weekdays.add(day)
            else:
                raise CalendarError(f"{name}: day_status {status!r} desconhecido em {day.isoformat()}")
        coverage.add(year)
    return TradingCalendar(
        calendar_id=calendar_id,
        version_ids=tuple(version_ids),
        coverage_years=frozenset(coverage),
        open_days=frozenset(open_days),
        closed_weekdays=frozenset(closed_weekdays),
        source_sha256=tuple(shas),
    )


def _read_sha256sums(directory: Path) -> dict[str, str]:
    sums_path = directory / SHA256SUMS_NAME
    if not sums_path.is_file():
        return {}
    pairs = [line.split() for line in sums_path.read_text(encoding="utf-8").splitlines()]
    return {parts[1].lstrip("*"): parts[0] for parts in pairs if len(parts) == 2}


def load_calendars(cfg: Conventions, *, root: Path, checksums: Mapping[str, str] | None = None) -> dict[CalendarId, TradingCalendar]:
    """Carrega todos os bundles uma vez por processo e constroi os dois calendarios."""
    directory = root / cfg.calendars_dir
    paths = sorted(directory.glob("b3_calendar_*.yaml"))
    if not paths:
        raise CalendarError(f"nenhum bundle b3_calendar_*.yaml em {directory}")
    sums = dict(checksums) if checksums is not None else _read_sha256sums(directory)
    bundles: list[dict[str, Any]] = []
    for path in paths:
        try:
            year = int(path.stem.rsplit("_", 1)[-1])
        except ValueError as exc:
            raise CalendarError(f"nome de bundle sem ano: {path.name}") from exc
        bundles.append(load_calendar_bundle(path, expected_year=year, expected_sha256=sums.get(path.name)))
    return {member: build_calendar(bundles, member) for member in CalendarId}


def business_days_between(cal: TradingCalendar, start: date, end: date, *, convention: IntervalConvention) -> int:
    """Conta dias uteis entre datas na convencao declarada, por bissecao."""
    if start > end:
        raise ValueError(f"start {start.isoformat()} > end {end.isoformat()}")
    missing = sorted(y for y in range(start.year, end.year + 1) if y not in cal.coverage_years)
    if missing:
        raise CalendarCoverageError(f"{cal.calendar_id.value}: anos fora da cobertura confirmada: {missing}")
    ordered = tuple(sorted(cal.open_days))
    if convention == "(D0,Dv]":
        return bisect_right(ordered, end) - bisect_right(ordered, start)
    return bisect_left(ordered, end) - bisect_left(ordered, start)


def is_business_day(cal: TradingCalendar, day: date) -> bool:
    """Diz se a data e dia util; fora da cobertura recusa, nunca devolve ``False``."""
    if day.year not in cal.coverage_years:
        raise CalendarCoverageError(f"{cal.calendar_id.value}: ano {day.year} fora da cobertura confirmada")
    return day in cal.open_days


def third_friday_preceding(cal: TradingCalendar, year: int, month: int) -> date:
    """Candidato de vencimento mensal por regra publicada (3a sexta civil; se fechada,
    recua ao dia util anterior); nao afirma serie listada."""
    first = date(year, month, 1)
    candidate = third = first + timedelta(days=(4 - first.weekday()) % 7 + 14)
    for _ in range(31):
        if is_business_day(cal, candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise CalendarError(f"nenhum dia util em ate 31 dias antes de {third.isoformat()}")
