from dataclasses import dataclass

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.core import llm_usage_metrics
from app.core.llm_usage_metrics import record_llm_usage


def _reset():
    llm_usage_metrics._tokens_counter = None
    llm_usage_metrics._cost_counter = None


def _metrics(reader: InMemoryMetricReader, name: str) -> list:
    data = reader.get_metrics_data()
    return [m for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics if m.name == name]


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


class _FakeResponse:
    def __init__(self, model_name: str | None):
        self.model_name = model_name


class _FakeResult:
    def __init__(self, input_tokens: int, output_tokens: int, model_name: str | None):
        self.usage = _FakeUsage(input_tokens, output_tokens)
        self.response = _FakeResponse(model_name)


def test_record_llm_usage_records_tokens_for_a_priced_model(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(llm_usage_metrics, "get_meter", lambda: provider.get_meter("test"))

    record_llm_usage("gatekeeper", _FakeResult(100, 50, "google/gemma-3-27b-it"))

    token_points = {
        (p.attributes["token_type"]): p.value
        for m in _metrics(reader, "agentic_ai_llm_tokens_total")
        for p in m.data.data_points
    }
    assert token_points == {"input": 100, "output": 50}
    _reset()


def test_record_llm_usage_computes_cost_for_a_priced_model(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(llm_usage_metrics, "get_meter", lambda: provider.get_meter("test"))

    record_llm_usage("writer", _FakeResult(1_000_000, 1_000_000, "google/gemma-3-27b-it"))

    cost_points = list(_metrics(reader, "agentic_ai_llm_cost_usd_total")[0].data.data_points)
    assert len(cost_points) == 1
    assert cost_points[0].value == 0.00000008 * 1_000_000 + 0.00000045 * 1_000_000
    _reset()


def test_record_llm_usage_records_zero_cost_for_an_unpriced_model(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(llm_usage_metrics, "get_meter", lambda: provider.get_meter("test"))

    record_llm_usage("verifier", _FakeResult(100, 50, "some/unlisted-model"))

    cost_points = list(_metrics(reader, "agentic_ai_llm_cost_usd_total")[0].data.data_points)
    assert cost_points[0].value == 0.0
    _reset()


def test_record_llm_usage_falls_back_to_unknown_model_when_none_found(monkeypatch):
    _reset()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(llm_usage_metrics, "get_meter", lambda: provider.get_meter("test"))

    record_llm_usage("gatekeeper", _FakeResult(10, 5, None))

    points = list(_metrics(reader, "agentic_ai_llm_tokens_total")[0].data.data_points)
    assert all(p.attributes["model"] == "unknown" for p in points)
    _reset()
