import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.core import llm_metrics
from app.core.llm_metrics import measure_llm_call


def _reset():
    llm_metrics._histogram = None


def _histograms(reader: InMemoryMetricReader) -> list:
    data = reader.get_metrics_data()
    return [
        m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "llm_generation_duration_seconds"
    ]


def test_measure_llm_call_records_a_duration_sample(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(llm_metrics, "get_meter", lambda: provider.get_meter("test"))

    with measure_llm_call("gatekeeper"):
        pass

    histograms = _histograms(reader)
    assert len(histograms) == 1
    points = list(histograms[0].data.data_points)
    assert len(points) == 1
    assert points[0].count == 1
    assert points[0].attributes["agent"] == "gatekeeper"
    _reset()


def test_measure_llm_call_still_records_when_the_block_raises(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(llm_metrics, "get_meter", lambda: provider.get_meter("test"))

    with pytest.raises(ValueError), measure_llm_call("writer"):
        raise ValueError("boom")

    histograms = _histograms(reader)
    assert len(histograms) == 1
    assert histograms[0].data.data_points[0].attributes["agent"] == "writer"
    _reset()
