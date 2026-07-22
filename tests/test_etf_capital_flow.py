# -*- coding: utf-8 -*-
"""Offline contracts for exchange-traded ETF secondary-market capital flow."""

from unittest.mock import patch

import pandas as pd
import pytest

from data_provider.fundamental_adapter import (
    AkshareFundamentalAdapter,
    _aggregate_intraday_capital_flow,
    _build_daily_capital_flow,
)
from data_provider.base import DataFetcherManager
from src.stock_analyzer import StockTrendAnalyzer
from src.services.market_symbol_utils import is_cn_etf_symbol


def _daily_flow_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-07-01", periods=10, freq="D")
    return pd.DataFrame(
        {
            "日期": dates.strftime("%Y-%m-%d"),
            "主力净流入-净额": [100.0 * index for index in range(1, 11)],
            "主力净流入-净占比": [float(index) for index in range(1, 11)],
            "大单净流入-净额": [10.0 * index for index in range(1, 11)],
            "大单净流入-净占比": [index / 10.0 for index in range(1, 11)],
            "超大单净流入-净额": [20.0 * index for index in range(1, 11)],
            "超大单净流入-净占比": [index / 5.0 for index in range(1, 11)],
        }
    )


@pytest.mark.parametrize("stock_code", ["159865", "SZ159865", "SZ.159865", "159865.SZ", "SH561510"])
def test_shared_cn_etf_symbol_normalizer_accepts_exchange_variants(stock_code: str) -> None:
    assert is_cn_etf_symbol(stock_code) is True


def test_daily_flow_uses_latest_date_and_complete_windows() -> None:
    flow = _build_daily_capital_flow(_daily_flow_frame(), "561510")

    assert flow["as_of"] == "2026-07-10"
    assert flow["previous_as_of"] == "2026-07-09"
    assert flow["main_net_inflow"] == 1000.0
    assert flow["previous_main_net_inflow"] == 900.0
    assert flow["main_net_inflow_pct"] == 10.0
    assert flow["inflow_3d"] == 2700.0
    assert flow["previous_inflow_3d"] == 1800.0
    assert flow["positive_days_3d"] == 3
    assert flow["inflow_5d"] == 4000.0
    assert flow["inflow_10d"] == 5500.0
    assert flow["large_net_inflow"] == 100.0
    assert flow["super_large_net_inflow"] == 200.0
    assert flow["scope"] == "daily"


def test_daily_flow_does_not_pad_incomplete_windows() -> None:
    flow = _build_daily_capital_flow(_daily_flow_frame().tail(4), "159865")

    assert flow["inflow_3d"] == 2700.0
    assert flow["inflow_5d"] is None
    assert flow["inflow_10d"] is None
    assert flow["previous_inflow_3d"] is None


@pytest.mark.parametrize(
    ("stock_code", "expected_market"),
    [("561510", "sh"), ("513050", "sh"), ("512480", "sh"), ("159865", "sz")],
)
def test_etf_daily_flow_routes_to_correct_exchange(stock_code: str, expected_market: str) -> None:
    adapter = AkshareFundamentalAdapter()
    calls = []

    def _fake_candidates(candidates):
        calls.append(candidates)
        if len(calls) == 1:
            return _daily_flow_frame(), "stock_individual_fund_flow", []
        return None, None, []

    with patch.object(adapter, "_call_df_candidates", side_effect=_fake_candidates):
        result = adapter.get_capital_flow(stock_code)

    first_name, first_kwargs = calls[0][0]
    assert first_name == "stock_individual_fund_flow"
    assert first_kwargs == {"stock": stock_code, "market": expected_market}
    assert result["stock_flow"]["as_of"] == "2026-07-10"
    assert result["status"] == "partial"
    assert "intraday_trade_direction_unavailable" in result["limitations"]


def test_intraday_flow_uses_vendor_side_and_keeps_neutral_separate() -> None:
    trades = pd.DataFrame(
        [
            {"时间": "09:30:01", "成交价": 10.0, "手数": 2, "买卖盘性质": "买盘"},
            {"时间": "09:30:02", "成交价": 10.0, "手数": 1, "买卖盘性质": "卖盘"},
            {"时间": "09:30:03", "成交价": 10.0, "手数": 3, "买卖盘性质": "中性盘"},
            {"时间": "09:30:04", "成交价": 10.0, "手数": 8, "买卖盘性质": "未知"},
        ]
    )

    flow = _aggregate_intraday_capital_flow(trades)

    assert flow["active_buy_amount"] == 2000.0
    assert flow["active_sell_amount"] == 1000.0
    assert flow["active_net_inflow"] == 1000.0
    assert flow["neutral_amount"] == 3000.0
    assert flow["trade_count"] == 3
    assert flow["unclassified_trade_count"] == 1
    assert flow["scope"] == "intraday"
    assert flow["classification"] == "vendor_classified"
    assert flow["is_estimated"] is True


def test_intraday_flow_without_vendor_direction_returns_no_direction_estimate() -> None:
    trades = pd.DataFrame([{"时间": "09:30:01", "成交价": 10.0, "手数": 2}])

    assert _aggregate_intraday_capital_flow(trades) == {}


def test_manager_keeps_daily_flow_when_intraday_call_times_out() -> None:
    manager = DataFetcherManager(fetchers=[])
    daily_payload = {
        "status": "ok",
        "stock_flow": {
            "main_net_inflow": 1_000_000,
            "inflow_5d": 2_000_000,
            "inflow_10d": 3_000_000,
            "as_of": "2026-07-21",
            "scope": "daily",
        },
        "intraday_flow": {},
        "sector_rankings": {"top": [], "bottom": []},
        "source_chain": ["capital_stock:stock_individual_fund_flow"],
        "errors": [],
        "limitations": [],
    }

    with patch.object(
        manager,
        "_run_with_retry",
        side_effect=[
            (daily_payload, None, 100),
            (None, "capital_flow_intraday timeout", 3_000),
        ],
    ) as run_with_retry:
        context = manager.get_capital_flow_context("159865", budget_seconds=5)

    assert [call.args[2] for call in run_with_retry.call_args_list] == [
        "capital_flow",
        "capital_flow_intraday",
    ]
    assert context["status"] == "partial"
    assert context["data"]["stock_flow"]["main_net_inflow"] == 1_000_000
    assert context["data"]["intraday_flow"] == {}
    assert "intraday_trade_direction_unavailable" in context["data"]["limitations"]
    assert "capital_flow_intraday timeout" in context["errors"]


def test_adapter_reports_failed_when_daily_source_raises() -> None:
    adapter = AkshareFundamentalAdapter()

    with patch.object(
        adapter,
        "_call_df_candidates",
        return_value=(None, None, ["stock_individual_fund_flow:ProxyError"]),
    ):
        result = adapter.get_capital_flow("159865", include_intraday=False)

    assert result["status"] == "failed"
    assert result["stock_flow"] == {}
    assert result["errors"] == ["stock_individual_fund_flow:ProxyError"]


def test_manager_skips_intraday_after_daily_source_failure() -> None:
    manager = DataFetcherManager(fetchers=[])
    failed_payload = {
        "status": "failed",
        "stock_flow": {},
        "intraday_flow": {},
        "sector_rankings": {"top": [], "bottom": []},
        "source_chain": [],
        "errors": ["stock_individual_fund_flow:ProxyError"],
        "limitations": [],
    }

    with patch.object(
        manager,
        "_run_with_retry",
        return_value=(failed_payload, None, 100),
    ) as run_with_retry:
        context = manager.get_capital_flow_context("159865", budget_seconds=5)

    assert run_with_retry.call_count == 1
    assert context["status"] == "failed"
    assert "intraday_skipped_after_daily_source_failure" in context["data"]["limitations"]


def test_trend_analysis_exposes_three_day_change_and_new_low_confirmation() -> None:
    closes = [12.0 - index * 0.05 for index in range(30)]
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2026-06-01", periods=30, freq="D"),
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": [1_000_000 + index * 1_000 for index in range(30)],
        }
    )

    result = StockTrendAnalyzer().analyze(frame, "159865")

    expected_change = (closes[-1] - closes[-4]) / closes[-4] * 100
    assert result.change_3d == pytest.approx(expected_change)
    assert result.is_new_low_3d is True
    assert result.to_dict()["change_3d"] == pytest.approx(expected_change)
