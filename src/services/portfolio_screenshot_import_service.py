# -*- coding: utf-8 -*-
"""Portfolio screenshot parsing and atomic import service."""

from __future__ import annotations

import json
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import date, time as dt_time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from json_repair import repair_json
from pydantic import BaseModel, Field

from src.repositories.portfolio_repo import PortfolioRepository
from src.services.portfolio_service import EPS, PortfolioOversellError, PortfolioService
from src.services.vision_extraction_service import complete_vision


POSITION_EXTRACTION_PROMPT = """你正在识别中国券商 App 的当前持仓截图。
只返回 JSON，不要返回 Markdown。输出结构：
{"summary":{"total_assets":null,"available_cash":null,"withdrawable_cash":null,
"total_market_value":null,"total_weight_pct":null,"total_profit_loss":null},
"positions":[{"symbol":null,"name":null,"quantity":null,"available_quantity":null,
"avg_cost":null,"current_price":null,"market_value":null,"weight_pct":null,
"profit_loss":null,"confidence":"low"}]}
quantity 必须读取“持仓/持仓数量”，绝不能使用“可用/可卖数量”；avg_cost 读取成本价。
顶部资金汇总只能放入 summary。不可见字段返回 null，不得计算、补全或猜测。
"""

TRADE_EXTRACTION_PROMPT = """你正在识别中国券商 App 的当日成交、历史成交或交割单截图。
只返回 JSON，不要返回 Markdown。输出结构：
{"document_type":"today_trades|historical_trades|settlement|other","trades":[{
"trade_date":null,"trade_time":null,"symbol":null,"name":null,"side":null,
"quantity":null,"price":null,"fee":null,"tax":null,"trade_uid":null,
"record_type":"executed_trade|order|cancelled|unfilled","confidence":"low"}]}
只输出已经实际成交的行，不得把委托、撤单、未成交、顶部 tab 或列标题当作成交。
均价映射 price，成交数量映射 quantity；不可见字段返回 null，不得猜测手续费或税费。
"""


class AccountNotEmptyError(Exception):
    """Raised when position initialization targets an account with trades."""


class AmbiguousTradeOrderError(Exception):
    """Raised when null same-day times make ledger validity order-dependent."""


@dataclass(frozen=True)
class ImageInput:
    content: bytes
    mime_type: str
    filename: Optional[str] = None


class _PositionVisionRow(BaseModel):
    symbol: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[float] = None
    available_quantity: Optional[float] = None
    avg_cost: Optional[float] = None
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    weight_pct: Optional[float] = None
    profit_loss: Optional[float] = None
    confidence: str = "low"


class _PositionVisionResponse(BaseModel):
    summary: Dict[str, Optional[float]] = Field(default_factory=dict)
    positions: List[_PositionVisionRow] = Field(default_factory=list)


class _TradeVisionRow(BaseModel):
    trade_date: Optional[str] = None
    trade_time: Optional[str] = None
    symbol: Optional[str] = None
    name: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    tax: Optional[float] = None
    trade_uid: Optional[str] = None
    record_type: str = "executed_trade"
    confidence: str = "low"


class _TradeVisionResponse(BaseModel):
    document_type: str = "other"
    trades: List[_TradeVisionRow] = Field(default_factory=list)


def _decode_json_object(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, count=1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = json.loads(repair_json(text))
    if not isinstance(payload, dict):
        raise ValueError("Vision response must be a JSON object")
    return payload


def _decimal_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return False


def _normalize_decimal_text(value: Any) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value: {value}") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"Invalid decimal value: {value}")
    normalized = format(decimal_value.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def build_trade_fingerprint(record: Mapping[str, Any]) -> str:
    """Build the visible-field fingerprint used for best-effort deduplication."""
    values = [
        str(record.get("trade_date") or ""),
        str(record.get("trade_time") or ""),
        str(record.get("symbol") or "").strip(),
        str(record.get("side") or "").strip().lower(),
        _normalize_decimal_text(record.get("quantity")),
        _normalize_decimal_text(record.get("price")),
        _normalize_decimal_text(record.get("fee", 0) or 0),
        _normalize_decimal_text(record.get("tax", 0) or 0),
    ]
    return "|".join(values)


def build_trade_dedup_hash(record: Mapping[str, Any], occurrence_index: int) -> str:
    if occurrence_index < 1:
        raise ValueError("occurrence_index must be >= 1")
    payload = f"portfolio_image_trade|{build_trade_fingerprint(record)}|{occurrence_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PortfolioScreenshotImportService:
    """Parse screenshot batches without persisting images or model responses."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        repo: Optional[PortfolioRepository] = None,
        vision_complete: Optional[Callable[..., str]] = None,
    ) -> None:
        self.portfolio_service = portfolio_service or PortfolioService()
        self.repo = repo or self.portfolio_service.repo
        self.vision_complete = vision_complete or complete_vision

    def parse_position_images(
        self,
        *,
        account_id: int,
        snapshot_date: date,
        images: List[ImageInput],
    ) -> Dict[str, Any]:
        self._validate_image_batch(images)
        self._validate_import_date(snapshot_date, field_name="snapshot_date")
        self._require_cn_cny_account(account_id)

        file_results: List[Dict[str, Any]] = []
        summary: Dict[str, Optional[float]] = {}
        positions: List[Dict[str, Any]] = []

        for file_index, image in enumerate(images):
            try:
                raw_text = self.vision_complete(
                    image.content,
                    image.mime_type,
                    POSITION_EXTRACTION_PROMPT,
                    max_tokens=2048,
                )
                response = _PositionVisionResponse.model_validate(_decode_json_object(raw_text))
                for key, value in response.summary.items():
                    if value is not None and key not in summary:
                        summary[key] = float(value)
                for row_index, row in enumerate(response.positions):
                    positions.append(self._normalize_position_row(row, file_index=file_index, row_index=row_index))
                file_results.append(
                    {
                        "index": file_index,
                        "filename": image.filename,
                        "status": "success",
                        "record_count": len(response.positions),
                        "error": None,
                    }
                )
            except Exception as exc:
                file_results.append(
                    {
                        "index": file_index,
                        "filename": image.filename,
                        "status": "failed",
                        "record_count": 0,
                        "error": getattr(exc, "code", "vision_failed"),
                    }
                )

        return {
            "batch_id": str(uuid.uuid4()),
            "account_id": account_id,
            "snapshot_date": snapshot_date.isoformat(),
            "files": file_results,
            "summary": summary,
            "positions": self._merge_positions(positions),
        }

    def parse_trade_images(
        self,
        *,
        account_id: int,
        default_trade_date: date,
        images: List[ImageInput],
    ) -> Dict[str, Any]:
        self._validate_image_batch(images)
        self._validate_import_date(default_trade_date, field_name="default_trade_date")
        self._require_cn_cny_account(account_id)

        file_results: List[Dict[str, Any]] = []
        trades: List[Dict[str, Any]] = []
        for file_index, image in enumerate(images):
            try:
                prompt = f"{TRADE_EXTRACTION_PROMPT}\n当行没有日期时使用批次日期 {default_trade_date.isoformat()}。"
                raw_text = self.vision_complete(
                    image.content,
                    image.mime_type,
                    prompt,
                    max_tokens=3072,
                )
                response = _TradeVisionResponse.model_validate(_decode_json_object(raw_text))
                occurrences: Dict[str, int] = {}
                for row_index, row in enumerate(response.trades):
                    item = self._normalize_trade_row(
                        row,
                        default_trade_date=default_trade_date,
                        file_index=file_index,
                        row_index=row_index,
                        document_type=response.document_type,
                    )
                    if item["fingerprint"]:
                        occurrences[item["fingerprint"]] = occurrences.get(item["fingerprint"], 0) + 1
                        item["occurrence_index"] = occurrences[item["fingerprint"]]
                        item["dedup_hash"] = build_trade_dedup_hash(item, item["occurrence_index"])
                    trades.append(item)
                file_results.append(
                    {
                        "index": file_index,
                        "filename": image.filename,
                        "status": "success",
                        "record_count": len(response.trades),
                        "error": None,
                    }
                )
            except Exception as exc:
                file_results.append(
                    {
                        "index": file_index,
                        "filename": image.filename,
                        "status": "failed",
                        "record_count": 0,
                        "error": getattr(exc, "code", "vision_failed"),
                    }
                )

        self._mark_cross_image_overlaps(trades)
        return {
            "batch_id": str(uuid.uuid4()),
            "account_id": account_id,
            "default_trade_date": default_trade_date.isoformat(),
            "files": file_results,
            "trades": trades,
        }

    def commit_initial_positions(
        self,
        *,
        account_id: int,
        batch_id: str,
        snapshot_date: date,
        positions: List[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        del batch_id
        self._validate_import_date(snapshot_date, field_name="snapshot_date")
        if not positions:
            raise ValueError("positions must not be empty")

        normalized: List[Dict[str, Any]] = []
        seen_symbols: set[str] = set()
        for item in positions:
            symbol = str(item.get("symbol") or "").strip()
            name = str(item.get("name") or "").strip()
            if not re.fullmatch(r"\d{6}", symbol):
                raise ValueError("position symbol must be a 6-digit China market code")
            if not name:
                raise ValueError("position name is required")
            if symbol in seen_symbols:
                raise ValueError(f"duplicate position symbol: {symbol}")
            seen_symbols.add(symbol)
            quantity = float(item.get("quantity") or 0)
            avg_cost = float(item.get("avg_cost") or 0)
            if quantity <= 0 or avg_cost <= 0:
                raise ValueError("position quantity and avg_cost must be > 0")
            identity = f"{account_id}|{snapshot_date.isoformat()}|{symbol}"
            normalized.append(
                self.portfolio_service.normalize_trade_fields(
                    symbol=symbol,
                    trade_date=snapshot_date,
                    side="buy",
                    quantity=quantity,
                    price=avg_cost,
                    fee=0,
                    tax=0,
                    market="cn",
                    currency="CNY",
                    trade_uid=f"image-position:{identity}",
                    dedup_hash=hashlib.sha256(
                        f"portfolio_image_position|{identity}|{_normalize_decimal_text(quantity)}|"
                        f"{_normalize_decimal_text(avg_cost)}".encode("utf-8")
                    ).hexdigest(),
                    note="image_position_init",
                )
            )

        with self.repo.portfolio_write_session() as session:
            account = self._require_cn_cny_account_in_session(session=session, account_id=account_id)
            existing = self.repo.list_trades_in_session(
                session=session,
                account_id=account_id,
                as_of=date.max,
            )
            if existing:
                raise AccountNotEmptyError(f"Account already contains trades: {account_id}")
            for trade in normalized:
                self.portfolio_service.add_normalized_trade_in_session(
                    session=session,
                    account=account,
                    account_id=account_id,
                    trade=trade,
                    validate_sell=False,
                )

        return {
            "record_count": len(positions),
            "inserted_count": len(positions),
            "duplicate_count": 0,
            "failed_count": 0,
            "errors": [],
        }

    def commit_trade_batch(
        self,
        *,
        account_id: int,
        batch_id: str,
        trades: List[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        del batch_id
        if not trades:
            raise ValueError("trades must not be empty")

        normalized: List[Dict[str, Any]] = []
        used_occurrences: Dict[str, set[int]] = {}
        for input_index, item in enumerate(trades):
            symbol = str(item.get("symbol") or "").strip()
            if not re.fullmatch(r"\d{6}", symbol):
                raise ValueError("trade symbol must be a 6-digit China market code")
            occurrence_index = item.get("occurrence_index")
            if isinstance(occurrence_index, bool) or not isinstance(occurrence_index, int) or occurrence_index < 1:
                raise ValueError("occurrence_index must be an integer >= 1")
            trade_date = self._coerce_date(item.get("trade_date"), field_name="trade_date")
            self._validate_import_date(trade_date, field_name="trade_date")
            trade = self.portfolio_service.normalize_trade_fields(
                symbol=symbol,
                trade_date=trade_date,
                trade_time=item.get("trade_time"),
                side=str(item.get("side") or ""),
                quantity=float(item.get("quantity") or 0),
                price=float(item.get("price") or 0),
                fee=float(item.get("fee", 0) or 0),
                tax=float(item.get("tax", 0) or 0),
                market="cn",
                currency="CNY",
                trade_uid=str(item.get("trade_uid") or "").strip() or None,
                note="image_trade_import",
            )
            fingerprint_record = self._trade_to_fingerprint_record(trade)
            fingerprint = build_trade_fingerprint(fingerprint_record)
            fingerprint_occurrences = used_occurrences.setdefault(fingerprint, set())
            if occurrence_index in fingerprint_occurrences:
                raise ValueError("duplicate occurrence_index for identical trade fingerprint")
            fingerprint_occurrences.add(occurrence_index)
            trade["dedup_hash"] = build_trade_dedup_hash(
                fingerprint_record,
                occurrence_index,
            )
            trade["_input_index"] = input_index
            normalized.append(trade)

        duplicate_count = 0
        with self.repo.portfolio_write_session() as session:
            account = self._require_cn_cny_account_in_session(session=session, account_id=account_id)
            existing_trades = self.repo.list_trades_in_session(
                session=session,
                account_id=account_id,
                as_of=date.max,
            )
            new_trades: List[Dict[str, Any]] = []
            seen_uids: set[str] = set()
            seen_hashes: set[str] = set()
            for trade in normalized:
                trade_uid = trade.get("trade_uid")
                dedup_hash = str(trade["dedup_hash"])
                uid_duplicate = bool(
                    trade_uid
                    and (
                        trade_uid in seen_uids
                        or self.repo.has_trade_uid_in_session(
                            session=session,
                            account_id=account_id,
                            trade_uid=trade_uid,
                        )
                    )
                )
                hash_duplicate = dedup_hash in seen_hashes or self.repo.has_trade_dedup_hash_in_session(
                    session=session,
                    account_id=account_id,
                    dedup_hash=dedup_hash,
                )
                if uid_duplicate or hash_duplicate:
                    duplicate_count += 1
                    continue
                if trade_uid:
                    seen_uids.add(trade_uid)
                seen_hashes.add(dedup_hash)
                new_trades.append(trade)

            self._validate_candidate_timeline(
                session=session,
                account_id=account_id,
                existing_trades=existing_trades,
                new_trades=new_trades,
            )
            ordered_new_trades = sorted(
                new_trades,
                key=lambda trade: (
                    trade["trade_date"],
                    trade.get("trade_time") is None,
                    trade.get("trade_time") or dt_time.min,
                    trade["_input_index"],
                ),
            )
            for trade in ordered_new_trades:
                self.portfolio_service.add_normalized_trade_in_session(
                    session=session,
                    account=account,
                    account_id=account_id,
                    trade=trade,
                    validate_sell=False,
                    validate_identity=True,
                )

        return {
            "record_count": len(trades),
            "inserted_count": len(normalized) - duplicate_count,
            "duplicate_count": duplicate_count,
            "failed_count": 0,
            "errors": [],
        }

    @staticmethod
    def _validate_image_batch(images: List[ImageInput]) -> None:
        if not 1 <= len(images) <= 5:
            raise ValueError("image batch must contain 1-5 files")

    @staticmethod
    def _validate_import_date(value: date, *, field_name: str) -> None:
        if value > date.today():
            raise ValueError(f"{field_name} cannot be in the future")

    def _require_cn_cny_account(self, account_id: int) -> Any:
        account = self.repo.get_account(account_id)
        if account is None:
            raise ValueError(f"Account not found or inactive: {account_id}")
        if (account.market or "").strip().lower() != "cn" or (
            account.base_currency or ""
        ).strip().upper() != "CNY":
            raise ValueError("Screenshot import currently supports cn/CNY accounts only")
        return account

    def _require_cn_cny_account_in_session(self, *, session: Any, account_id: int) -> Any:
        account = self.repo.get_account_in_session(session=session, account_id=account_id)
        if account is None:
            raise ValueError(f"Account not found or inactive: {account_id}")
        if (account.market or "").strip().lower() != "cn" or (
            account.base_currency or ""
        ).strip().upper() != "CNY":
            raise ValueError("Screenshot import currently supports cn/CNY accounts only")
        return account

    @staticmethod
    def _coerce_date(value: Any, *, field_name: str) -> date:
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value or ""))
        except ValueError as exc:
            raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc

    @staticmethod
    def _trade_to_fingerprint_record(trade: Mapping[str, Any]) -> Dict[str, Any]:
        trade_time = trade.get("trade_time")
        return {
            "trade_date": trade["trade_date"].isoformat(),
            "trade_time": trade_time.isoformat(timespec="seconds") if trade_time else None,
            "symbol": trade["symbol"],
            "side": trade["side"],
            "quantity": trade["quantity"],
            "price": trade["price"],
            "fee": trade["fee"],
            "tax": trade["tax"],
        }

    def _validate_candidate_timeline(
        self,
        *,
        session: Any,
        account_id: int,
        existing_trades: List[Any],
        new_trades: List[Mapping[str, Any]],
    ) -> None:
        corporate_actions = self.repo.list_corporate_actions_in_session(
            session=session,
            account_id=account_id,
            as_of=date.max,
        )
        events: Dict[Tuple[str, str, str], Dict[date, Dict[str, List[Dict[str, Any]]]]] = {}

        def day_bucket(key: Tuple[str, str, str], event_date: date) -> Dict[str, List[Dict[str, Any]]]:
            return events.setdefault(key, {}).setdefault(event_date, {"actions": [], "trades": []})

        for row in corporate_actions:
            key = self._position_key(row.symbol, row.market, row.currency)
            day_bucket(key, row.effective_date)["actions"].append(
                {
                    "action_type": (row.action_type or "").strip().lower(),
                    "split_ratio": float(row.split_ratio or 0),
                    "stable_order": int(row.id),
                }
            )
        for row in existing_trades:
            key = self._position_key(row.symbol, row.market, row.currency)
            day_bucket(key, row.trade_date)["trades"].append(
                {
                    "side": (row.side or "").strip().lower(),
                    "quantity": float(row.quantity or 0),
                    "trade_time": row.trade_time,
                    "stable_order": int(row.id),
                    "is_new": False,
                }
            )
        for trade in new_trades:
            key = self._position_key(str(trade["symbol"]), "cn", "CNY")
            day_bucket(key, trade["trade_date"])["trades"].append(
                {
                    "side": trade["side"],
                    "quantity": float(trade["quantity"]),
                    "trade_time": trade.get("trade_time"),
                    "stable_order": int(trade["_input_index"]),
                    "is_new": True,
                }
            )

        for key, days in events.items():
            quantity = 0.0
            for event_date in sorted(days):
                bucket = days[event_date]
                for action in sorted(bucket["actions"], key=lambda item: item["stable_order"]):
                    if action["action_type"] != "split_adjustment":
                        continue
                    if action["split_ratio"] <= 0:
                        raise ValueError(f"Invalid split_ratio for {key[0]}")
                    quantity *= action["split_ratio"]

                day_trades = bucket["trades"]
                has_new = any(item["is_new"] for item in day_trades)
                has_null_time = any(item["trade_time"] is None for item in day_trades)
                if has_new and has_null_time:
                    optimistic = self._order_null_time_trades(day_trades, optimistic=True)
                    pessimistic = self._order_null_time_trades(day_trades, optimistic=False)
                    optimistic_result = self._simulate_trade_sequence(
                        quantity,
                        optimistic,
                        symbol=key[0],
                        trade_date=event_date,
                    )
                    if optimistic_result is None:
                        self._raise_first_oversell(
                            quantity,
                            optimistic,
                            symbol=key[0],
                            trade_date=event_date,
                        )
                    pessimistic_result = self._simulate_trade_sequence(
                        quantity,
                        pessimistic,
                        symbol=key[0],
                        trade_date=event_date,
                    )
                    if pessimistic_result is None:
                        raise AmbiguousTradeOrderError(
                            f"Same-day trade order is ambiguous for {key[0]} on {event_date.isoformat()}"
                        )
                    quantity = optimistic_result
                    continue

                ordered = sorted(
                    day_trades,
                    key=lambda item: (
                        item["trade_time"] is None,
                        item["trade_time"] or dt_time.min,
                        item["stable_order"],
                    ),
                )
                result = self._simulate_trade_sequence(
                    quantity,
                    ordered,
                    symbol=key[0],
                    trade_date=event_date,
                )
                if result is None:
                    self._raise_first_oversell(
                        quantity,
                        ordered,
                        symbol=key[0],
                        trade_date=event_date,
                    )
                quantity = result

    @staticmethod
    def _position_key(symbol: str, market: str, currency: str) -> Tuple[str, str, str]:
        return (
            PortfolioService._normalize_symbol_for_position(symbol),
            PortfolioService._normalize_market(market),
            PortfolioService._normalize_currency(currency),
        )

    @staticmethod
    def _order_null_time_trades(
        trades: List[Dict[str, Any]],
        *,
        optimistic: bool,
    ) -> List[Dict[str, Any]]:
        known = sorted(
            (item for item in trades if item["trade_time"] is not None),
            key=lambda item: (item["trade_time"], item["stable_order"]),
        )
        null_buys = sorted(
            (item for item in trades if item["trade_time"] is None and item["side"] == "buy"),
            key=lambda item: item["stable_order"],
        )
        null_sells = sorted(
            (item for item in trades if item["trade_time"] is None and item["side"] == "sell"),
            key=lambda item: item["stable_order"],
        )
        if optimistic:
            return [*null_buys, *known, *null_sells]
        return [*null_sells, *known, *null_buys]

    @staticmethod
    def _simulate_trade_sequence(
        starting_quantity: float,
        trades: List[Mapping[str, Any]],
        *,
        symbol: str,
        trade_date: date,
    ) -> Optional[float]:
        del symbol, trade_date
        quantity = starting_quantity
        for trade in trades:
            trade_quantity = float(trade["quantity"])
            if trade["side"] == "buy":
                quantity += trade_quantity
            elif quantity + EPS < trade_quantity:
                return None
            else:
                quantity -= trade_quantity
                if quantity <= EPS:
                    quantity = 0.0
        return quantity

    @staticmethod
    def _raise_first_oversell(
        starting_quantity: float,
        trades: List[Mapping[str, Any]],
        *,
        symbol: str,
        trade_date: date,
    ) -> None:
        quantity = starting_quantity
        for trade in trades:
            trade_quantity = float(trade["quantity"])
            if trade["side"] == "buy":
                quantity += trade_quantity
                continue
            if quantity + EPS < trade_quantity:
                raise PortfolioOversellError(
                    symbol=symbol,
                    trade_date=trade_date,
                    requested_quantity=trade_quantity,
                    available_quantity=quantity,
                )
            quantity -= trade_quantity
        raise ValueError("Invalid candidate trade timeline")

    @staticmethod
    def _normalize_position_row(
        row: _PositionVisionRow,
        *,
        file_index: int,
        row_index: int,
    ) -> Dict[str, Any]:
        symbol = (row.symbol or "").strip()
        name = (row.name or "").strip()
        issues: List[str] = []
        if not re.fullmatch(r"\d{6}", symbol):
            issues.append("invalid_symbol")
        if not name:
            issues.append("missing_name")
        if row.quantity is None or row.quantity <= 0:
            issues.append("invalid_quantity")
        if row.avg_cost is None or row.avg_cost <= 0:
            issues.append("invalid_avg_cost")

        return {
            "source_refs": [{"file_index": file_index, "row_index": row_index}],
            "symbol": symbol,
            "name": name,
            "quantity": row.quantity,
            "avg_cost": row.avg_cost,
            "current_price": row.current_price,
            "market_value": row.market_value,
            "available_quantity": row.available_quantity,
            "weight_pct": row.weight_pct,
            "profit_loss": row.profit_loss,
            "confidence": row.confidence if row.confidence in {"high", "medium", "low"} else "low",
            "status": "error" if issues else "ready",
            "issues": issues,
        }

    @staticmethod
    def _normalize_trade_row(
        row: _TradeVisionRow,
        *,
        default_trade_date: date,
        file_index: int,
        row_index: int,
        document_type: str,
    ) -> Dict[str, Any]:
        issues: List[str] = []
        raw_date = (row.trade_date or "").strip()
        try:
            trade_date = date.fromisoformat(raw_date) if raw_date else default_trade_date
        except ValueError:
            trade_date = default_trade_date
            issues.append("invalid_trade_date")
        if trade_date > date.today():
            issues.append("future_trade_date")

        raw_time = (row.trade_time or "").strip()
        trade_time: Optional[str] = None
        if raw_time:
            try:
                if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", raw_time):
                    raise ValueError
                parsed_time = dt_time.fromisoformat(raw_time)
                if parsed_time.tzinfo is not None:
                    raise ValueError
                trade_time = parsed_time.isoformat(timespec="seconds")
            except ValueError:
                issues.append("invalid_trade_time")

        symbol = (row.symbol or "").strip()
        if not re.fullmatch(r"\d{6}", symbol):
            issues.append("invalid_symbol")
        name = (row.name or "").strip()
        if not name:
            issues.append("missing_name")

        side_map = {"buy": "buy", "买入": "buy", "b": "buy", "sell": "sell", "卖出": "sell", "s": "sell"}
        side = side_map.get((row.side or "").strip().lower())
        if side is None:
            issues.append("invalid_side")
            side = ""
        if row.quantity is None or row.quantity <= 0:
            issues.append("invalid_quantity")
        if row.price is None or row.price <= 0:
            issues.append("invalid_price")
        if row.fee is not None and row.fee < 0:
            issues.append("invalid_fee")
        if row.tax is not None and row.tax < 0:
            issues.append("invalid_tax")

        record_type = (row.record_type or "").strip().lower()
        if record_type != "executed_trade" or document_type not in {
            "today_trades",
            "historical_trades",
            "settlement",
        }:
            issues.append("not_executed_trade")

        fee = float(row.fee) if row.fee is not None else 0.0
        tax = float(row.tax) if row.tax is not None else 0.0
        if row.fee is None:
            issues.append("fee_defaulted")
        if row.tax is None:
            issues.append("tax_defaulted")

        fatal_issues = {
            "invalid_trade_date",
            "future_trade_date",
            "invalid_trade_time",
            "invalid_symbol",
            "invalid_side",
            "invalid_quantity",
            "invalid_price",
            "invalid_fee",
            "invalid_tax",
            "not_executed_trade",
        }
        item: Dict[str, Any] = {
            "source_refs": [{"file_index": file_index, "row_index": row_index}],
            "trade_date": trade_date.isoformat(),
            "trade_time": trade_time,
            "symbol": symbol,
            "name": name,
            "side": side,
            "quantity": row.quantity,
            "price": row.price,
            "fee": fee,
            "tax": tax,
            "trade_uid": (row.trade_uid or "").strip() or None,
            "confidence": row.confidence if row.confidence in {"high", "medium", "low"} else "low",
            "occurrence_index": 1,
            "fingerprint": "",
            "dedup_hash": None,
            "status": "error" if fatal_issues.intersection(issues) else "ready",
            "issues": issues,
        }
        if item["status"] != "error":
            item["fingerprint"] = build_trade_fingerprint(item)
        return item

    @staticmethod
    def _mark_cross_image_overlaps(trades: List[Dict[str, Any]]) -> None:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in trades:
            if item["fingerprint"]:
                grouped.setdefault(item["fingerprint"], []).append(item)
        for items in grouped.values():
            file_indexes = {
                source["file_index"]
                for item in items
                for source in item["source_refs"]
            }
            if len(file_indexes) < 2:
                continue
            for item in items:
                item["status"] = "conflict"
                if "ambiguous_overlap" not in item["issues"]:
                    item["issues"].append("ambiguous_overlap")

    @staticmethod
    def _merge_positions(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        by_symbol: Dict[str, Dict[str, Any]] = {}
        for item in positions:
            symbol = item["symbol"]
            if item["status"] == "error" or not symbol:
                merged.append(item)
                continue
            existing = by_symbol.get(symbol)
            if existing is None:
                by_symbol[symbol] = item
                merged.append(item)
                continue

            existing["source_refs"].extend(item["source_refs"])
            if not _decimal_equal(existing["quantity"], item["quantity"]) or not _decimal_equal(
                existing["avg_cost"], item["avg_cost"]
            ):
                existing["status"] = "conflict"
                if "position_conflict" not in existing["issues"]:
                    existing["issues"].append("position_conflict")
            if existing["name"] != item["name"] and "name_mismatch" not in existing["issues"]:
                existing["issues"].append("name_mismatch")
        return merged
