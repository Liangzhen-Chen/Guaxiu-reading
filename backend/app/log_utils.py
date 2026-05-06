"""
Logging utilities: request_id contextvar, JSON formatter, error tracking.
No external dependencies -- stdlib only.
"""
import json
import logging
import time
import uuid
from collections import deque
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Retrieve the current request_id from context."""
    return request_id_ctx.get()


def generate_request_id() -> str:
    """Generate a compact hex UUID for a new request."""
    return uuid.uuid4().hex


# ── Global error ring-buffer (last 1000 5xx responses) ──
# Each entry: (unix_timestamp, method, path, status_code)
error_log: deque = deque(maxlen=1000)


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    All structured fields (request_id, method, path, status_code, duration_ms,
    user_id, event, model, prompt_tokens, completion_tokens, estimated_cost_usd)
    are injected as extra= dict entries on the LogRecord and serialized into the
    JSON output.

    Example output:
    {"timestamp":"2026-05-06T10:30:00.123Z","level":"INFO","logger":"app.main",
     "request_id":"a1b2c3d4","message":"request","method":"POST",
     "path":"/api/reading/chat","status_code":200,"duration_ms":1520.45}
    """

    _EXTRA_FIELDS = (
        "user_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "event",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "estimated_cost_usd",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self._fmt_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", get_request_id()),
            "message": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            val = getattr(record, field, None)
            if val is not None:
                entry[field] = val
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)

    @staticmethod
    def _fmt_timestamp(ts: float) -> str:
        t = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))
        return f"{t}.{int((ts % 1) * 1000):03d}Z"


def setup_logging() -> None:
    """Configure the root logger with a JSON stdout handler.

    Call once at application startup (in main.py).
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove any pre-existing handlers (e.g. uvicorn default)
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Suppress verbose third-party loggers
    for name in ("httpx", "httpcore", "openai", "httpx._client", "httpx._config"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Keep uvicorn access log handler if present (we're replacing root, not uvicorn's)
    # Uvicorn writes its own access log via its own logger which we don't touch.
    logging.getLogger("uvicorn.access").propagate = False
