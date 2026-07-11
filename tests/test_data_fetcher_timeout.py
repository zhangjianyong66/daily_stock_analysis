# -*- coding: utf-8 -*-
"""Regression tests for DataFetcherManager caller-side timeout fallback."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from data_provider.base import DataFetcherManager


class _Fetcher:
    def __init__(self, name: str, priority: int):
        self.name = name
        self.priority = priority


class _BlockingNameFetcher(_Fetcher):
    def __init__(self, name: str, priority: int, release_event: threading.Event, entered_event: threading.Event):
        super().__init__(name, priority)
        self._release_event = release_event
        self._entered_event = entered_event

    def get_stock_name(self, stock_code: str):
        self._entered_event.set()
        self._release_event.wait(timeout=2)
        return ""


class _NameFetcher(_Fetcher):
    def __init__(self, name: str, priority: int, stock_name: str):
        super().__init__(name, priority)
        self._stock_name = stock_name

    def get_stock_name(self, stock_code: str):
        return self._stock_name


class _BlockingDailyFetcher(_Fetcher):
    def __init__(self, name: str, priority: int, release_event: threading.Event, entered_event: threading.Event):
        super().__init__(name, priority)
        self._release_event = release_event
        self._entered_event = entered_event

    def get_daily_data(self, **kwargs):
        self._entered_event.set()
        self._release_event.wait(timeout=2)
        return pd.DataFrame()


class _DailyFetcher(_Fetcher):
    def get_daily_data(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "date": "2026-07-10",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "volume": 1000,
                    "amount": 10000,
                    "pct_chg": 1.0,
                }
            ]
        )


@patch("src.config.get_config")
def test_stock_name_timeout_falls_back_to_next_provider(mock_get_config):
    release_blocked = threading.Event()
    blocked_entered = threading.Event()
    mock_get_config.return_value = SimpleNamespace(data_source_stock_name_timeout_seconds=0.01)
    manager = DataFetcherManager(
        fetchers=[
            _BlockingNameFetcher("BlockingFetcher", 0, release_blocked, blocked_entered),
            _NameFetcher("FallbackFetcher", 1, "贵州茅台"),
        ]
    )

    try:
        started = time.monotonic()
        name = manager.get_stock_name("TESTNAME", allow_realtime=False)
    finally:
        release_blocked.set()

    assert blocked_entered.wait(timeout=0.5)
    assert time.monotonic() - started < 1
    assert name == "贵州茅台"


@patch("src.config.get_config")
def test_daily_data_timeout_records_failure_and_falls_back(mock_get_config):
    release_blocked = threading.Event()
    blocked_entered = threading.Event()
    mock_get_config.return_value = SimpleNamespace(data_source_daily_timeout_seconds=0.01)
    manager = DataFetcherManager(
        fetchers=[
            _BlockingDailyFetcher("BlockingFetcher", 0, release_blocked, blocked_entered),
            _DailyFetcher("FallbackFetcher", 1),
        ]
    )
    DataFetcherManager.reset_daily_source_health()

    try:
        started = time.monotonic()
        df, source = manager.get_daily_data("600519", days=1)
    finally:
        release_blocked.set()

    assert blocked_entered.wait(timeout=0.5)
    assert time.monotonic() - started < 1
    assert source == "FallbackFetcher"
    assert not df.empty
