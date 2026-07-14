# -*- coding: utf-8 -*-
"""Concurrency tests for ETF bulk quote cache refresh singleflight."""

import threading
from unittest.mock import patch

import pandas as pd
import pytest

from data_provider import akshare_fetcher, efinance_fetcher
from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.efinance_fetcher import EfinanceFetcher
from data_provider.realtime_cache import SingleFlightTTLCache


def _akshare_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "159869",
                "名称": "游戏ETF",
                "最新价": 1.234,
                "涨跌幅": 1.2,
            }
        ]
    )


def _efinance_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "股票代码": "159869",
                "股票名称": "游戏ETF",
                "最新价": 1.234,
                "涨跌幅": 1.2,
            }
        ]
    )


@pytest.fixture(autouse=True)
def _reset_etf_caches():
    for module in (akshare_fetcher, efinance_fetcher):
        module._etf_realtime_cache["data"] = None
        module._etf_realtime_cache["timestamp"] = 0
        singleflight = getattr(module, "_etf_realtime_singleflight", None)
        if singleflight is not None:
            singleflight.clear()
    yield


def _run_two_calls(call):
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=1)
            results.append(call())
        except Exception as exc:  # pragma: no cover - thread collection
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    return results, errors


def test_akshare_etf_cache_miss_runs_one_bulk_refresh():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)
    calls = 0
    release = threading.Event()

    def load():
        nonlocal calls
        calls += 1
        release.wait(timeout=1)
        return _akshare_frame()

    timer = threading.Timer(0.1, release.set)
    timer.start()
    try:
        with patch.object(fetcher, "_set_random_user_agent"), patch.object(
            fetcher,
            "_enforce_rate_limit",
        ), patch("akshare.fund_etf_spot_em", side_effect=load):
            results, errors = _run_two_calls(
                lambda: fetcher._get_etf_realtime_quote(
                    "159869",
                    request_timeout_seconds=1.0,
                    raise_on_error=True,
                )
            )
    finally:
        timer.cancel()

    assert errors == []
    assert calls == 1
    assert len(results) == 2
    assert {quote.price for quote in results} == {1.234}


def test_efinance_etf_cache_miss_runs_one_bulk_refresh():
    fetcher = EfinanceFetcher.__new__(EfinanceFetcher)
    calls = 0
    release = threading.Event()

    def load(*args, **kwargs):
        nonlocal calls
        calls += 1
        release.wait(timeout=1)
        return _efinance_frame()

    timer = threading.Timer(0.1, release.set)
    timer.start()
    try:
        with patch.object(fetcher, "_set_random_user_agent"), patch.object(
            fetcher,
            "_enforce_rate_limit",
        ), patch("data_provider.efinance_fetcher._ef_call_with_timeout", side_effect=load):
            results, errors = _run_two_calls(
                lambda: fetcher._get_etf_realtime_quote(
                    "159869",
                    request_timeout_seconds=1.0,
                    raise_on_error=True,
                )
            )
    finally:
        timer.cancel()

    assert errors == []
    assert calls == 1
    assert len(results) == 2
    assert {quote.price for quote in results} == {1.234}


def test_singleflight_waiters_share_refresh_failure():
    state = {"data": None, "timestamp": 0, "ttl": 60}
    cache = SingleFlightTTLCache(state)
    calls = 0
    release = threading.Event()

    def load():
        nonlocal calls
        calls += 1
        release.wait(timeout=1)
        raise ConnectionError("remote disconnected")

    timer = threading.Timer(0.1, release.set)
    timer.start()
    try:
        _, errors = _run_two_calls(
            lambda: cache.get_or_refresh(load, wait_timeout_seconds=1.0)
        )
    finally:
        timer.cancel()

    assert calls == 1
    assert len(errors) == 2
    assert all(isinstance(error, ConnectionError) for error in errors)


def test_singleflight_waiter_honors_own_timeout():
    state = {"data": None, "timestamp": 0, "ttl": 60}
    cache = SingleFlightTTLCache(state)
    refresh_started = threading.Event()
    release = threading.Event()
    result = []

    def load():
        refresh_started.set()
        release.wait(timeout=1)
        return _akshare_frame()

    owner = threading.Thread(
        target=lambda: result.append(
            cache.get_or_refresh(load, wait_timeout_seconds=1.0)
        )
    )
    owner.start()
    assert refresh_started.wait(timeout=0.5)
    try:
        with pytest.raises(TimeoutError, match="refresh wait timeout"):
            cache.get_or_refresh(load, wait_timeout_seconds=0.01)
    finally:
        release.set()
        owner.join(timeout=1)

    assert len(result) == 1
