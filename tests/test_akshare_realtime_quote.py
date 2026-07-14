# -*- coding: utf-8 -*-
"""Regression tests for AkShare realtime routing by physical provider."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from data_provider import akshare_fetcher
from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote


def _quote(source: RealtimeSource) -> UnifiedRealtimeQuote:
    return UnifiedRealtimeQuote(code="159869", name="游戏ETF", source=source, price=1.234)


@pytest.mark.parametrize(
    ("route_source", "method_name", "quote_source"),
    [
        ("tencent", "_get_stock_realtime_quote_tencent", RealtimeSource.TENCENT),
        ("sina", "_get_stock_realtime_quote_sina", RealtimeSource.AKSHARE_SINA),
        ("em", "_get_etf_realtime_quote", RealtimeSource.AKSHARE_EM),
    ],
)
def test_etf_route_uses_requested_physical_source(route_source, method_name, quote_source):
    fetcher = AkshareFetcher.__new__(AkshareFetcher)
    expected = _quote(quote_source)
    circuit_breaker = MagicMock()
    circuit_breaker.is_available.return_value = True

    methods = {
        "_get_stock_realtime_quote_tencent": MagicMock(return_value=expected),
        "_get_stock_realtime_quote_sina": MagicMock(return_value=expected),
        "_get_etf_realtime_quote": MagicMock(return_value=expected),
    }
    with patch(
        "data_provider.akshare_fetcher.get_realtime_circuit_breaker",
        return_value=circuit_breaker,
    ), patch.object(
        fetcher,
        "_get_stock_realtime_quote_tencent",
        methods["_get_stock_realtime_quote_tencent"],
    ), patch.object(
        fetcher,
        "_get_stock_realtime_quote_sina",
        methods["_get_stock_realtime_quote_sina"],
    ), patch.object(
        fetcher,
        "_get_etf_realtime_quote",
        methods["_get_etf_realtime_quote"],
    ):
        result = fetcher.get_realtime_quote("159869", source=route_source)

    assert result is expected
    methods[method_name].assert_called_once_with("159869")
    for other_name, method in methods.items():
        if other_name != method_name:
            method.assert_not_called()


def test_regular_a_share_route_remains_source_specific():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)
    expected = UnifiedRealtimeQuote(
        code="600519",
        source=RealtimeSource.TENCENT,
        price=1688.0,
    )
    circuit_breaker = MagicMock()
    circuit_breaker.is_available.return_value = True

    with patch(
        "data_provider.akshare_fetcher.get_realtime_circuit_breaker",
        return_value=circuit_breaker,
    ), patch.object(
        fetcher,
        "_get_stock_realtime_quote_tencent",
        return_value=expected,
    ) as tencent, patch.object(
        fetcher,
        "_get_etf_realtime_quote",
    ) as etf:
        result = fetcher.get_realtime_quote("600519", source="tencent")

    assert result is expected
    tencent.assert_called_once_with("600519")
    etf.assert_not_called()


def test_tencent_request_uses_lightweight_timeout_cap():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)
    fields = [""] * 50
    fields[1] = "游戏ETF"
    fields[2] = "159869"
    fields[3] = "1.234"
    fields[4] = "1.200"
    fields[5] = "1.210"
    fields[30] = "20260714150000"
    response = MagicMock(status_code=200, text=f'v_sz159869="{"~".join(fields)}"')

    with patch.object(fetcher, "_enforce_rate_limit"), patch(
        "data_provider.akshare_fetcher.requests.get",
        return_value=response,
    ) as request:
        quote = fetcher._get_stock_realtime_quote_tencent(
            "159869",
            request_timeout_seconds=9.0,
        )

    assert quote is not None
    assert quote.price == 1.234
    assert request.call_args.kwargs["timeout"] == 9.0


def test_sina_request_uses_ten_second_cap_and_allows_manager_to_shrink_it():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)
    response = MagicMock(
        status_code=200,
        text='var hq_str_sz159869="游戏ETF,1.200,1.210,1.234,1.250,1.180,1.230,1.234,100,1000"',
    )

    with patch.object(fetcher, "_enforce_rate_limit"), patch(
        "data_provider.akshare_fetcher.requests.get",
        return_value=response,
    ) as request:
        fetcher._get_stock_realtime_quote_sina("159869", request_timeout_seconds=12.0)
        assert request.call_args.kwargs["timeout"] == 10.0

        fetcher._get_stock_realtime_quote_sina("159869", request_timeout_seconds=2.5)
        assert request.call_args.kwargs["timeout"] == 2.5


def test_lightweight_rate_limit_state_is_isolated_by_physical_source():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)

    with patch.object(fetcher, "random_sleep"), patch(
        "data_provider.akshare_fetcher.time.time",
        side_effect=[100.0, 100.0],
    ), patch("data_provider.akshare_fetcher.time.sleep") as sleep:
        fetcher._enforce_rate_limit("tencent")
        fetcher._enforce_rate_limit("sina")

    sleep.assert_not_called()


def test_tencent_request_can_propagate_network_error_to_manager():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)

    with patch.object(fetcher, "_enforce_rate_limit"), patch(
        "data_provider.akshare_fetcher.requests.get",
        side_effect=requests.ConnectionError("remote disconnected"),
    ), pytest.raises(requests.ConnectionError):
        fetcher._get_stock_realtime_quote_tencent(
            "159869",
            request_timeout_seconds=2.5,
            raise_on_error=True,
        )


def test_eastmoney_bulk_route_does_not_retry_inside_provider():
    fetcher = AkshareFetcher.__new__(AkshareFetcher)
    akshare_fetcher._realtime_cache["data"] = None
    akshare_fetcher._realtime_cache["timestamp"] = 0

    with patch.object(fetcher, "_set_random_user_agent"), patch.object(
        fetcher,
        "_enforce_rate_limit",
    ), patch(
        "akshare.stock_zh_a_spot_em",
        side_effect=requests.ConnectionError("remote disconnected"),
    ) as bulk_call, pytest.raises(requests.ConnectionError):
        fetcher._get_stock_realtime_quote_em(
            "600519",
            request_timeout_seconds=8.0,
            raise_on_error=True,
        )

    bulk_call.assert_called_once_with()
