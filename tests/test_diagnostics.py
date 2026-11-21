import json
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.diagnostics import logger, request_id_context, worker_operation
from app.main import create_app


@pytest.fixture
def diagnostic_records(caplog):
    logger.addHandler(caplog.handler)
    yield caplog
    logger.removeHandler(caplog.handler)


def test_request_reference_is_preserved_and_private_inputs_are_not_logged(diagnostic_records):
    app = create_app()

    @app.post("/diagnostic-test/{item}")
    def endpoint(item: str):
        return {"ok": True}

    reference = "00000000-0000-4000-8000-000000000001"
    response = TestClient(app).post(
        "/diagnostic-test/private-path?q=private-search",
        headers={"X-Request-ID": reference, "Authorization": "Bearer private-token"},
        json={"body": "private-thought"},
    )
    assert response.headers["X-Request-ID"] == reference
    event = json.loads(diagnostic_records.records[-1].message)
    assert event["request_id"] == reference
    assert event["route"] == "/diagnostic-test/{item}"
    assert event["status_code"] == 200
    assert event["duration_ms"] >= 0
    assert "private-" not in diagnostic_records.text
    assert request_id_context.get() is None


@pytest.mark.parametrize("reference", ["", "not-a-uuid", "private-thought" * 100])
def test_untrusted_request_references_are_replaced(reference):
    response = TestClient(create_app()).get("/health", headers={"X-Request-ID": reference})
    assert str(UUID(response.headers["X-Request-ID"])) == response.headers["X-Request-ID"]
    assert response.headers["X-Request-ID"] != reference


def test_unhandled_error_is_sanitized_and_cors_headers_survive(diagnostic_records):
    app = create_app()

    @app.get("/diagnostic-error")
    def endpoint():
        raise RuntimeError("private-database-url private-thought")

    response = TestClient(app).get("/diagnostic-error", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "X-Request-ID" in response.headers["Access-Control-Expose-Headers"]
    assert "private-" not in response.text + diagnostic_records.text
    event = json.loads(diagnostic_records.records[-1].message)
    assert event["error_type"] == "RuntimeError"
    assert event["status_code"] == 500


def test_http_errors_preserve_retry_headers(diagnostic_records):
    app = create_app()

    @app.get("/diagnostic-limit")
    def endpoint():
        raise HTTPException(429, "Try again later.", headers={"Retry-After": "10"})

    response = TestClient(app).get("/diagnostic-limit")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "10"
    assert response.json() == {"detail": "Try again later."}
    assert response.headers["X-Request-ID"]


def test_unmatched_paths_are_not_recorded(diagnostic_records):
    response = TestClient(create_app()).get("/private-path?q=private-query")
    assert response.status_code == 404
    assert json.loads(diagnostic_records.records[-1].message)["route"] == "(unmatched)"
    assert "private-" not in diagnostic_records.text


def test_worker_failure_omits_private_exception_content(diagnostic_records):
    with pytest.raises(RuntimeError, match="see safe diagnostics") as caught:
        with worker_operation("test_operation", "00000000-0000-4000-8000-000000000001"):
            raise ValueError("private-provider-response")
    event = json.loads(diagnostic_records.records[-1].message)
    assert event["event"] == "worker.failed"
    assert event["error_type"] == "ValueError"
    assert "private-" not in diagnostic_records.text + str(caught.value)
    assert caught.value.__suppress_context__ is True
