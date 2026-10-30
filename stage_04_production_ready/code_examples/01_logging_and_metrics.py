"""Standard-library observability example.

The functions return structured dictionaries so they can be tested without a
running Prometheus or OpenTelemetry service.
"""
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {"level": record.levelname, "message": record.getMessage(), "request_id": getattr(record, "request_id", "")},
            ensure_ascii=False,
        )


@contextmanager
def timed_metric(metrics: dict[str, float], name: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        metrics[name] = (time.perf_counter() - started) * 1000


def make_logger() -> logging.Logger:
    logger = logging.getLogger("stage4")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


if __name__ == "__main__":
    logger = make_logger()
    logger.info("service started", extra={"request_id": "demo-1"})
