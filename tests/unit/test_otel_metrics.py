from __future__ import annotations

from backend.observability import metrics


class FakeHistogram:
    def __init__(self) -> None:
        self.records: list[tuple[float, object]] = []

    def record(self, value: float, attributes: object | None = None) -> None:
        self.records.append((value, attributes))


def test_record_genai_duration_converts_ms_to_seconds(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeHistogram()
    monkeypatch.setattr(metrics, "_GENAI_OPERATION_DURATION", fake)
    monkeypatch.setattr(metrics, "setup_metrics", lambda: None)

    metrics.record_genai_operation_duration(1250.0, {"gen_ai.operation.name": "chat"})

    assert fake.records == [(1.25, {"gen_ai.operation.name": "chat"})]


def test_metric_names_are_public_constants() -> None:
    assert metrics.GENAI_OPERATION_DURATION_METRIC_NAME == "gen_ai.client.operation.duration"
    assert metrics.RETRIEVAL_OPERATION_DURATION_METRIC_NAME == "quimera.retrieval.operation.duration"


def test_record_retrieval_duration_keeps_ms(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeHistogram()
    monkeypatch.setattr(metrics, "_RETRIEVAL_OPERATION_DURATION", fake)
    monkeypatch.setattr(metrics, "setup_metrics", lambda: None)

    metrics.record_retrieval_duration(37.5, {"retrieval.result_count": 4})

    assert fake.records == [(37.5, {"retrieval.result_count": 4})]
