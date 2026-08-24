from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import Database
from backend.app.main import create_app


def test_frontend_is_served_without_shadowing_backend_routes(tmp_path: Path) -> None:
    frontend_dist = tmp_path / "dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text(
        "<!doctype html><title>Yoko deployment test</title>",
        encoding="utf-8",
    )
    app = create_app(
        database=Database(tmp_path / "static.db"),
        frontend_dist=frontend_dist,
    )

    with TestClient(app) as client:
        homepage = client.get("/")
        health = client.get("/api/health")
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")

    assert homepage.status_code == 200
    assert "Yoko deployment test" in homepage.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
    assert openapi.status_code == 200
    assert "/api/health" in openapi.json()["paths"]


def test_backend_starts_when_frontend_build_is_missing(tmp_path: Path) -> None:
    app = create_app(
        database=Database(tmp_path / "api-only.db"),
        frontend_dist=tmp_path / "missing-dist",
    )

    with TestClient(app) as client:
        homepage = client.get("/")
        health = client.get("/api/health")

    assert homepage.status_code == 404
    assert health.status_code == 200
