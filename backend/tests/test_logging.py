from __future__ import annotations

import json
import logging

from backend.app.logging_config import JsonFormatter


def test_json_formatter_only_emits_safe_whitelisted_context() -> None:
    record = logging.LogRecord(
        name="yoko.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-1"
    record.path = "/api/ready"
    record.secret = "must-not-be-logged"
    record.request_body = {"message": "must-not-be-logged"}

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "http_request"
    assert payload["request_id"] == "request-1"
    assert payload["path"] == "/api/ready"
    assert "secret" not in payload
    assert "request_body" not in payload
