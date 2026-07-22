# -*- coding: utf-8 -*-
"""
Contract tests for get_capital_flow tool output semantics.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.tools.data_tools import _handle_get_capital_flow


class _DummyManagerOk:
    """Returns a well-formed capital flow context."""

    def get_capital_flow_context(self, _stock_code: str):
        return {
            "status": "ok",
            "data": {
                "stock_flow": {
                    "main_net_inflow": 1500000.0,
                    "inflow_5d": 8000000.0,
                    "inflow_10d": 15000000.0,
                },
                "sector_rankings": {
                    "top": [{"name": "白酒", "inflow": 5e8}, {"name": "半导体", "inflow": 3e8}],
                    "bottom": [{"name": "煤炭", "inflow": -2e8}],
                },
            },
            "errors": [],
        }


class _DummyManagerNotSupported:
    """Returns not_supported status (e.g. HK stock or an unsupported source)."""

    def get_capital_flow_context(self, _stock_code: str):
        return {"status": "not_supported"}


class _DummyManagerRaises:
    """Simulates a fetch failure."""

    def get_capital_flow_context(self, _stock_code: str):
        raise RuntimeError("network timeout")


class TestGetCapitalFlowContract(unittest.TestCase):

    def test_ok_response_shape(self) -> None:
        """Happy path: key fields are present and values match the source data."""
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerOk(),
        ):
            result = _handle_get_capital_flow("600519")

        self.assertEqual(result["stock_code"], "600519")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["main_net_inflow"], 1500000.0)
        self.assertEqual(result["inflow_5d"], 8000000.0)
        self.assertEqual(result["inflow_10d"], 15000000.0)
        self.assertIn("sector_rankings", result)
        self.assertIn("top_inflow_sectors", result["sector_rankings"])
        self.assertIn("top_outflow_sectors", result["sector_rankings"])
        # At most 3 items are returned per ranking list
        self.assertLessEqual(len(result["sector_rankings"]["top_inflow_sectors"]), 3)
        self.assertEqual(result["errors"], [])

    def test_not_supported_for_non_cn_or_etf(self) -> None:
        """Unsupported markets return status=not_supported with an explanatory note."""
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerNotSupported(),
        ):
            result = _handle_get_capital_flow("HK00700")

        self.assertEqual(result["stock_code"], "HK00700")
        self.assertEqual(result["status"], "not_supported")
        self.assertIn("note", result)

    def test_etf_response_exposes_daily_scope_and_intraday_reference(self) -> None:
        manager = _DummyManagerOk()
        original = manager.get_capital_flow_context

        def _etf_context(stock_code: str):
            ctx = original(stock_code)
            ctx["data"]["stock_flow"].update(
                {
                    "main_net_inflow_pct": 2.5,
                    "as_of": "2026-07-21",
                    "scope": "daily",
                }
            )
            ctx["data"]["intraday_flow"] = {
                "active_net_inflow": 2_000_000,
                "scope": "intraday",
                "classification": "vendor_classified",
                "is_estimated": True,
            }
            return ctx

        manager.get_capital_flow_context = _etf_context
        with patch("src.agent.tools.data_tools._get_fetcher_manager", return_value=manager):
            result = _handle_get_capital_flow("159865")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scope"], "daily")
        self.assertEqual(result["as_of"], "2026-07-21")
        self.assertEqual(result["main_net_inflow_pct"], 2.5)
        self.assertEqual(result["intraday_flow"]["scope"], "intraday")

    def test_exception_path_formatting(self) -> None:
        """Fetch errors are caught and returned with status=error."""
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerRaises(),
        ):
            result = _handle_get_capital_flow("600519")

        self.assertEqual(result["stock_code"], "600519")
        self.assertEqual(result["status"], "error")
        self.assertIn("capital flow fetch failed", result["error"])
        self.assertIn("network timeout", result["error"])


if __name__ == "__main__":
    unittest.main()
