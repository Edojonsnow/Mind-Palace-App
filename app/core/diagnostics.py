"""Allow-listed operational events. Never record request or exception content."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("mind_palace.diagnostics")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def emit_event(
    event: str,
    *,
    method: str | None = None,
    route: str | None = None,
    status_code: int | None = None,
    duration_ms: float | None = None,
    error_type: str | None = None,
    job_id: str | None = None,
    operation: str | None = None,
) -> None:
    fields = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "request_id": request_id_context.get(),
        "method": method,
        "route": route,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "error_type": error_type,
        "job_id": job_id,
        "operation": operation,
    }
    level = logging.ERROR if error_type or (status_code or 0) >= 500 else logging.INFO
    payload = {key: value for key, value in fields.items() if value is not None}
    logger.log(level, json.dumps(payload))


def normalize_request_id(value: str | None) -> str:
    try:
        return str(UUID(value or ""))
    except ValueError:
        return str(uuid4())


class RequestDiagnosticsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = normalize_request_id(headers.get(b"x-request-id", b"").decode("latin-1"))
        context_token = request_id_context.set(request_id)
        started_at = perf_counter()
        status_code = 500
        response_started = False
        error_type = None

        async def send_with_reference(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                response_headers = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message = {**message, "headers": [
                    *response_headers, (b"x-request-id", request_id.encode("ascii")),
                ]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_reference)
        except Exception as error:
            error_type = type(error).__name__
            status_code = 500
            if response_started:
                # A partially sent stream cannot be replaced with a JSON response.
                raise RuntimeError("Response interrupted; see request diagnostics") from None
            response = JSONResponse(
                {"detail": "Something went wrong. Please try again.", "request_id": request_id},
                status_code=500,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send_with_reference)
        finally:
            route = scope.get("route")
            route_template = getattr(route, "path", "(unmatched)")
            method = scope["method"]
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                method = "OTHER"
            if route_template not in {"/health", "/version"} or status_code >= 400:
                emit_event(
                    "http.request", method=method, route=route_template,
                    status_code=status_code,
                    duration_ms=round((perf_counter() - started_at) * 1000, 2),
                    error_type=error_type,
                )
            request_id_context.reset(context_token)


@contextmanager
def worker_operation(operation: str, job_id: str | None = None) -> Iterator[None]:
    started_at = perf_counter()
    try:
        yield
    except Exception as error:
        emit_event(
            "worker.failed", operation=operation, job_id=job_id,
            error_type=type(error).__name__,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        # RQ records and logs uncaught exceptions; do not give it private error messages.
        raise RuntimeError("Worker operation failed; see safe diagnostics") from None
    else:
        emit_event(
            "worker.finished", operation=operation, job_id=job_id,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
