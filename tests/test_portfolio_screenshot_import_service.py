# -*- coding: utf-8 -*-
"""Tests for portfolio screenshot parsing and atomic ledger imports."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from sqlalchemy import select

from src.config import Config
from src.repositories.portfolio_repo import PortfolioBusyError
from src.services.portfolio_service import PortfolioOversellError, PortfolioService
from src.services.portfolio_screenshot_import_service import (
    AccountNotEmptyError,
    AmbiguousTradeOrderError,
    ImageInput,
    PortfolioImageBatchTimeoutError,
    PortfolioImageProcessingCancelled,
    PortfolioScreenshotImportService,
    build_trade_dedup_hash,
    build_trade_fingerprint,
)
from src.storage import DatabaseManager, PortfolioCashLedger, PortfolioTrade


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 12


class PortfolioScreenshotImportServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.db_path = Path(self.temp_dir.name) / "portfolio_screenshot_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()

        self.portfolio_service = PortfolioService()
        self.account = self.portfolio_service.create_account(
            name="Main",
            broker="Demo",
            market="cn",
            base_currency="CNY",
        )

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    @staticmethod
    def _image(index: int = 0) -> ImageInput:
        return ImageInput(
            content=PNG_BYTES + bytes([index]),
            mime_type="image/png",
            filename=f"position-{index}.png",
        )

    @staticmethod
    def _position_response(
        *,
        symbol: str = "600000",
        name: str = "浦发银行",
        quantity: float = 1000,
        avg_cost: float = 10.0,
        available_quantity: float = 0,
    ) -> str:
        return json.dumps(
            {
                "summary": {
                    "total_assets": 12000,
                    "available_cash": 2000,
                    "total_market_value": 10200,
                },
                "positions": [
                    {
                        "symbol": symbol,
                        "name": name,
                        "quantity": quantity,
                        "available_quantity": available_quantity,
                        "avg_cost": avg_cost,
                        "current_price": 10.2,
                        "market_value": 10200,
                        "weight_pct": 85,
                        "confidence": "high",
                    }
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _trade_response(*trades: dict, document_type: str = "today_trades") -> str:
        return json.dumps(
            {"document_type": document_type, "trades": list(trades)},
            ensure_ascii=False,
        )

    @staticmethod
    def _trade_row(**overrides: object) -> dict:
        row = {
            "trade_date": None,
            "trade_time": "10:01:02",
            "symbol": "600000",
            "name": "浦发银行",
            "side": "买入",
            "quantity": 300,
            "price": 10.2,
            "fee": None,
            "tax": None,
            "trade_uid": None,
            "record_type": "executed_trade",
            "confidence": "high",
        }
        row.update(overrides)
        return row

    def _service(self, *responses: object) -> tuple[PortfolioScreenshotImportService, MagicMock]:
        completion = MagicMock(side_effect=list(responses))
        service = PortfolioScreenshotImportService(
            portfolio_service=self.portfolio_service,
            vision_complete=completion,
        )
        return service, completion

    @staticmethod
    def _commit_trade(**overrides: object) -> dict:
        row = {
            "trade_date": "2026-07-13",
            "trade_time": "10:01:02",
            "symbol": "600000",
            "name": "浦发银行",
            "side": "buy",
            "quantity": 300,
            "price": 10.2,
            "fee": 0,
            "tax": 0,
            "trade_uid": None,
            "occurrence_index": 1,
        }
        row.update(overrides)
        return row

    def test_position_parse_uses_position_quantity_not_available_quantity(self) -> None:
        service, _ = self._service(self._position_response(quantity=1000, available_quantity=0))

        result = service.parse_position_images(
            account_id=self.account["id"],
            snapshot_date=date.today(),
            images=[self._image()],
        )

        self.assertEqual(result["positions"][0]["quantity"], 1000)
        self.assertEqual(result["positions"][0]["available_quantity"], 0)
        self.assertEqual(result["positions"][0]["avg_cost"], 10.0)
        self.assertEqual(result["summary"]["available_cash"], 2000)
        self.assertNotIn("cash_ledger", result)

    def test_position_parse_merges_identical_rows_across_images(self) -> None:
        response = self._position_response()
        service, _ = self._service(response, response)

        result = service.parse_position_images(
            account_id=self.account["id"],
            snapshot_date=date.today(),
            images=[self._image(0), self._image(1)],
        )

        self.assertEqual(len(result["positions"]), 1)
        self.assertEqual(result["positions"][0]["status"], "ready")
        self.assertEqual(
            result["positions"][0]["source_refs"],
            [{"file_index": 0, "row_index": 0}, {"file_index": 1, "row_index": 0}],
        )

    def test_position_parse_marks_quantity_or_cost_conflict(self) -> None:
        service, _ = self._service(
            self._position_response(quantity=1000, avg_cost=10),
            self._position_response(quantity=900, avg_cost=10.5),
        )

        result = service.parse_position_images(
            account_id=self.account["id"],
            snapshot_date=date.today(),
            images=[self._image(0), self._image(1)],
        )

        self.assertEqual(len(result["positions"]), 1)
        self.assertEqual(result["positions"][0]["status"], "conflict")
        self.assertIn("position_conflict", result["positions"][0]["issues"])

    def test_position_parse_name_difference_is_warning_only(self) -> None:
        service, _ = self._service(
            self._position_response(name="浦发银行"),
            self._position_response(name="上海浦发银行"),
        )

        result = service.parse_position_images(
            account_id=self.account["id"],
            snapshot_date=date.today(),
            images=[self._image(0), self._image(1)],
        )

        self.assertEqual(result["positions"][0]["status"], "ready")
        self.assertIn("name_mismatch", result["positions"][0]["issues"])

    def test_position_parse_preserves_per_file_failure(self) -> None:
        service, _ = self._service(self._position_response(), ValueError("vision timeout"))

        result = service.parse_position_images(
            account_id=self.account["id"],
            snapshot_date=date.today(),
            images=[self._image(0), self._image(1)],
        )

        self.assertEqual(result["files"][0]["status"], "success")
        self.assertEqual(result["files"][1]["status"], "failed")
        self.assertEqual(result["files"][1]["error"], "vision_failed")
        self.assertNotIn("vision timeout", json.dumps(result, ensure_ascii=False))

    def test_position_parse_emits_file_and_attempt_progress_with_deadline(self) -> None:
        events: list[dict] = []
        seen_kwargs: dict = {}

        def complete(*_args, **kwargs):
            seen_kwargs.update(kwargs)
            kwargs["attempt_callback"](1, 2)
            return self._position_response()

        service = PortfolioScreenshotImportService(
            portfolio_service=self.portfolio_service,
            vision_complete=complete,
        )
        deadline = time.monotonic() + 60

        result = service.parse_position_images(
            account_id=self.account["id"],
            snapshot_date=date.today(),
            images=[self._image()],
            progress_callback=events.append,
            deadline_monotonic=deadline,
        )

        self.assertEqual(result["files"][0]["status"], "success")
        self.assertEqual([event["phase"] for event in events], ["file_started", "attempt", "file_completed"])
        self.assertEqual(seen_kwargs["deadline_monotonic"], deadline)

    def test_position_parse_stops_before_next_image_after_cancel_request(self) -> None:
        completion = MagicMock(return_value=self._position_response())
        service = PortfolioScreenshotImportService(
            portfolio_service=self.portfolio_service,
            vision_complete=completion,
        )
        cancelled = False

        def on_progress(event: dict) -> None:
            nonlocal cancelled
            if event["phase"] == "file_completed":
                cancelled = True

        with self.assertRaises(PortfolioImageProcessingCancelled):
            service.parse_position_images(
                account_id=self.account["id"],
                snapshot_date=date.today(),
                images=[self._image(0), self._image(1)],
                progress_callback=on_progress,
                cancel_requested=lambda: cancelled,
            )

        self.assertEqual(completion.call_count, 1)

    def test_position_parse_rejects_expired_batch_deadline_before_vision(self) -> None:
        service, completion = self._service(self._position_response())

        with self.assertRaises(PortfolioImageBatchTimeoutError):
            service.parse_position_images(
                account_id=self.account["id"],
                snapshot_date=date.today(),
                images=[self._image()],
                deadline_monotonic=time.monotonic() - 1,
            )

        completion.assert_not_called()

    def test_position_parse_rejects_invalid_batch_account_and_date(self) -> None:
        service, completion = self._service(self._position_response())

        with self.assertRaisesRegex(ValueError, "1-5"):
            service.parse_position_images(
                account_id=self.account["id"],
                snapshot_date=date.today(),
                images=[],
            )
        with self.assertRaisesRegex(ValueError, "future"):
            service.parse_position_images(
                account_id=self.account["id"],
                snapshot_date=date.today() + timedelta(days=1),
                images=[self._image()],
            )

        hk_account = self.portfolio_service.create_account(
            name="HK",
            broker="Demo",
            market="hk",
            base_currency="HKD",
        )
        with self.assertRaisesRegex(ValueError, "cn/CNY"):
            service.parse_position_images(
                account_id=hk_account["id"],
                snapshot_date=date.today(),
                images=[self._image()],
            )

        completion.assert_not_called()

    def test_trade_parse_fills_batch_date_time_and_default_fees(self) -> None:
        trade_date = date(2026, 7, 13)
        service, _ = self._service(
            self._trade_response(
                self._trade_row(quantity=300),
                self._trade_row(quantity=200),
            )
        )

        result = service.parse_trade_images(
            account_id=self.account["id"],
            default_trade_date=trade_date,
            images=[self._image()],
        )

        self.assertEqual(result["trades"][0]["trade_date"], "2026-07-13")
        self.assertEqual(result["trades"][0]["trade_time"], "10:01:02")
        self.assertEqual(result["trades"][0]["quantity"], 300)
        self.assertEqual(result["trades"][0]["fee"], 0)
        self.assertEqual(result["trades"][0]["tax"], 0)
        self.assertIn("fee_defaulted", result["trades"][0]["issues"])
        self.assertIn("tax_defaulted", result["trades"][0]["issues"])
        self.assertEqual(result["trades"][0]["status"], "ready")

    def test_trade_parse_prefers_row_date_and_rejects_future_date(self) -> None:
        service, _ = self._service(
            self._trade_response(
                self._trade_row(trade_date="2026-07-10"),
                self._trade_row(trade_date=(date.today() + timedelta(days=1)).isoformat()),
            )
        )

        result = service.parse_trade_images(
            account_id=self.account["id"],
            default_trade_date=date(2026, 7, 13),
            images=[self._image()],
        )

        self.assertEqual(result["trades"][0]["trade_date"], "2026-07-10")
        self.assertEqual(result["trades"][0]["status"], "ready")
        self.assertEqual(result["trades"][1]["status"], "error")
        self.assertIn("future_trade_date", result["trades"][1]["issues"])

    def test_trade_parse_rejects_orders_cancellations_and_missing_fields(self) -> None:
        service, _ = self._service(
            self._trade_response(
                self._trade_row(record_type="order"),
                self._trade_row(record_type="cancelled"),
                self._trade_row(quantity=None),
            )
        )

        result = service.parse_trade_images(
            account_id=self.account["id"],
            default_trade_date=date(2026, 7, 13),
            images=[self._image()],
        )

        self.assertEqual([item["status"] for item in result["trades"]], ["error", "error", "error"])
        self.assertIn("not_executed_trade", result["trades"][0]["issues"])
        self.assertIn("not_executed_trade", result["trades"][1]["issues"])
        self.assertIn("invalid_quantity", result["trades"][2]["issues"])

    def test_trade_parse_treats_missing_name_as_warning(self) -> None:
        service, _ = self._service(self._trade_response(self._trade_row(name=None)))

        result = service.parse_trade_images(
            account_id=self.account["id"],
            default_trade_date=date(2026, 7, 13),
            images=[self._image()],
        )

        self.assertEqual(result["trades"][0]["status"], "ready")
        self.assertIn("missing_name", result["trades"][0]["issues"])

    def test_trade_fingerprint_normalizes_decimal_values(self) -> None:
        base = {
            "trade_date": "2026-07-13",
            "trade_time": "10:01:02",
            "symbol": "600000",
            "side": "buy",
            "quantity": "300.0",
            "price": "10.20",
            "fee": "0.00",
            "tax": 0,
        }
        equivalent = {**base, "quantity": 300, "price": "10.2", "fee": 0}

        self.assertEqual(build_trade_fingerprint(base), build_trade_fingerprint(equivalent))
        self.assertEqual(build_trade_dedup_hash(base, 1), build_trade_dedup_hash(equivalent, 1))
        self.assertNotEqual(build_trade_dedup_hash(base, 1), build_trade_dedup_hash(base, 2))

    def test_trade_parse_keeps_same_image_occurrences_but_marks_cross_image_overlap(self) -> None:
        identical = self._trade_row(quantity=300)
        first_file = self._trade_response(identical, identical)
        second_file = self._trade_response(identical)
        service, _ = self._service(first_file, second_file)

        result = service.parse_trade_images(
            account_id=self.account["id"],
            default_trade_date=date(2026, 7, 13),
            images=[self._image(0), self._image(1)],
        )

        self.assertEqual(len(result["trades"]), 3)
        self.assertEqual([item["occurrence_index"] for item in result["trades"][:2]], [1, 2])
        self.assertTrue(all(item["status"] == "conflict" for item in result["trades"]))
        self.assertTrue(all("ambiguous_overlap" in item["issues"] for item in result["trades"]))

    def test_trade_parse_rejects_future_batch_date_before_vision_call(self) -> None:
        service, completion = self._service(self._trade_response(self._trade_row()))

        with self.assertRaisesRegex(ValueError, "future"):
            service.parse_trade_images(
                account_id=self.account["id"],
                default_trade_date=date.today() + timedelta(days=1),
                images=[self._image()],
            )

        completion.assert_not_called()

    def test_commit_initial_positions_writes_atomic_opening_buys_without_cash(self) -> None:
        service, _ = self._service()

        result = service.commit_initial_positions(
            account_id=self.account["id"],
            batch_id="batch-position-1",
            snapshot_date=date(2026, 7, 13),
            positions=[
                {"symbol": "600000", "name": "浦发银行", "quantity": 1000, "avg_cost": 10},
                {"symbol": "000001", "name": "平安银行", "quantity": 500, "avg_cost": 12},
            ],
        )

        self.assertEqual(result["inserted_count"], 2)
        with DatabaseManager.get_instance().get_session() as session:
            trades = session.execute(select(PortfolioTrade)).scalars().all()
            cash_rows = session.execute(select(PortfolioCashLedger)).scalars().all()
        self.assertEqual(len(trades), 2)
        self.assertEqual(len(cash_rows), 0)
        self.assertTrue(all(row.side == "buy" and row.fee == 0 and row.tax == 0 for row in trades))
        self.assertTrue(all(row.trade_time is None for row in trades))

    def test_commit_initial_positions_rejects_nonempty_account_without_changes(self) -> None:
        self.portfolio_service.record_trade(
            account_id=self.account["id"],
            symbol="600519",
            trade_date=date(2026, 7, 12),
            side="buy",
            quantity=10,
            price=100,
        )
        service, _ = self._service()

        with self.assertRaises(AccountNotEmptyError):
            service.commit_initial_positions(
                account_id=self.account["id"],
                batch_id="batch-position-2",
                snapshot_date=date(2026, 7, 13),
                positions=[{"symbol": "600000", "name": "浦发银行", "quantity": 1000, "avg_cost": 10}],
            )

        self.assertEqual(
            self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"],
            1,
        )

    def test_commit_initial_positions_rolls_back_when_second_insert_fails(self) -> None:
        service, _ = self._service()
        original = service.repo.add_trade_in_session
        call_count = 0

        def flaky_insert(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("second row failed")
            return original(**kwargs)

        with patch.object(service.repo, "add_trade_in_session", side_effect=flaky_insert):
            with self.assertRaisesRegex(ValueError, "second row failed"):
                service.commit_initial_positions(
                    account_id=self.account["id"],
                    batch_id="batch-position-3",
                    snapshot_date=date(2026, 7, 13),
                    positions=[
                        {"symbol": "600000", "name": "浦发银行", "quantity": 1000, "avg_cost": 10},
                        {"symbol": "000001", "name": "平安银行", "quantity": 500, "avg_cost": 12},
                    ],
                )

        self.assertEqual(self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"], 0)

    def test_commit_initial_positions_propagates_portfolio_busy(self) -> None:
        service, _ = self._service()
        with patch.object(
            service.repo,
            "portfolio_write_session",
            side_effect=PortfolioBusyError("busy"),
        ):
            with self.assertRaises(PortfolioBusyError):
                service.commit_initial_positions(
                    account_id=self.account["id"],
                    batch_id="batch-position-busy",
                    snapshot_date=date(2026, 7, 13),
                    positions=[{"symbol": "600000", "name": "浦发银行", "quantity": 1000, "avg_cost": 10}],
                )

    def test_commit_trade_batch_skips_existing_fingerprint_duplicate(self) -> None:
        service, _ = self._service()
        trade = self._commit_trade()
        dedup_hash = build_trade_dedup_hash(trade, 1)
        self.portfolio_service.record_trade(
            account_id=self.account["id"],
            symbol=trade["symbol"],
            trade_date=date.fromisoformat(trade["trade_date"]),
            trade_time=trade["trade_time"],
            side=trade["side"],
            quantity=trade["quantity"],
            price=trade["price"],
            fee=trade["fee"],
            tax=trade["tax"],
            dedup_hash=dedup_hash,
        )

        result = service.commit_trade_batch(
            account_id=self.account["id"],
            batch_id="batch-trade-duplicate",
            trades=[trade],
        )

        self.assertEqual(result["inserted_count"], 0)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"], 1)

    def test_commit_trade_batch_preserves_legal_identical_fills(self) -> None:
        service, _ = self._service()
        trade = self._commit_trade()

        result = service.commit_trade_batch(
            account_id=self.account["id"],
            batch_id="batch-trade-split-fill",
            trades=[
                {**trade, "occurrence_index": 1},
                {**trade, "occurrence_index": 2},
            ],
        )

        self.assertEqual(result["inserted_count"], 2)
        rows = self.portfolio_service.list_trade_events(account_id=self.account["id"])["items"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["id"] for row in rows}), 2)

    def test_commit_trade_batch_rejects_duplicate_occurrence_index(self) -> None:
        service, _ = self._service()
        trade = self._commit_trade()

        with self.assertRaisesRegex(ValueError, "occurrence_index"):
            service.commit_trade_batch(
                account_id=self.account["id"],
                batch_id="batch-trade-unresolved-overlap",
                trades=[dict(trade), dict(trade)],
            )

        self.assertEqual(self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"], 0)

    def test_commit_trade_batch_preserves_reviewed_occurrence_index(self) -> None:
        service, _ = self._service()
        trade = self._commit_trade()
        self.portfolio_service.record_trade(
            account_id=self.account["id"],
            symbol=trade["symbol"],
            trade_date=date.fromisoformat(trade["trade_date"]),
            trade_time=trade["trade_time"],
            side=trade["side"],
            quantity=trade["quantity"],
            price=trade["price"],
            fee=trade["fee"],
            tax=trade["tax"],
            dedup_hash=build_trade_dedup_hash(trade, 1),
        )

        result = service.commit_trade_batch(
            account_id=self.account["id"],
            batch_id="batch-trade-reviewed-occurrence",
            trades=[{**trade, "occurrence_index": 2}],
        )

        self.assertEqual(result["inserted_count"], 1)
        self.assertEqual(result["duplicate_count"], 0)
        rows = self.portfolio_service.list_trade_events(account_id=self.account["id"])["items"]
        self.assertEqual(len(rows), 2)

    def test_commit_trade_batch_replays_buy_and_sell_by_time(self) -> None:
        service, _ = self._service()

        result = service.commit_trade_batch(
            account_id=self.account["id"],
            batch_id="batch-trade-time-order",
            trades=[
                self._commit_trade(side="sell", quantity=100, trade_time="10:02:00"),
                self._commit_trade(side="buy", quantity=100, trade_time="10:01:00"),
            ],
        )

        self.assertEqual(result["inserted_count"], 2)
        rows = self.portfolio_service.list_trade_events(account_id=self.account["id"])["items"]
        self.assertEqual([row["trade_time"] for row in rows], ["10:02:00", "10:01:00"])
        snapshot = self.portfolio_service.get_portfolio_snapshot(
            account_id=self.account["id"],
            as_of=date(2026, 7, 13),
            cost_method="fifo",
            include_realtime=False,
        )
        self.assertEqual(snapshot["accounts"][0]["positions"], [])

    def test_commit_trade_batch_rolls_back_when_batch_oversells(self) -> None:
        service, _ = self._service()

        with self.assertRaises(PortfolioOversellError):
            service.commit_trade_batch(
                account_id=self.account["id"],
                batch_id="batch-trade-oversell",
                trades=[
                    self._commit_trade(side="buy", quantity=10, trade_time="10:01:00"),
                    self._commit_trade(side="sell", quantity=11, trade_time="10:02:00"),
                ],
            )

        self.assertEqual(self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"], 0)

    def test_commit_trade_batch_rejects_backfill_that_breaks_future_ledger(self) -> None:
        self.portfolio_service.record_trade(
            account_id=self.account["id"],
            symbol="600000",
            trade_date=date(2026, 7, 10),
            trade_time="09:30:00",
            side="buy",
            quantity=10,
            price=10,
        )
        self.portfolio_service.record_trade(
            account_id=self.account["id"],
            symbol="600000",
            trade_date=date(2026, 7, 12),
            trade_time="09:30:00",
            side="sell",
            quantity=10,
            price=11,
        )
        service, _ = self._service()

        with self.assertRaises(PortfolioOversellError):
            service.commit_trade_batch(
                account_id=self.account["id"],
                batch_id="batch-trade-backfill",
                trades=[self._commit_trade(trade_date="2026-07-11", side="sell", quantity=5)],
            )

        self.assertEqual(self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"], 2)

    def test_commit_trade_batch_rejects_order_sensitive_null_time(self) -> None:
        self.portfolio_service.record_trade(
            account_id=self.account["id"],
            symbol="600000",
            trade_date=date(2026, 7, 13),
            side="buy",
            quantity=10,
            price=10,
        )
        service, _ = self._service()

        with self.assertRaises(AmbiguousTradeOrderError):
            service.commit_trade_batch(
                account_id=self.account["id"],
                batch_id="batch-trade-null-time",
                trades=[self._commit_trade(side="sell", quantity=10, trade_time="09:30:00")],
            )

        self.assertEqual(self.portfolio_service.list_trade_events(account_id=self.account["id"])["total"], 1)


if __name__ == "__main__":
    unittest.main()
