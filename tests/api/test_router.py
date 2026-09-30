from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_query_endpoint_streams_steps_and_result():
    fake_final_state = {
        "final_answer": "Paris [geo.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_final_state

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"})

    assert response.status_code == 200
    assert "event: step" in response.text
    assert "event: result" in response.text
    assert "Paris" in response.text


def test_query_endpoint_rejects_empty_query():
    client = TestClient(app)
    response = client.post("/query", json={"query": ""})

    assert response.status_code == 422
