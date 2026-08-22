from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app.agent import LangChainAgent
from backend.app.database import Database
from backend.app.main import create_app


def main() -> int:
    # Validate configuration before constructing the API so failures are explicit.
    LangChainAgent._build_model()
    with TemporaryDirectory(prefix="yoko-live-smoke-") as directory:
        app = create_app(
            database=Database(Path(directory) / "smoke.db"),
            agent=LangChainAgent(),
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/chat",
                json={
                    "user_id": "demo-user",
                    "message": "请用一句简短的中文向我问好，不要创建提醒。",
                    "timezone": "Asia/Shanghai",
                },
            )

    payload = response.json()
    if response.status_code != 200:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    if payload["metrics"]["model_call_count"] < 1 or not payload["reply"].strip():
        print("真实模型响应缺少有效回复或模型调用记录。")
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "reply": payload["reply"],
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
