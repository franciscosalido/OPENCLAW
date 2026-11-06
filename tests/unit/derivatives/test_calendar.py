"""Calendarios 3.0.0: carga estrita, cobertura, contagem e 3a sexta (DL-PR02)."""

from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from backend.derivatives.pricing.calendar import (
    CalendarCoverageError,
    CalendarError,
    CalendarId,
    CalendarIntegrityError,
    TradingCalendar,
    build_calendar,
    business_days_between,
    is_business_day,
    load_calendar_bundle,
    load_calendars,
    third_friday_preceding,
)
from config.derivatives_config_model import Conventions

CALENDARS = Path("config/calendars")
BAD = Path("tests/fixtures/derivatives/calendars_bad")

# Quadro A do OC 041/2026 (errata): os 14 fechamentos de seg-sex da B3 em 2026.
QUADRO_A_2026 = (
    date(2026, 1, 1),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 4, 3),
    date(2026, 4, 21),
    date(2026, 5, 1),
    date(2026, 6, 4),
    date(2026, 9, 7),
    date(2026, 10, 12),
    date(2026, 11, 2),
    date(2026, 11, 20),
    date(2026, 12, 24),
    date(2026, 12, 25),
    date(2026, 12, 31),
)


@pytest.fixture(scope="module")
def calendars() -> dict[CalendarId, TradingCalendar]:
    return load_calendars(Conventions(), root=Path("."))


@pytest.fixture(scope="module")
def b3(calendars: dict[CalendarId, TradingCalendar]) -> TradingCalendar:
    return calendars[CalendarId.B3_LISTED_TRADING]


@pytest.fixture(scope="module")
def anbima(calendars: dict[CalendarId, TradingCalendar]) -> TradingCalendar:
    return calendars[CalendarId.BR_ANBIMA_BUSINESS]


# --- carga estrita ---------------------------------------------------------


@pytest.mark.parametrize("year", [2026, 2027, 2028])
def test_bundle_loads_with_schema_3_0_0(year: int) -> None:
    bundle = load_calendar_bundle(
        CALENDARS / f"b3_calendar_{year}.yaml", expected_year=year
    )
    assert bundle["schema_version"] == "3.0.0"
    assert bundle["year"] == year


def test_wrong_checksum_raises_integrity_error() -> None:
    with pytest.raises(CalendarIntegrityError, match="sha256"):
        load_calendar_bundle(
            CALENDARS / "b3_calendar_2026.yaml",
            expected_year=2026,
            expected_sha256="0" * 64,
        )


def test_schema_2_0_0_rejected() -> None:
    with pytest.raises(CalendarError, match="schema_version"):
        load_calendar_bundle(
            BAD / "b3_calendar_2026_schema2.yaml", expected_year=2026
        )


def test_duplicate_json_key_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "b3_calendar_2030.yaml"
    bad.write_text(
        '{"schema_version": "3.0.0", "schema_version": "3.0.0", "year": 2030}',
        encoding="utf-8",
    )
    with pytest.raises(CalendarError, match="duplicada"):
        load_calendar_bundle(bad, expected_year=2030)


def test_nan_constant_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "b3_calendar_2030.yaml"
    bad.write_text(
        '{"schema_version": "3.0.0", "year": 2030, "x": NaN}', encoding="utf-8"
    )
    with pytest.raises(CalendarError, match="proibida"):
        load_calendar_bundle(bad, expected_year=2030)


def test_wrong_year_rejected() -> None:
    with pytest.raises(CalendarError, match="year"):
        load_calendar_bundle(
            CALENDARS / "b3_calendar_2026.yaml", expected_year=2027
        )


def test_invalid_json_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "b3_calendar_2030.yaml"
    bad.write_text('{"schema_version": "3.0.0",', encoding="utf-8")
    with pytest.raises(CalendarError, match="JSON estrito"):
        load_calendar_bundle(bad, expected_year=2030)


def test_non_object_bundle_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "b3_calendar_2030.yaml"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(CalendarError, match="objeto JSON"):
        load_calendar_bundle(bad, expected_year=2030)


def test_missing_data_section_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "b3_calendar_2030.yaml"
    bad.write_text(
        '{"schema_version": "3.0.0", "year": 2030}', encoding="utf-8"
    )
    with pytest.raises(CalendarError, match="data"):
        load_calendar_bundle(bad, expected_year=2030)


def test_missing_calendar_day_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "b3_calendar_2030.yaml"
    bad.write_text(
        '{"schema_version": "3.0.0", "year": 2030, "data": {}}',
        encoding="utf-8",
    )
    with pytest.raises(CalendarError, match="calendar_day"):
        load_calendar_bundle(bad, expected_year=2030)


def test_loaded_bundle_carries_source_sha256() -> None:
    bundle = load_calendar_bundle(
        CALENDARS / "b3_calendar_2026.yaml", expected_year=2026
    )
    # Hash fixado de proposito: A3 exige que nenhum byte do bundle mude.
    assert bundle["_source_sha256"] == (
        "2b44e71b23838aabd9b64f6f6bce8ed4e2eb56de10e7ee12700ecbe6124574de"
    )


def test_error_hierarchy_is_value_error() -> None:
    assert issubclass(CalendarCoverageError, CalendarError)
    assert issubclass(CalendarIntegrityError, CalendarError)
    assert issubclass(CalendarError, ValueError)


# --- B3 2026 ---------------------------------------------------------------


def test_b3_2026_has_247_open_days(b3: TradingCalendar) -> None:
    assert len({day for day in b3.open_days if day.year == 2026}) == 247


def test_b3_2026_closed_weekdays_match_quadro_a(b3: TradingCalendar) -> None:
    assert sorted(b3.closed_weekdays) == sorted(QUADRO_A_2026)


def test_b3_christmas_eve_and_new_years_eve_closed(b3: TradingCalendar) -> None:
    assert is_business_day(b3, date(2026, 12, 24)) is False
    assert is_business_day(b3, date(2026, 12, 31)) is False


def test_b3_ash_wednesday_open(b3: TradingCalendar) -> None:
    assert is_business_day(b3, date(2026, 2, 18)) is True


def test_b3_sao_paulo_city_holiday_open(b3: TradingCalendar) -> None:
    assert is_business_day(b3, date(2026, 7, 9)) is True


@pytest.mark.parametrize("closure", QUADRO_A_2026, ids=str)
def test_quadro_a_closure_is_not_business_day(
    b3: TradingCalendar, closure: date
) -> None:
    assert is_business_day(b3, closure) is False
    assert closure in b3.closed_weekdays


def test_weekend_is_neither_open_nor_closed_weekday(b3: TradingCalendar) -> None:
    saturday = date(2026, 1, 3)
    assert is_business_day(b3, saturday) is False
    assert saturday not in b3.closed_weekdays


def test_b3_full_year_2026_counts_247(b3: TradingCalendar) -> None:
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    # 01/01 e 31/12 sao fechados; as duas convencoes coincidem no ano cheio.
    assert business_days_between(b3, start, end, convention="(D0,Dv]") == 247
    assert business_days_between(b3, start, end, convention="[D0,Dv)") == 247


# --- ANBIMA ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "expected"), [(2026, 249), (2027, 251), (2028, 248)]
)
def test_anbima_open_days_per_year(
    anbima: TradingCalendar, year: int, expected: int
) -> None:
    assert len({day for day in anbima.open_days if day.year == year}) == expected


def test_anbima_christmas_eve_and_new_years_eve_open(
    anbima: TradingCalendar,
) -> None:
    assert is_business_day(anbima, date(2026, 12, 24)) is True
    assert is_business_day(anbima, date(2026, 12, 31)) is True


def test_anbima_leap_day_2028_closed_carnival_and_covered(
    anbima: TradingCalendar,
) -> None:
    assert 2028 in anbima.coverage_years
    assert is_business_day(anbima, date(2028, 2, 29)) is False


def test_anbima_counts_across_year_boundary(anbima: TradingCalendar) -> None:
    assert (
        business_days_between(
            anbima, date(2026, 12, 20), date(2027, 1, 10), convention="(D0,Dv]"
        )
        == 13
    )


def test_anbima_third_friday_january_2027(anbima: TradingCalendar) -> None:
    assert third_friday_preceding(anbima, 2027, 1) == date(2027, 1, 15)


# --- cobertura: recusa do desconhecido --------------------------------------


def test_b3_coverage_is_only_2026(b3: TradingCalendar) -> None:
    assert b3.coverage_years == frozenset({2026})


def test_anbima_coverage_is_2026_to_2028(anbima: TradingCalendar) -> None:
    assert anbima.coverage_years == frozenset({2026, 2027, 2028})


def test_b3_count_into_2027_raises_coverage_error(b3: TradingCalendar) -> None:
    with pytest.raises(CalendarCoverageError, match="2027"):
        business_days_between(
            b3, date(2026, 12, 20), date(2027, 1, 10), convention="(D0,Dv]"
        )


def test_b3_projection_2027_never_promoted_to_open_days(
    b3: TradingCalendar,
) -> None:
    assert all(day.year == 2026 for day in b3.open_days)


def test_is_business_day_refuses_uncovered_year(b3: TradingCalendar) -> None:
    with pytest.raises(CalendarCoverageError, match="2029"):
        is_business_day(b3, date(2029, 1, 2))


# --- contagem --------------------------------------------------------------


def test_count_exclusive_inclusive_nov_05_to_19(b3: TradingCalendar) -> None:
    assert (
        business_days_between(
            b3, date(2026, 11, 5), date(2026, 11, 19), convention="(D0,Dv]"
        )
        == 10
    )


def test_count_inclusive_exclusive_same_when_both_open(
    b3: TradingCalendar,
) -> None:
    assert (
        business_days_between(
            b3, date(2026, 11, 5), date(2026, 11, 19), convention="[D0,Dv)"
        )
        == 10
    )


def test_conventions_differ_when_end_is_not_business_day(
    b3: TradingCalendar,
) -> None:
    # 2026-11-20 e fechamento da B3 (Consciencia Negra): (D0,Dv] nao o conta,
    # mas [D0,Dv) passa a contar o proprio 2026-11-05 (dia util).
    start, end = date(2026, 11, 5), date(2026, 11, 20)
    assert business_days_between(b3, start, end, convention="(D0,Dv]") == 10
    assert business_days_between(b3, start, end, convention="[D0,Dv)") == 11


def test_start_after_end_rejected(b3: TradingCalendar) -> None:
    with pytest.raises(ValueError, match="start"):
        business_days_between(
            b3, date(2026, 11, 19), date(2026, 11, 5), convention="(D0,Dv]"
        )


def test_same_date_counts_zero(b3: TradingCalendar) -> None:
    day = date(2026, 11, 19)
    assert business_days_between(b3, day, day, convention="(D0,Dv]") == 0
    assert business_days_between(b3, day, day, convention="[D0,Dv)") == 0


# --- 3a sexta (candidato por regra publicada) --------------------------------


def test_third_friday_november_2026_precedes_to_nov_19(
    b3: TradingCalendar,
) -> None:
    assert third_friday_preceding(b3, 2026, 11) == date(2026, 11, 19)


def test_third_friday_december_2026_is_open(b3: TradingCalendar) -> None:
    assert third_friday_preceding(b3, 2026, 12) == date(2026, 12, 18)


def test_third_friday_out_of_coverage_refused(b3: TradingCalendar) -> None:
    with pytest.raises(CalendarCoverageError, match="2027"):
        third_friday_preceding(b3, 2027, 1)


# --- build_calendar sintetico ------------------------------------------------


def _synthetic_bundle(year: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "3.0.0",
        "year": year,
        "bundle_id": f"synthetic-{year}",
        "data": {
            "calendar_day": rows,
            "calendar_version": [
                {
                    "calendar_id": "B3_LISTED_TRADING",
                    "version_id": f"B3_LISTED_TRADING:{year}:r1",
                }
            ],
            "calendar_day_projection": [],
        },
    }


def test_single_unknown_row_excludes_whole_year() -> None:
    rows = [
        {
            "calendar_id": "B3_LISTED_TRADING",
            "calendar_date": "2030-01-02",
            "day_status": "open",
            "is_weekend": False,
        },
        {
            "calendar_id": "B3_LISTED_TRADING",
            "calendar_date": "2030-01-03",
            "day_status": "unknown",
            "is_weekend": False,
        },
    ]
    calendar = build_calendar(
        [_synthetic_bundle(2030, rows)], CalendarId.B3_LISTED_TRADING
    )
    assert calendar.coverage_years == frozenset()
    assert calendar.open_days == frozenset()


def test_unexpected_day_status_rejected() -> None:
    rows = [
        {
            "calendar_id": "B3_LISTED_TRADING",
            "calendar_date": "2030-01-02",
            "day_status": "half_day",
            "is_weekend": False,
        }
    ]
    with pytest.raises(CalendarError, match="half_day"):
        build_calendar([_synthetic_bundle(2030, rows)], CalendarId.B3_LISTED_TRADING)


def test_other_identities_do_not_leak_into_calendar() -> None:
    rows = [
        {
            "calendar_id": "US_NYSE_CASH_EQUITIES",
            "calendar_date": "2030-01-02",
            "day_status": "open",
            "is_weekend": False,
        }
    ]
    calendar = build_calendar(
        [_synthetic_bundle(2030, rows)], CalendarId.B3_LISTED_TRADING
    )
    assert calendar.open_days == frozenset()
    assert calendar.coverage_years == frozenset()


def test_trading_calendar_is_frozen(b3: TradingCalendar) -> None:
    with pytest.raises(AttributeError):
        b3.calendar_id = CalendarId.BR_ANBIMA_BUSINESS  # type: ignore[misc]


def test_version_ids_record_what_was_read(b3: TradingCalendar) -> None:
    # B3 2027/2028 ficam fora da cobertura, mas a proveniencia registra as
    # tres versions lidas.
    assert len(b3.version_ids) == 3
    assert all(vid.startswith("B3_LISTED_TRADING:") for vid in b3.version_ids)


# --- load_calendars ----------------------------------------------------------


def test_load_calendars_missing_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match="nenhum bundle"):
        load_calendars(Conventions(), root=tmp_path)


def test_load_calendars_filename_without_year_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "config" / "calendars"
    directory.mkdir(parents=True)
    (directory / "b3_calendar_errata.yaml").write_text("{}", encoding="utf-8")
    with pytest.raises(CalendarError, match="sem ano"):
        load_calendars(Conventions(), root=tmp_path)


def test_load_calendars_uses_explicit_checksums() -> None:
    wrong = {f"b3_calendar_{year}.yaml": "f" * 64 for year in (2026, 2027, 2028)}
    with pytest.raises(CalendarIntegrityError, match="sha256"):
        load_calendars(Conventions(), root=Path("."), checksums=wrong)


# --- guarda de performance ---------------------------------------------------


@pytest.mark.timeout(10)
def test_load_three_bundles_and_build_two_calendars_under_one_second() -> None:
    start = time.perf_counter()
    load_calendars(Conventions(), root=Path("."))
    elapsed = time.perf_counter() - start
    if os.environ.get("CI") and elapsed >= 1.0:
        pytest.skip(f"CI lento: carga levou {elapsed:.2f}s")
    assert elapsed < 1.0
