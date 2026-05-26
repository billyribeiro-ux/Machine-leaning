"""
Request context middleware — generates a correlation ID for every inbound
request so that all log lines emitted while handling it can be traced back
to a single origin.

The correlation ID is:
  1. Read from the ``X-Request-ID`` header if the caller provides one.
  2. Generated as a short UUID-4 prefix otherwise.
  3. Stored in a :class:`contextvars.ContextVar` so any logger in the call
     chain can access it without explicit plumbing.
  4. Returned to the caller in the ``X-Request-ID`` response header.
"""

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("revolution.api")


class _RequestIDFilter(logging.Filter):
    """Injects ``request_id`` into every LogRecord automatically."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return True


_filter_installed = False


def install_request_id_filter() -> None:
    """Attach the filter to the root ``revolution`` logger once."""
    global _filter_installed
    if _filter_installed:
        return
    root = logging.getLogger("revolution")
    root.addFilter(_RequestIDFilter())
    _filter_installed = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Adds correlation ID, request logging, and response-time header."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request_id_var.set(rid)

        start = time.perf_counter()

        logger.info(
            "%s %s",
            request.method,
            request.url.path,
            extra={"request_id": rid},
        )

        response: Response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": rid},
        )

        return response
