from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from src.config import Config
from src.repositories.search_usage_repo import SearchUsageRepository
from src.services.search_paid_budget_service import (
    SearchBudgetExceeded,
    SearchBudgetUnavailable,
    SearchPaidBudgetService,
)
from src.services.search_request_audit_service import audited_request_once
from src.services.search_usage_service import SearchUsageService
from src.storage import DatabaseManager


@pytest.fixture()
def paid_budget_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "paid-budget.db"))
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "paid-budget-test-secret")
    monkeypatch.setenv("SEARCH_ROUTING_MODE", "searxng_first_cn")
    monkeypatch.setenv("SEARXNG_BASE_URLS", "http://searxng:8080")
    monkeypatch.setenv("ANSPIRE_DAILY_WARNING_REQUESTS", "2")
    monkeypatch.setenv("ANSPIRE_DAILY_HARD_LIMIT_REQUESTS", "3")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    yield
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _config(*, warning: int, hard: int):
    return SimpleNamespace(
        search_routing_mode="searxng_first_cn",
        anspire_daily_warning_requests=warning,
        anspire_daily_hard_limit_requests=hard,
    )


def _response():
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.headers = {"content-type": "application/json"}
    response.text = '{"results": []}'
    response.json.return_value = {"results": []}
    return response


def test_warning_and_hard_limit_are_claimed_once_and_next_request_is_blocked(paid_budget_db):
    service = SearchPaidBudgetService(config_getter=lambda: _config(warning=2, hard=3))
    with patch.object(service, "_notify_async") as notify:
        assert service.reserve_before_request("Anspire")["reserved_requests"] == 1
        assert service.reserve_before_request("Anspire")["reserved_requests"] == 2
        assert service.reserve_before_request("Anspire")["reserved_requests"] == 3
        with pytest.raises(SearchBudgetExceeded, match="budget_blocked"):
            service.reserve_before_request("Anspire")

    assert notify.call_count == 2
    assert notify.call_args_list[0].kwargs == {"reserved": 2, "limit": 2, "hard": False}
    assert notify.call_args_list[1].kwargs == {"reserved": 3, "limit": 3, "hard": True}


def test_reservation_is_atomic_across_threads_and_persists_across_service_instances(paid_budget_db):
    config_getter = lambda: _config(warning=0, hard=10)

    def reserve_once(_index: int) -> bool:
        try:
            SearchPaidBudgetService(config_getter=config_getter).reserve_before_request("Anspire")
            return True
        except SearchBudgetExceeded:
            return False

    with patch.object(SearchPaidBudgetService, "_notify_async"):
        with ThreadPoolExecutor(max_workers=8) as pool:
            allowed = list(pool.map(reserve_once, range(24)))

    assert sum(allowed) == 10
    with pytest.raises(SearchBudgetExceeded):
        SearchPaidBudgetService(config_getter=config_getter).reserve_before_request("Anspire")


def test_budget_repository_failure_fails_closed_before_network():
    repo = Mock(spec=SearchUsageRepository)
    repo.reserve_paid_request.side_effect = RuntimeError("db unavailable")
    service = SearchPaidBudgetService(repo=repo, config_getter=lambda: _config(warning=2, hard=3))

    with pytest.raises(SearchBudgetUnavailable, match="budget_unavailable"):
        service.reserve_before_request("Anspire")


def test_budget_block_does_not_create_fake_physical_audit_row(paid_budget_db, monkeypatch):
    monkeypatch.setenv("ANSPIRE_DAILY_WARNING_REQUESTS", "0")
    monkeypatch.setenv("ANSPIRE_DAILY_HARD_LIMIT_REQUESTS", "1")
    Config.reset_instance()
    request_func = Mock(return_value=_response())

    with patch.object(SearchPaidBudgetService, "_notify_async"):
        audited_request_once(
            "GET",
            "https://plugin.anspire.cn/api/ntsearch/search",
            provider="Anspire",
            api_key="test-key",
            query="first",
            timeout=1,
            request_func=request_func,
        )
        with pytest.raises(SearchBudgetExceeded):
            audited_request_once(
                "GET",
                "https://plugin.anspire.cn/api/ntsearch/search",
                provider="Anspire",
                api_key="test-key",
                query="blocked",
                timeout=1,
                request_func=request_func,
            )

    dashboard = SearchUsageService().dashboard(
        from_dt=datetime(2000, 1, 1),
        to_dt=datetime.now(timezone.utc).replace(tzinfo=None),
        page=1,
        page_size=10,
    )
    assert request_func.call_count == 1
    assert dashboard["summary"]["physical_requests"] == 1
