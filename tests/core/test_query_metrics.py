from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.core import query_metrics
from app.core.query_metrics import record_query_outcome, record_retry_count


def _reset():
    query_metrics._outcome_counter = None
    query_metrics._retry_histogram = None


def _metrics(reader: InMemoryMetricReader, name: str) -> list:
    data = reader.get_metrics_data()
    return [
        m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == name
    ]


def test_record_query_outcome_increments_the_labeled_counter(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(query_metrics, "get_meter", lambda: provider.get_meter("test"))

    record_query_outcome("completed")
    record_query_outcome("completed")
    record_query_outcome("error")

    counters = _metrics(reader, "agentic_ai_query_outcome_total")
    assert len(counters) == 1
    by_outcome = {p.attributes["outcome"]: p.value for p in counters[0].data.data_points}
    assert by_outcome == {"completed": 2, "error": 1}
    _reset()


def test_record_retry_count_records_a_sample(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(query_metrics, "get_meter", lambda: provider.get_meter("test"))

    record_retry_count(2)

    histograms = _metrics(reader, "agentic_ai_verifier_retry_count")
    assert len(histograms) == 1
    points = list(histograms[0].data.data_points)
    assert len(points) == 1
    assert points[0].count == 1
    assert points[0].sum == 2
    _reset()
