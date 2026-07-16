from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock, patch

import pytest
import requests
from tenacity import wait_none

from src.config import Config
from src.schemas.search_usage import SearchAuditContext, search_audit_scope
from src.services.search_request_audit_service import audited_request_once
from src.services.search_usage_service import SearchUsageService
from src.storage import DatabaseManager
from src.repositories.search_usage_repo import SearchUsageRepository


@pytest.fixture()
def search_usage_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "search-usage.db"))
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "search-usage-test-secret")
    monkeypatch.setenv("ANSPIRE_API_KEYS", "test-anspire-key")
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    yield
    DatabaseManager.reset_instance()
    Config.reset_instance()


def fake_response(status: int, payload, text: str = ""):
    response = Mock(spec=requests.Response)
    response.status_code = status
    response.headers = {"content-type": "application/json", "x-request-id": "req-test"}
    response.text = text or json.dumps(payload, ensure_ascii=False)
    response.json.return_value = payload
    return response


def test_anspire_balance_401_is_persisted_as_quota_exhausted_and_redacted(search_usage_db):
    response = fake_response(
        401,
        {
            "message": "可用免费额度 0.00，充值余额 0.00；key=test-anspire-key",
            "authorization": "Bearer leaked-secret",
        },
    )
    with search_audit_scope(
        SearchAuditContext(call_source="analysis", operation="comprehensive", stock_code="159516")
    ):
        audited_request_once(
            "GET",
            "https://plugin.anspire.cn/api/ntsearch/search",
            provider="Anspire",
            api_key="test-anspire-key",
            query="半导体设备ETF 业绩预期",
            headers={"Authorization": "Bearer test-anspire-key"},
            params={"query": "半导体设备ETF 业绩预期", "api_key": "test-anspire-key"},
            timeout=1,
            request_func=lambda *_args, **_kwargs: response,
        )

    detail = SearchUsageService().get_call_detail(1)
    assert detail is not None
    assert detail["error_category"] == "quota_exhausted"
    serialized = json.dumps(detail, ensure_ascii=False)
    assert "test-anspire-key" not in serialized
    assert "leaked-secret" not in serialized
    assert detail["request_snapshot"]["query_params"]["query"] == "半导体设备ETF 业绩预期"


def test_tenacity_retries_create_three_physical_rows(search_usage_db):
    from src.search_service import _get_with_retry

    success = fake_response(200, {"results": []})
    effects = [requests.ConnectionError("one"), requests.ConnectionError("two"), success]
    context = SearchAuditContext(call_source="analysis", operation="retry-test")
    with patch("src.search_service.requests.get", side_effect=effects):
        with search_audit_scope(context):
            retried = _get_with_retry.retry_with(wait=wait_none())
            response = retried(
                "https://plugin.anspire.cn/api/ntsearch/search",
                headers={"Authorization": "Bearer test-anspire-key"},
                params={"query": "retry"},
                timeout=1,
                provider="Anspire",
                api_key="test-anspire-key",
                query="retry",
            )
    assert response.status_code == 200
    dashboard = SearchUsageService().dashboard(
        from_dt=datetime(2000, 1, 1),
        to_dt=datetime.now(timezone.utc).replace(tzinfo=None),
        page=1,
        page_size=10,
    )
    assert dashboard["summary"]["physical_requests"] == 3
    attempts = sorted(item["physical_attempt"] for item in dashboard["calls"]["items"])
    assert attempts == [1, 2, 3]
    assert dashboard["summary"]["business_searches"] == 1


def test_snapshot_truncation_records_original_size_and_sha(search_usage_db, monkeypatch):
    from src.services import search_request_audit_service as audit

    monkeypatch.setattr(audit, "RESPONSE_SNAPSHOT_MAX_BYTES", 256)
    response = fake_response(200, {"results": [{"content": "x" * 2000}]})
    audited_request_once(
        "GET",
        "https://example.com/search",
        provider="Example",
        api_key="key",
        query="query",
        timeout=1,
        request_func=lambda *_args, **_kwargs: response,
    )
    detail = SearchUsageService().get_call_detail(1)
    assert detail is not None
    assert detail["response_truncated"] is True
    assert detail["response_size_bytes"] > 256
    assert len(detail["response_sha256"]) == 64


def test_fault_notification_claim_has_24_hour_cooldown_and_one_recovery(search_usage_db):
    repo = SearchUsageRepository()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fault, activated = repo.record_fault_event(
        provider="Anspire",
        key_fingerprint="fingerprint",
        category="quota_exhausted",
        occurred_at=now,
        call_id=1,
        error_summary="余额不足",
        immediate=True,
        transient_window=timedelta(minutes=10),
        threshold=3,
    )
    assert activated is True
    assert repo.claim_notification(fault["id"], recovery=False, now=now, cooldown=timedelta(hours=24)) is True
    assert repo.claim_notification(fault["id"], recovery=False, now=now, cooldown=timedelta(hours=24)) is False
    repo.resolve_faults("Anspire", "fingerprint", now + timedelta(minutes=1))
    assert repo.claim_notification(fault["id"], recovery=True, now=now, cooldown=timedelta(hours=24)) is True
    assert repo.claim_notification(fault["id"], recovery=True, now=now, cooldown=timedelta(hours=24)) is False


def test_success_clears_inactive_transient_failure_counter(search_usage_db):
    repo = SearchUsageRepository()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for index in range(2):
        fault, activated = repo.record_fault_event(
            provider="Anspire",
            key_fingerprint="fingerprint",
            category="timeout",
            occurred_at=now + timedelta(seconds=index),
            call_id=index + 1,
            error_summary="timeout",
            immediate=False,
            transient_window=timedelta(minutes=10),
            threshold=3,
        )
        assert activated is False
    assert fault["consecutive_count"] == 2
    assert repo.resolve_faults("Anspire", "fingerprint", now + timedelta(seconds=3)) == []
    fault, activated = repo.record_fault_event(
        provider="Anspire",
        key_fingerprint="fingerprint",
        category="timeout",
        occurred_at=now + timedelta(seconds=4),
        call_id=4,
        error_summary="timeout",
        immediate=False,
        transient_window=timedelta(minutes=10),
        threshold=3,
    )
    assert activated is False
    assert fault["consecutive_count"] == 1
