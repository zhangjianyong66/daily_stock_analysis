from __future__ import annotations

import json

from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.schemas.search_usage import SearchAuditContext, search_audit_scope
from src.services.search_request_audit_service import audited_request_once
from src.storage import DatabaseManager


def test_search_detail_and_exports_require_enabled_logged_in_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "search-api.db"))
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "api-test-secret")
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    auth._auth_enabled = False

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"results":[]}'

        @staticmethod
        def json():
            return {"results": []}

    with search_audit_scope(SearchAuditContext(call_source="analysis")):
        audited_request_once(
            "GET", "https://example.com/search", provider="Example", api_key="key", query="query",
            timeout=1, request_func=lambda *_args, **_kwargs: Response(),
        )

    app = create_app(static_dir=tmp_path)
    client = TestClient(app)
    assert client.get("/api/v1/usage/search/calls/1").status_code == 403

    auth._auth_enabled = True
    session = auth.create_session()
    assert session
    client.cookies.set(auth.COOKIE_NAME, session)
    detail = client.get("/api/v1/usage/search/calls/1")
    assert detail.status_code == 200
    assert detail.json()["request_snapshot"]["url"] == "https://example.com/search"
    csv_response = client.get("/api/v1/usage/search/export.csv?period=all")
    assert csv_response.status_code == 200
    assert "request_snapshot" not in csv_response.text
    json_response = client.get("/api/v1/usage/search/calls/1/export.json")
    assert json_response.status_code == 200
    assert json.loads(json_response.text)["response_snapshot"]["body"]["results"] == []

    DatabaseManager.reset_instance()
    Config.reset_instance()
