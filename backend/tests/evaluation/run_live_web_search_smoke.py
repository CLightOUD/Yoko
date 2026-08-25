from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app.agent import LangChainAgent
from backend.app.database import Database
from backend.app.main import create_app


def main() -> int:
    LangChainAgent._build_model()
    with TemporaryDirectory(prefix="yoko-live-web-search-") as directory:
        app = create_app(
            database=Database(Path(directory) / "web-search.db"),
            agent=LangChainAgent(),
        )
        with TestClient(
            app,
            raise_server_exceptions=False,
            headers={"Origin": "http://127.0.0.1:5173"},
        ) as client:
            registered = client.post(
                "/api/auth/register",
                json={
                    "username": "live_web_search_user",
                    "password": "live-web-search-password-2026",
                    "display_name": "联网冒烟用户",
                    "timezone": "Asia/Shanghai",
                },
            )
            if registered.status_code != 201:
                print(json.dumps(registered.json(), ensure_ascii=False, indent=2))
                return 1
            response = client.post(
                "/api/chat",
                json={
                    "message": "请联网查询 Python 官方文档主页，简单说明并给出来源。",
                    "timezone": "Asia/Shanghai",
                },
            )

    payload = response.json()
    if response.status_code != 200:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    web_calls = [
        call
        for call in payload["tool_calls"]
        if call["tool_name"] == "web_search"
    ]
    if (
        payload["status"] != "completed"
        or len(web_calls) != 1
        or web_calls[0]["status"] != "success"
        or not payload["sources"]
    ):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "reply": payload["reply"],
                "web_search": web_calls[0],
                "sources": payload["sources"],
                "model_call_count": payload["metrics"]["model_call_count"],
                "input_tokens": payload["metrics"]["input_tokens"],
                "output_tokens": payload["metrics"]["output_tokens"],
                "total_ms": payload["metrics"]["total_ms"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
