#!/usr/bin/env python
"""Compare Agent-0 golden reports and enforce the Gateway-2 baseline gate."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


EXIT_OK = 0
EXIT_SCHEMA_SANITIZATION = 2
EXIT_CITATION_QUALITY = 3
EXIT_LATENCY_REGRESSION = 4
EXIT_FIXTURE_CONFIG_MISMATCH = 5
EXIT_INCOMPATIBLE = 6

ALLOWED_RUN_TYPES = frozenset({"cold_start", "warm_model", "degraded_qdrant"})
PROHIBITED_EXACT_KEYS = frozenset(
    {
        "prompt",
        "question",
        "raw_user_input",
        "answer",
        "chunks",
        "chunk_text",
        "vectors",
        "embeddings",
        "payload",
        "qdrant_payload",
        "headers",
        "api_key",
        "authorization",
        "raw_exception",
        "exception_message",
        "traceback",
        "model_weights_path",
        "username",
    }
)
PROHIBITED_VALUE_MARKERS = (
    "/Users/",
    "/home/",
    "\\Users\\",
    "sk-",
    "Bearer ",
    "FAKE_API_KEY_SHOULD_NOT_APPEAR",
    "FAKE_PROMPT_SHOULD_NOT_APPEAR",
    "FAKE_CHUNK_SHOULD_NOT_APPEAR",
    "FAKE_VECTOR_SHOULD_NOT_APPEAR",
)
MIXED_LATENCY_KEYS = frozenset(
    {"mean_total_ms", "mean_latency_ms_by_alias", "p95_latency_ms_by_alias"}
)
SUMMARY_REQUIRED_FIELDS = frozenset(
    {
        "run_id",
        "timestamp_utc",
        "sprint",
        "source_commit",
        "branch",
        "question_fixture_hash",
        "golden_harness_version",
        "thresholds_version",
        "results_artifact",
        "summary_by_alias_and_run_type",
    }
)
RESULT_REQUIRED_FIELDS = frozenset(
    {
        "question_id",
        "question_fixture_hash",
        "alias",
        "run_type",
        "total_ms",
        "citation_present",
        "answer_length_chars",
        "estimated_remote_tokens_avoided",
    }
)


class Gateway2GateError(ValueError):
    """Gate failure with a stable exit code."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class Gateway2Report:
    """Loaded Gateway-2 summary plus its JSONL result rows."""

    summary_path: Path
    summary: Mapping[str, Any]
    results: tuple[Mapping[str, Any], ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse comparison CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Compare golden reports or enforce the Gateway-2 baseline gate.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--verify-only",
        help="Validate one Gateway-2 baseline summary JSON without live services.",
    )
    mode.add_argument("--baseline", help="Baseline summary JSON.")
    parser.add_argument("--candidate", help="Candidate summary JSON.")
    parser.add_argument("--thresholds", help="Gateway-2 regression thresholds YAML.")
    parser.add_argument(
        "--latency-threshold-pct",
        type=float,
        default=20.0,
        help="Legacy mean latency regression threshold by alias.",
    )
    return parser.parse_args(argv)


def compare_summaries(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    latency_threshold_pct: float,
) -> tuple[str, int]:
    """Return the legacy human-readable comparison table and exit code."""
    if latency_threshold_pct < 0:
        raise ValueError("latency_threshold_pct cannot be negative")
    baseline_rate = _pass_rate(baseline)
    candidate_rate = _pass_rate(candidate)
    pass_rate_delta = candidate_rate - baseline_rate
    baseline_latency = _read_float_mapping(baseline, "mean_latency_ms_by_alias")
    candidate_latency = _read_float_mapping(candidate, "mean_latency_ms_by_alias")
    aliases = sorted(set(baseline_latency) | set(candidate_latency))
    latency_rows: list[tuple[str, float, float, float]] = []
    latency_regression = False
    for alias in aliases:
        base = baseline_latency.get(alias, 0.0)
        cand = candidate_latency.get(alias, 0.0)
        delta_pct = _percent_delta(base, cand)
        latency_rows.append((alias, base, cand, delta_pct))
        if base > 0 and delta_pct > latency_threshold_pct:
            latency_regression = True

    fallback_delta = _read_int(candidate, "fallback_count") - _read_int(
        baseline,
        "fallback_count",
    )
    token_delta = _read_float(
        candidate,
        "total_estimated_remote_tokens_avoided",
    ) - _read_float(baseline, "total_estimated_remote_tokens_avoided")

    lines = [
        "golden_run_comparison",
        f"pass_rate_delta={pass_rate_delta:.4f}",
        f"fallback_count_delta={fallback_delta}",
        f"total_estimated_remote_tokens_avoided_delta={token_delta:.1f}",
        "alias | baseline_mean_ms | candidate_mean_ms | delta_pct",
    ]
    for alias, base, cand, delta_pct in latency_rows:
        lines.append(f"{alias} | {base:.1f} | {cand:.1f} | {delta_pct:.1f}")

    exit_code = 1 if pass_rate_delta < 0 or latency_regression else 0
    return "\n".join(lines) + "\n", exit_code


def verify_gateway2_summary(summary_path: Path | str) -> Gateway2Report:
    """Load and validate a Gateway-2 summary and sibling JSONL result artifact."""
    path = Path(summary_path)
    summary = _load_summary(path)
    _validate_gateway2_summary(summary)
    artifact = _read_nonempty_str(summary, "results_artifact")
    results_path = path.parent / artifact
    results = tuple(_load_jsonl(results_path))
    _validate_gateway2_results(results, summary=summary)
    return Gateway2Report(summary_path=path, summary=summary, results=results)


def compare_gateway2_reports(
    *,
    baseline_path: Path | str,
    candidate_path: Path | str,
    thresholds_path: Path | str,
) -> tuple[str, int]:
    """Compare candidate against baseline using Gateway-2 gate thresholds."""
    baseline = verify_gateway2_summary(baseline_path)
    candidate = verify_gateway2_summary(candidate_path)
    thresholds = load_thresholds(thresholds_path)
    _validate_report_compatibility(baseline, candidate, thresholds)
    _validate_citation_gate(baseline, candidate)
    _validate_quality_gate(candidate, thresholds)
    latency_lines = _validate_latency_gate(baseline, candidate, thresholds)
    lines = [
        "gateway2_baseline_regression_gate",
        f"baseline={baseline.summary_path}",
        f"candidate={candidate.summary_path}",
        "status=pass",
        *latency_lines,
    ]
    return "\n".join(lines) + "\n", EXIT_OK


def load_thresholds(path: Path | str) -> Mapping[str, Any]:
    """Load configurable Gateway-2 regression thresholds."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise Gateway2GateError(
            "thresholds YAML must be a mapping",
            EXIT_FIXTURE_CONFIG_MISMATCH,
        )
    version = raw.get("thresholds_version")
    if not isinstance(version, str) or not version.strip():
        raise Gateway2GateError(
            "thresholds_version is required",
            EXIT_FIXTURE_CONFIG_MISMATCH,
        )
    aliases = raw.get("aliases")
    if not isinstance(aliases, Mapping) or not aliases:
        raise Gateway2GateError(
            "threshold aliases mapping is required",
            EXIT_FIXTURE_CONFIG_MISMATCH,
        )
    return raw


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    try:
        if args.verify_only is not None:
            verify_gateway2_summary(args.verify_only)
            sys.stdout.write("Gateway-2 baseline summary OK\n")
            return EXIT_OK
        if args.baseline is None or args.candidate is None:
            raise Gateway2GateError(
                "--candidate is required with --baseline",
                EXIT_INCOMPATIBLE,
            )
        if args.thresholds is not None:
            output, exit_code = compare_gateway2_reports(
                baseline_path=args.baseline,
                candidate_path=args.candidate,
                thresholds_path=args.thresholds,
            )
        else:
            baseline = _load_summary(args.baseline)
            candidate = _load_summary(args.candidate)
            if _is_gateway2_summary(baseline) or _is_gateway2_summary(candidate):
                raise Gateway2GateError(
                    "--thresholds is required for Gateway-2 baseline comparison",
                    EXIT_FIXTURE_CONFIG_MISMATCH,
                )
            output, exit_code = compare_summaries(
                baseline,
                candidate,
                latency_threshold_pct=args.latency_threshold_pct,
            )
        sys.stdout.write(output)
        return exit_code
    except Gateway2GateError as exc:
        print(f"Gateway-2 gate failed: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Golden comparison failed: {type(exc).__name__}", file=sys.stderr)
        return EXIT_SCHEMA_SANITIZATION


def _load_summary(path: Path | str) -> Mapping[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("summary JSON must be an object")
    return raw


def _is_gateway2_summary(summary: Mapping[str, Any]) -> bool:
    return (
        summary.get("sprint") == "Gateway-2"
        or summary.get("baseline_format_version") == "gateway2_baseline_v1"
        or "summary_by_alias_and_run_type" in summary
    )


def _load_jsonl(path: Path) -> Iterable[Mapping[str, Any]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, Mapping):
            raise Gateway2GateError(
                f"JSONL line {line_number} must be an object",
                EXIT_SCHEMA_SANITIZATION,
            )
        yield raw


def _validate_gateway2_summary(summary: Mapping[str, Any]) -> None:
    _assert_sanitized(summary)
    missing = SUMMARY_REQUIRED_FIELDS - set(summary)
    if missing:
        raise Gateway2GateError(
            f"summary missing required fields: {sorted(missing)}",
            EXIT_SCHEMA_SANITIZATION,
        )
    if summary.get("sprint") != "Gateway-2":
        raise Gateway2GateError("summary sprint must be Gateway-2", EXIT_INCOMPATIBLE)
    fixture_hash = summary.get("question_fixture_hash")
    if not isinstance(fixture_hash, str) or len(fixture_hash) < 12:
        raise Gateway2GateError(
            "question_fixture_hash is required",
            EXIT_FIXTURE_CONFIG_MISMATCH,
        )
    for key in MIXED_LATENCY_KEYS:
        if key in summary:
            raise Gateway2GateError(
                f"summary must not contain mixed latency key {key}",
                EXIT_SCHEMA_SANITIZATION,
            )
    grouped = summary.get("summary_by_alias_and_run_type")
    if not isinstance(grouped, Mapping) or not grouped:
        raise Gateway2GateError(
            "summary_by_alias_and_run_type is required",
            EXIT_SCHEMA_SANITIZATION,
        )
    for alias, run_types in grouped.items():
        if not isinstance(alias, str) or not alias.strip():
            raise Gateway2GateError("summary alias keys must be strings", EXIT_SCHEMA_SANITIZATION)
        if not isinstance(run_types, Mapping) or not run_types:
            raise Gateway2GateError(
                "summary must group metrics by alias and run_type",
                EXIT_SCHEMA_SANITIZATION,
            )
        for run_type, metrics in run_types.items():
            if run_type not in ALLOWED_RUN_TYPES:
                raise Gateway2GateError(
                    f"invalid run_type in summary: {run_type}",
                    EXIT_SCHEMA_SANITIZATION,
                )
            if not isinstance(metrics, Mapping):
                raise Gateway2GateError(
                    "summary run_type metrics must be mappings",
                    EXIT_SCHEMA_SANITIZATION,
                )


def _validate_gateway2_results(
    results: Sequence[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any],
) -> None:
    if not results:
        raise Gateway2GateError("results artifact must not be empty", EXIT_SCHEMA_SANITIZATION)
    fixture_hash = _read_nonempty_str(summary, "question_fixture_hash")
    for result in results:
        _assert_sanitized(result)
        missing = RESULT_REQUIRED_FIELDS - set(result)
        if missing:
            raise Gateway2GateError(
                f"result missing required fields: {sorted(missing)}",
                EXIT_SCHEMA_SANITIZATION,
            )
        if result.get("question_fixture_hash") != fixture_hash:
            raise Gateway2GateError(
                "result question_fixture_hash differs from summary",
                EXIT_FIXTURE_CONFIG_MISMATCH,
            )
        run_type = result.get("run_type")
        if run_type not in ALLOWED_RUN_TYPES:
            raise Gateway2GateError("result run_type missing or invalid", EXIT_SCHEMA_SANITIZATION)
        for key in (
            "question_id",
            "alias",
            "run_type",
            "question_fixture_hash",
        ):
            _read_nonempty_str(result, key)
        for key in (
            "total_ms",
            "answer_length_chars",
            "estimated_remote_tokens_avoided",
        ):
            _read_number(result, key)
        if not isinstance(result.get("citation_present"), bool):
            raise Gateway2GateError(
                "citation_present must be boolean",
                EXIT_SCHEMA_SANITIZATION,
            )
        _validate_optional_metrics(result)


def _validate_optional_metrics(result: Mapping[str, Any]) -> None:
    metric_keys = (
        "generation_ms",
        "prompt_eval_duration_ms",
        "eval_duration_ms",
        "load_duration_ms",
        "ollama_eval_count",
        "tokens_per_second",
        "quality_score",
    )
    for key in metric_keys:
        value = result.get(key)
        if value is None:
            if key.endswith("_ms") and result.get("metric_unavailable_reason") is None:
                raise Gateway2GateError(
                    f"{key} requires metric_unavailable_reason when null",
                    EXIT_SCHEMA_SANITIZATION,
                )
            continue
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise Gateway2GateError(f"{key} must be numeric or null", EXIT_SCHEMA_SANITIZATION)


def _validate_report_compatibility(
    baseline: Gateway2Report,
    candidate: Gateway2Report,
    thresholds: Mapping[str, Any],
) -> None:
    if baseline.summary.get("question_fixture_hash") != candidate.summary.get(
        "question_fixture_hash"
    ):
        raise Gateway2GateError("question fixture hash mismatch", EXIT_FIXTURE_CONFIG_MISMATCH)
    if baseline.summary.get("thresholds_version") != thresholds.get("thresholds_version"):
        raise Gateway2GateError(
            "baseline thresholds_version differs from thresholds config",
            EXIT_FIXTURE_CONFIG_MISMATCH,
        )
    baseline_keys = _result_keys(baseline.results)
    candidate_keys = _result_keys(candidate.results)
    missing = baseline_keys - candidate_keys
    if missing:
        raise Gateway2GateError(
            f"candidate missing baseline result keys: {sorted(missing)[:3]}",
            EXIT_INCOMPATIBLE,
        )


def _validate_citation_gate(
    baseline: Gateway2Report,
    candidate: Gateway2Report,
) -> None:
    candidate_by_key = {(_result_key(result)): result for result in candidate.results}
    for base in baseline.results:
        candidate_result = candidate_by_key[_result_key(base)]
        citation_expected = bool(base.get("citation_expected", False))
        if citation_expected and candidate_result.get("citation_present") is not True:
            raise Gateway2GateError("citation gate failed", EXIT_CITATION_QUALITY)
        if (
            base.get("citation_present") is True
            and candidate_result.get("citation_present") is False
        ):
            raise Gateway2GateError("citation regression detected", EXIT_CITATION_QUALITY)


def _validate_quality_gate(
    candidate: Gateway2Report,
    thresholds: Mapping[str, Any],
) -> None:
    quality = thresholds.get("quality")
    if not isinstance(quality, Mapping):
        return
    required = quality.get("required", False)
    minimum = quality.get("minimum_score")
    if not isinstance(required, bool):
        raise Gateway2GateError("quality.required must be boolean", EXIT_FIXTURE_CONFIG_MISMATCH)
    if minimum is None:
        return
    if not isinstance(minimum, int | float) or isinstance(minimum, bool):
        raise Gateway2GateError(
            "quality.minimum_score must be numeric",
            EXIT_FIXTURE_CONFIG_MISMATCH,
        )
    for result in candidate.results:
        score = result.get("quality_score")
        if score is None:
            if required:
                raise Gateway2GateError("quality score required but missing", EXIT_CITATION_QUALITY)
            continue
        if not isinstance(score, int | float) or isinstance(score, bool):
            raise Gateway2GateError("quality_score must be numeric", EXIT_SCHEMA_SANITIZATION)
        if score < float(minimum):
            raise Gateway2GateError("quality gate failed", EXIT_CITATION_QUALITY)


def _validate_latency_gate(
    baseline: Gateway2Report,
    candidate: Gateway2Report,
    thresholds: Mapping[str, Any],
) -> list[str]:
    lines: list[str] = ["alias | run_type | baseline_total_ms | candidate_total_ms | delta_pct"]
    baseline_means = _mean_total_by_alias_run_type(baseline.results)
    candidate_means = _mean_total_by_alias_run_type(candidate.results)
    aliases = thresholds.get("aliases")
    if not isinstance(aliases, Mapping):
        raise Gateway2GateError("threshold aliases mapping is required", EXIT_FIXTURE_CONFIG_MISMATCH)
    for alias, run_type_config in aliases.items():
        if not isinstance(alias, str) or not isinstance(run_type_config, Mapping):
            raise Gateway2GateError("threshold alias entries must be mappings", EXIT_FIXTURE_CONFIG_MISMATCH)
        for run_type, config in run_type_config.items():
            if run_type not in ALLOWED_RUN_TYPES or not isinstance(config, Mapping):
                raise Gateway2GateError("invalid threshold run_type entry", EXIT_FIXTURE_CONFIG_MISMATCH)
            if config.get("fallback_contract_only") is True:
                continue
            warning_only = bool(config.get("warning_only", False))
            threshold_pct = config.get("latency_regression_pct")
            if threshold_pct is None:
                continue
            if not isinstance(threshold_pct, int | float) or isinstance(threshold_pct, bool):
                raise Gateway2GateError("latency_regression_pct must be numeric", EXIT_FIXTURE_CONFIG_MISMATCH)
            key = (alias, run_type)
            if key not in baseline_means or key not in candidate_means:
                if warning_only:
                    continue
                raise Gateway2GateError("missing latency group for threshold", EXIT_INCOMPATIBLE)
            base = baseline_means[key]
            cand = candidate_means[key]
            delta_pct = _percent_delta(base, cand)
            lines.append(f"{alias} | {run_type} | {base:.1f} | {cand:.1f} | {delta_pct:.1f}")
            if not warning_only and delta_pct > float(threshold_pct):
                raise Gateway2GateError("latency regression detected", EXIT_LATENCY_REGRESSION)
    return lines


def _mean_total_by_alias_run_type(
    results: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], list[float]] = {}
    for result in results:
        alias = _read_nonempty_str(result, "alias")
        run_type = _read_nonempty_str(result, "run_type")
        total = _read_number(result, "total_ms")
        values.setdefault((alias, run_type), []).append(total)
    return {key: sum(items) / len(items) for key, items in values.items()}


def _result_keys(results: Sequence[Mapping[str, Any]]) -> set[tuple[str, str, str]]:
    return {_result_key(result) for result in results}


def _result_key(result: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _read_nonempty_str(result, "question_id"),
        _read_nonempty_str(result, "alias"),
        _read_nonempty_str(result, "run_type"),
    )


def _assert_sanitized(data: object) -> None:
    for key, value in _walk_items(data):
        lowered = key.lower()
        if lowered in PROHIBITED_EXACT_KEYS:
            raise Gateway2GateError(
                f"prohibited serialized key: {key}",
                EXIT_SCHEMA_SANITIZATION,
            )
        if isinstance(value, str):
            for marker in PROHIBITED_VALUE_MARKERS:
                if marker in value:
                    raise Gateway2GateError(
                        "prohibited serialized value marker",
                        EXIT_SCHEMA_SANITIZATION,
                    )


def _walk_items(data: object) -> Iterable[tuple[str, object]]:
    if isinstance(data, Mapping):
        for key, value in data.items():
            yield str(key), value
            yield from _walk_items(value)
    elif isinstance(data, list | tuple):
        for item in data:
            yield from _walk_items(item)


def _read_nonempty_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Gateway2GateError(f"{key} must be a non-empty string", EXIT_SCHEMA_SANITIZATION)
    return value.strip()


def _read_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise Gateway2GateError(f"{key} must be numeric", EXIT_SCHEMA_SANITIZATION)
    return float(value)


def _pass_rate(summary: Mapping[str, Any]) -> float:
    total = _read_int(summary, "total_questions")
    if total <= 0:
        return 0.0
    return _read_int(summary, "passed") / total


def _read_int(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key)
    if not isinstance(value, int):
        raise ValueError(f"summary {key} must be an integer")
    return value


def _read_float(summary: Mapping[str, Any], key: str) -> float:
    value = summary.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"summary {key} must be numeric")
    return float(value)


def _read_float_mapping(summary: Mapping[str, Any], key: str) -> dict[str, float]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"summary {key} must be an object")
    output: dict[str, float] = {}
    for alias, latency in value.items():
        if not isinstance(alias, str):
            raise ValueError(f"summary {key} keys must be strings")
        if not isinstance(latency, int | float):
            raise ValueError(f"summary {key}.{alias} must be numeric")
        output[alias] = float(latency)
    return output


def _percent_delta(baseline: float, candidate: float) -> float:
    if baseline <= 0:
        return 0.0 if candidate <= 0 else 100.0
    return ((candidate - baseline) / baseline) * 100.0


if __name__ == "__main__":
    raise SystemExit(main())
