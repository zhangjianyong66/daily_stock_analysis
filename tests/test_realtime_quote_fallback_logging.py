# -*- coding: utf-8 -*-
"""Regression tests for realtime quote fallback logging semantics."""

import asyncio
import importlib.util
import logging
import sys
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

try:
    json_repair_available = importlib.util.find_spec("json_repair") is not None
except ValueError:
    json_repair_available = "json_repair" in sys.modules

if not json_repair_available and "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

from data_provider.base import DataFetcherManager
from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote
from src.core.pipeline import StockAnalysisPipeline
from src.enums import ReportType
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


class _DummyFetcher:
    def __init__(self, name: str, priority: int, result=None, error: Exception | None = None):
        self.name = name
        self.priority = priority
        self._result = result
        self._error = error
        self.calls = 0

    def get_realtime_quote(self, *args, **kwargs):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def _make_quote(
    code: str = "600519",
    name: str = "贵州茅台",
    source: RealtimeSource = RealtimeSource.AKSHARE_EM,
    price: float = 1688.0,
    **overrides,
) -> UnifiedRealtimeQuote:
    return UnifiedRealtimeQuote(
        code=code,
        name=name,
        source=source,
        price=price,
        change_pct=1.2,
        **overrides,
    )


def _make_complete_quote(
    *,
    source: RealtimeSource,
    price: float = 1688.0,
) -> UnifiedRealtimeQuote:
    return _make_quote(
        source=source,
        price=price,
        volume=100,
        amount=1000.0,
        volume_ratio=1.2,
        turnover_rate=0.8,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=100000.0,
        circ_mv=80000.0,
        amplitude=2.5,
    )


def _make_pipeline(enable_realtime_quote: bool, realtime_quote=None) -> StockAnalysisPipeline:
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.config = SimpleNamespace(
        enable_realtime_quote=enable_realtime_quote,
        enable_chip_distribution=True,
        agent_mode=False,
        agent_skills=[],
        fundamental_stage_timeout_seconds=1.5,
        report_language="zh",
    )
    pipeline.fetcher_manager = MagicMock()
    pipeline.fetcher_manager.get_stock_name.return_value = "贵州茅台"
    pipeline.fetcher_manager.get_realtime_quote.return_value = realtime_quote
    pipeline.fetcher_manager.get_chip_distribution.return_value = None
    pipeline.fetcher_manager.get_fundamental_context.return_value = {
        "source_chain": [],
        "coverage": {},
    }
    pipeline.fetcher_manager.build_failed_fundamental_context.return_value = {
        "source_chain": [],
        "coverage": {},
    }
    pipeline.db = MagicMock()
    pipeline.db.save_fundamental_snapshot.return_value = None
    pipeline.db.get_data_range.return_value = []
    pipeline.db.get_analysis_context.return_value = {}
    pipeline.search_service = SimpleNamespace(is_available=False)
    pipeline.social_sentiment_service = SimpleNamespace(is_available=False)
    pipeline.query_source = "system"
    pipeline.trend_analyzer = MagicMock()
    pipeline.analyzer = MagicMock()
    pipeline.analyzer.analyze.return_value = None
    pipeline._attach_belong_boards_to_fundamental_context = MagicMock(side_effect=lambda code, ctx: ctx)
    pipeline._enhance_context = MagicMock(return_value={"realtime": {}})
    pipeline.save_context_snapshot = False
    return pipeline


@pytest.fixture(autouse=True)
def _clear_realtime_last_good_cache():
    cache = getattr(DataFetcherManager, "_realtime_last_good_cache", None)
    lock = getattr(DataFetcherManager, "_realtime_last_good_lock", None)
    if cache is not None:
        if lock is None:
            cache.clear()
        else:
            with lock:
                cache.clear()
    yield
    if cache is not None:
        if lock is None:
            cache.clear()
        else:
            with lock:
                cache.clear()


@patch("src.config.get_config")
def test_manager_retries_lightweight_connection_error_once(mock_get_config):
    expected = _make_quote(source=RealtimeSource.TENCENT)

    class FlakyTencent(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("temporary connection reset")
            return expected

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    tencent = FlakyTencent("AkshareFetcher", 0)
    manager = DataFetcherManager(fetchers=[tencent])

    quote = manager.get_realtime_quote("600519")

    assert quote is expected
    assert tencent.calls == 2


@patch("src.config.get_config")
def test_manager_does_not_retry_empty_quote(mock_get_config):
    expected = _make_quote(source=RealtimeSource.EFINANCE)
    tencent = _DummyFetcher("AkshareFetcher", 0, result=None)
    eastmoney = _DummyFetcher("EfinanceFetcher", 1, result=expected)
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,efinance",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[tencent, eastmoney])

    quote = manager.get_realtime_quote("600519")

    assert quote is expected
    assert tencent.calls == 1


@patch("src.config.get_config")
def test_manager_blocks_second_eastmoney_client_after_connection_failure(mock_get_config):
    efinance = _DummyFetcher(
        "EfinanceFetcher",
        0,
        error=ConnectionError("remote disconnected"),
    )
    akshare = _DummyFetcher("AkshareFetcher", 1, result=_make_quote())
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[efinance, akshare])

    quote = manager.get_realtime_quote("600519")

    assert quote is None
    assert efinance.calls == 1
    assert akshare.calls == 0


@patch("src.config.get_config")
def test_manager_allows_second_eastmoney_client_after_parse_failure(mock_get_config):
    expected = _make_quote()
    efinance = _DummyFetcher(
        "EfinanceFetcher",
        0,
        error=ValueError("provider payload changed"),
    )
    akshare = _DummyFetcher("AkshareFetcher", 1, result=expected)
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[efinance, akshare])

    quote = manager.get_realtime_quote("600519")

    assert quote is expected
    assert efinance.calls == 1
    assert akshare.calls == 1


@patch("src.config.get_config")
def test_manager_returns_same_day_last_good_as_stale_deep_copy(mock_get_config):
    live_quote = _make_quote(source=RealtimeSource.TENCENT)
    tencent = _DummyFetcher("AkshareFetcher", 0, result=live_quote)
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[tencent])

    first = manager.get_realtime_quote("600519")
    tencent._result = None
    second = manager.get_realtime_quote("600519")

    assert first is live_quote
    assert second is not first
    assert second.price == first.price
    assert second.source == RealtimeSource.TENCENT
    assert second.is_stale is True
    assert second.data_quality == "stale"
    assert second.cache_age_seconds is not None
    assert second.failure_summary == "tencent:empty"

    second.price = 1.0
    third = manager.get_realtime_quote("600519")
    assert third.price == 1688.0


@patch("src.config.get_config")
def test_manager_rejects_expired_last_good_quote(mock_get_config):
    tencent = _DummyFetcher(
        "AkshareFetcher",
        0,
        result=_make_quote(source=RealtimeSource.TENCENT),
    )
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[tencent])
    assert manager.get_realtime_quote("600519") is not None

    key = ("cn", "600519")
    with DataFetcherManager._realtime_last_good_lock:
        entry = DataFetcherManager._realtime_last_good_cache[key]
        DataFetcherManager._realtime_last_good_cache[key] = replace(
            entry,
            cached_at=time.monotonic() - 1801,
        )
    tencent._result = None

    assert manager.get_realtime_quote("600519") is None


@patch("src.config.get_config")
def test_manager_rejects_previous_market_day_last_good_quote(mock_get_config):
    tencent = _DummyFetcher(
        "AkshareFetcher",
        0,
        result=_make_quote(source=RealtimeSource.TENCENT),
    )
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[tencent])

    with patch.object(
        DataFetcherManager,
        "_realtime_market_date",
        side_effect=["2026-07-14", "2026-07-15"],
    ):
        assert manager.get_realtime_quote("600519") is not None
        tencent._result = None
        assert manager.get_realtime_quote("600519") is None


@patch("src.config.get_config")
def test_manager_stops_starting_sources_after_total_budget(mock_get_config):
    release = threading.Event()

    class BlockingTencent(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            release.wait(timeout=1)
            return None

    tencent = BlockingTencent("AkshareFetcher", 0)
    eastmoney = _DummyFetcher("EfinanceFetcher", 1, result=_make_quote())
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,efinance",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[tencent, eastmoney])

    try:
        with patch.object(DataFetcherManager, "_REALTIME_TOTAL_BUDGET_SECONDS", 0.02):
            started = time.monotonic()
            quote = manager.get_realtime_quote("600519")
    finally:
        release.set()

    assert quote is None
    assert time.monotonic() - started < 0.2
    assert tencent.calls == 1
    assert eastmoney.calls == 0


@patch("src.config.get_config")
def test_manager_last_good_cache_returns_independent_copies_concurrently(mock_get_config):
    tencent = _DummyFetcher(
        "AkshareFetcher",
        0,
        result=_make_quote(source=RealtimeSource.TENCENT),
    )
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[tencent])
    assert manager.get_realtime_quote("600519") is not None
    tencent._result = None

    results = []
    errors = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait(timeout=1)
            results.append(manager.get_realtime_quote("600519"))
        except Exception as exc:  # pragma: no cover - thread collection
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert len(results) == 8
    assert all(result.is_stale is True for result in results)
    assert len({id(result) for result in results}) == 8
    results[0].price = 1.0
    assert all(result.price == 1688.0 for result in results[1:])


@patch("src.config.get_config")
def test_manager_does_not_warn_when_fallback_source_succeeds(mock_get_config, caplog):
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("efinance timeout")),
            _DummyFetcher("AkshareFetcher", 1, result=_make_quote()),
        ]
    )

    with caplog.at_level(logging.INFO):
        quote = manager.get_realtime_quote("600519")

    assert quote is not None
    assert quote.name == "贵州茅台"
    assert quote.fetched_at is not None
    assert quote.fallback_from == "efinance"
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert "所有数据源均不可用" not in caplog.text


@patch("src.config.get_config")
def test_manager_supplement_does_not_mark_fallback_from(mock_get_config):
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
    )
    primary = _make_quote(source=RealtimeSource.EFINANCE)
    supplement = _make_quote(source=RealtimeSource.AKSHARE_EM, volume_ratio=1.7)
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=supplement),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is primary
    assert quote.fetched_at is not None
    assert quote.fallback_from is None
    assert quote.source == RealtimeSource.EFINANCE
    assert quote.volume_ratio == 1.7


@patch("src.config.get_config")
def test_manager_does_not_replace_existing_primary_with_later_hedge_pair(mock_get_config):
    primary = _make_quote(source=RealtimeSource.EFINANCE)
    supplement = _make_complete_quote(source=RealtimeSource.TENCENT)

    class SourceAwareAkshare(_DummyFetcher):
        def __init__(self):
            super().__init__("AkshareFetcher", 1)
            self.sources = []

        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            self.sources.append(kwargs.get("source"))
            return supplement

    akshare = SourceAwareAkshare()
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,tencent,akshare_sina",
        data_source_realtime_timeout_seconds=1,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            akshare,
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is primary
    assert quote.source == RealtimeSource.EFINANCE
    assert quote.fallback_from is None
    assert akshare.sources == ["tencent"]


@patch("src.config.get_config")
def test_manager_fallback_from_records_highest_priority_failed_source(mock_get_config):
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,tushare,akshare_em",
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("efinance timeout")),
            _DummyFetcher("TushareFetcher", 1, error=RuntimeError("tushare timeout")),
            _DummyFetcher("AkshareFetcher", 2, result=_make_quote()),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is not None
    assert quote.source == RealtimeSource.AKSHARE_EM
    assert quote.fallback_from == "efinance"
    assert quote.fetched_at is not None


@patch("src.config.get_config")
def test_manager_realtime_timeout_falls_back_to_next_source(mock_get_config):
    release_blocked = threading.Event()
    blocked_entered = threading.Event()
    fallback_quote = _make_quote(source=RealtimeSource.AKSHARE_EM)

    class BlockingFetcher(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            blocked_entered.set()
            release_blocked.wait(timeout=2)
            return None

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,efinance",
        data_source_realtime_timeout_seconds=0.01,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(
        fetchers=[
            BlockingFetcher("AkshareFetcher", 0),
            _DummyFetcher("EfinanceFetcher", 1, result=fallback_quote),
        ]
    )

    try:
        started = time.monotonic()
        quote = manager.get_realtime_quote("600519")
    finally:
        release_blocked.set()

    assert blocked_entered.wait(timeout=0.5)
    assert time.monotonic() - started < 1
    assert quote is fallback_quote
    assert quote.fallback_from == "tencent"


@patch("src.config.get_config")
def test_manager_lightweight_source_plan_uses_ten_second_hard_cap(mock_get_config):
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,akshare_sina,efinance",
        data_source_realtime_timeout_seconds=30,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[_DummyFetcher("AkshareFetcher", 0)])

    _, plans = manager._build_realtime_source_plans(
        "600519",
        "600519",
        mock_get_config.return_value,
    )

    assert [plan.timeout_seconds for plan in plans] == [10.0, 10.0, 8.0]


@patch("src.config.get_config")
def test_manager_starts_sina_hedge_while_tencent_is_still_running(mock_get_config):
    tencent_started = threading.Event()
    release_tencent = threading.Event()
    sina_started = threading.Event()
    sina_quote = _make_complete_quote(source=RealtimeSource.AKSHARE_SINA, price=1680.0)

    class SourceAwareAkshare(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            if kwargs.get("source") == "tencent":
                tencent_started.set()
                release_tencent.wait(timeout=1)
                return _make_complete_quote(source=RealtimeSource.TENCENT, price=1690.0)
            sina_started.set()
            return sina_quote

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,akshare_sina",
        data_source_realtime_timeout_seconds=1,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[SourceAwareAkshare("AkshareFetcher", 0)])

    try:
        with patch.object(DataFetcherManager, "_REALTIME_HEDGE_DELAY_SECONDS", 0.02):
            quote = manager.get_realtime_quote("600519")
    finally:
        release_tencent.set()

    assert tencent_started.wait(timeout=0.2)
    assert sina_started.wait(timeout=0.2)
    assert quote is sina_quote
    assert quote.source == RealtimeSource.AKSHARE_SINA
    assert quote.fallback_from == "tencent"


@patch("src.config.get_config")
def test_manager_fast_tencent_failure_starts_sina_without_waiting_for_hedge_delay(mock_get_config):
    sina_started = threading.Event()
    sina_quote = _make_complete_quote(source=RealtimeSource.AKSHARE_SINA)

    class SourceAwareAkshare(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            if kwargs.get("source") == "tencent":
                return None
            sina_started.set()
            return sina_quote

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,akshare_sina",
        data_source_realtime_timeout_seconds=1,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[SourceAwareAkshare("AkshareFetcher", 0)])

    started = time.monotonic()
    with patch.object(DataFetcherManager, "_REALTIME_HEDGE_DELAY_SECONDS", 0.5):
        quote = manager.get_realtime_quote("600519")

    assert time.monotonic() - started < 0.2
    assert sina_started.is_set()
    assert quote is sina_quote
    assert quote.fallback_from == "tencent"


def test_manager_same_physical_scope_does_not_spawn_calls_behind_late_worker():
    release = threading.Event()
    entered = threading.Event()

    class BlockingFetcher(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            entered.set()
            release.wait(timeout=1)
            return None

    fetcher = BlockingFetcher("AkshareFetcher", 0)
    manager = DataFetcherManager(fetchers=[fetcher])

    try:
        with pytest.raises(TimeoutError):
            manager._call_fetcher_method(
                fetcher,
                "get_realtime_quote",
                "600519",
                timeout_seconds=0.01,
                call_scope="tencent",
            )
        assert entered.wait(timeout=0.2)
        with pytest.raises(TimeoutError):
            manager._call_fetcher_method(
                fetcher,
                "get_realtime_quote",
                "600519",
                timeout_seconds=0.01,
                call_scope="tencent",
            )
        assert fetcher.calls == 1
    finally:
        release.set()


@patch("src.config.get_config")
def test_manager_late_tencent_result_does_not_overwrite_sina_last_good(mock_get_config):
    release_tencent = threading.Event()
    tencent_finished = threading.Event()
    sina_quote = _make_complete_quote(source=RealtimeSource.AKSHARE_SINA, price=1680.0)

    class SourceAwareAkshare(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            if kwargs.get("source") == "tencent":
                release_tencent.wait(timeout=1)
                tencent_finished.set()
                return _make_complete_quote(source=RealtimeSource.TENCENT, price=1690.0)
            return sina_quote

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,akshare_sina",
        data_source_realtime_timeout_seconds=1,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[SourceAwareAkshare("AkshareFetcher", 0)])

    with patch.object(DataFetcherManager, "_REALTIME_HEDGE_DELAY_SECONDS", 0.01):
        quote = manager.get_realtime_quote("600519")
    release_tencent.set()
    assert tencent_finished.wait(timeout=0.5)

    assert quote is sina_quote
    with DataFetcherManager._realtime_last_good_lock:
        cached = DataFetcherManager._realtime_last_good_cache[("cn", "600519")].quote
    assert cached.source == RealtimeSource.AKSHARE_SINA
    assert cached.price == 1680.0


@patch("src.config.get_config")
def test_manager_hedge_diagnostics_show_both_starts_and_sina_winner(mock_get_config):
    release_tencent = threading.Event()
    events = []
    sina_quote = _make_complete_quote(source=RealtimeSource.AKSHARE_SINA)

    class SourceAwareAkshare(_DummyFetcher):
        def get_realtime_quote(self, *args, **kwargs):
            self.calls += 1
            if kwargs.get("source") == "tencent":
                release_tencent.wait(timeout=1)
                return _make_complete_quote(source=RealtimeSource.TENCENT)
            return sina_quote

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="tencent,akshare_sina",
        data_source_realtime_timeout_seconds=1,
        realtime_cache_ttl=600,
    )
    manager = DataFetcherManager(fetchers=[SourceAwareAkshare("AkshareFetcher", 0)])
    token = activate_run_diagnostic_context(trace_id="trace-realtime-hedge", event_sink=events.append)

    try:
        with patch.object(DataFetcherManager, "_REALTIME_HEDGE_DELAY_SECONDS", 0.01):
            quote = manager.get_realtime_quote("600519")
        snapshot = current_diagnostic_snapshot()
    finally:
        release_tencent.set()
        reset_run_diagnostic_context(token)

    started_events = [event for event in events if event["type"] == "provider_run_started"]
    assert len(started_events) == 2
    assert [event["metadata"]["route_source"] for event in started_events] == [
        "tencent",
        "akshare_sina",
    ]
    assert quote is sina_quote
    assert len(snapshot["provider_runs"]) == 1
    winner = snapshot["provider_runs"][0]
    assert winner["success"] is True
    assert winner["route_source"] == "akshare_sina"
    assert winner["physical_source"] == "sina"
    assert winner["fallback_from"] == "tencent"


@patch("src.config.get_config")
def test_manager_drops_invalid_provider_timestamp_before_return(mock_get_config):
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance",
        realtime_cache_ttl=600,
    )
    raw_quote = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp="not-a-date",
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=raw_quote),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is raw_quote
    assert quote.fetched_at is not None
    assert quote.provider_timestamp is None
    assert quote.stale_seconds is None
    assert quote.is_stale is None


def test_pipeline_warns_once_when_all_realtime_sources_fail(caplog):
    pipeline = _make_pipeline(enable_realtime_quote=True, realtime_quote=None)

    with caplog.at_level(logging.INFO):
        result = pipeline.analyze_stock("600519", ReportType.SIMPLE, "q1")

    assert result is None
    pipeline.fetcher_manager.get_stock_name.assert_called_once_with("600519", allow_realtime=False)
    pipeline.fetcher_manager.get_realtime_quote.assert_called_once_with("600519", log_final_failure=False)
    downgrade_logs = [
        record.message
        for record in caplog.records
        if "历史收盘价继续分析" in record.message
    ]
    assert downgrade_logs == ["贵州茅台(600519) 所有实时行情数据源均不可用，已降级为历史收盘价继续分析"]


@patch("src.config.get_config")
def test_event_monitor_keeps_manager_failure_summary_for_direct_quote_call(mock_get_config, caplog):
    from src.agent.events import EventMonitor, PriceAlert

    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance",
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("efinance timeout")),
        ]
    )
    monitor = EventMonitor()
    rule = PriceAlert(stock_code="600519", direction="above", price=1800.0)

    async def _run_inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("data_provider.DataFetcherManager", return_value=manager), patch(
        "src.agent.events.asyncio.to_thread", new=_run_inline
    ), caplog.at_level(logging.INFO):
        result = asyncio.run(monitor._check_price(rule))

    assert result is None
    assert "[实时行情] 600519 所有数据源均失败: [efinance] 失败: efinance timeout" in caplog.text


def test_pipeline_logs_disabled_realtime_once_without_fetching_quote(caplog):
    pipeline = _make_pipeline(enable_realtime_quote=False, realtime_quote=_make_quote())

    with caplog.at_level(logging.INFO):
        result = pipeline.analyze_stock("600519", ReportType.SIMPLE, "q1")

    assert result is None
    pipeline.fetcher_manager.get_stock_name.assert_called_once_with("600519", allow_realtime=False)
    pipeline.fetcher_manager.get_realtime_quote.assert_not_called()
    downgrade_logs = [
        record.message
        for record in caplog.records
        if "历史收盘价继续分析" in record.message
    ]
    assert downgrade_logs == ["贵州茅台(600519) 实时行情已禁用，使用历史收盘价继续分析"]
