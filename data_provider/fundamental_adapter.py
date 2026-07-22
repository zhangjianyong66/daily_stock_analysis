# -*- coding: utf-8 -*-
"""
AkShare fundamental adapter (fail-open).

This adapter intentionally uses capability probing against multiple AkShare
endpoint candidates. It should never raise to caller; partial data is allowed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.services.market_symbol_utils import is_cn_etf_symbol

logger = logging.getLogger(__name__)

_DIVIDEND_KEYWORD_MAP: Dict[str, List[str]] = {
    "per_share": [
        "每股派息",
        "每股现金红利",
        "每股分红",
        "每股派现",
        "派现(元/股)",
        "派息(元/股)",
        "税前派息(元/股)",
        "现金分红(税前)",
    ],
    "plan_text": [
        "分配方案",
        "分红方案",
        "实施方案",
        "派息方案",
        "方案",
        "预案",
        "方案说明",
    ],
    "ex_dividend_date": ["除权除息日", "除息日", "除权日", "除权除息", "除息日期"],
    "record_date": ["股权登记日", "登记日"],
    "announce_date": ["公告日期", "公告日", "实施公告日", "预案公告日"],
    "report_date": ["报告期", "报告日期", "截止日期", "统计截止日期"],
}


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    try:
        return parsed.to_pydatetime()
    except Exception:
        return None


def _normalize_code(raw: Any) -> str:
    s = _safe_str(raw).upper()
    if "." in s:
        s = s.split(".", 1)[0]
    s = re.sub(r"^(SH|SZ|BJ)", "", s)
    return s


def _pick_by_keywords(row: pd.Series, keywords: List[str]) -> Optional[Any]:
    """
    Return first non-empty row value whose column name contains any keyword.
    """
    for col in row.index:
        col_s = str(col)
        if any(k in col_s for k in keywords):
            val = row.get(col)
            if val is not None and str(val).strip() not in ("", "-", "nan", "None"):
                return val
    return None


def _parse_dividend_plan_to_per_share(plan_text: str) -> Optional[float]:
    """Parse per-share cash dividend from Chinese plan text."""
    text = _safe_str(plan_text)
    if not text:
        return None

    for pattern in (
        r"(?:每)?\s*10\s*股?\s*派(?:发)?\s*([0-9]+(?:\.[0-9]+)?)\s*元",
        r"10\s*派\s*([0-9]+(?:\.[0-9]+)?)\s*元",
    ):
        match = re.search(pattern, text)
        if match:
            parsed = _safe_float(match.group(1))
            if parsed is not None and parsed > 0:
                return parsed / 10.0

    match_per_share = re.search(r"每\s*股\s*派(?:发)?\s*([0-9]+(?:\.[0-9]+)?)\s*元", text)
    if match_per_share:
        parsed = _safe_float(match_per_share.group(1))
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _extract_cash_dividend_per_share(row: pd.Series) -> Optional[float]:
    """Extract pre-tax cash dividend per share from a row."""
    plan_text = _safe_str(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["plan_text"]))
    # Keep pre-tax semantics; skip explicit after-tax plans unless pre-tax marker exists.
    if "税后" in plan_text and "税前" not in plan_text and "含税" not in plan_text:
        return None

    direct = _safe_float(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["per_share"]))
    if direct is not None and direct > 0:
        return direct
    return _parse_dividend_plan_to_per_share(plan_text)


def _filter_rows_by_code(df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码", "symbol", "ts_code"))]
    if not code_cols:
        return df

    target = _normalize_code(stock_code)
    for col in code_cols:
        try:
            series = df[col].astype(str).map(_normalize_code)
            filtered = df[series == target]
            if not filtered.empty:
                return filtered
        except Exception:
            continue
    return pd.DataFrame()


def _normalize_report_date(value: Any) -> Optional[str]:
    parsed = _safe_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _build_dividend_payload(
    dividend_df: pd.DataFrame,
    stock_code: str,
    max_events: int = 5,
) -> Dict[str, Any]:
    work_df = _filter_rows_by_code(dividend_df, stock_code)
    if work_df.empty:
        return {}

    now_date = datetime.now().date()
    ttm_start_date = now_date - timedelta(days=365)
    dedupe_keys = set()
    events: List[Dict[str, Any]] = []

    for _, row in work_df.iterrows():
        if not isinstance(row, pd.Series):
            continue
        ex_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["ex_dividend_date"]))
        record_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["record_date"]))
        announce_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["announce_date"]))
        event_dt = ex_dt or record_dt or announce_dt
        if event_dt is None:
            continue
        event_date = event_dt.date()
        if event_date > now_date:
            continue

        per_share = _extract_cash_dividend_per_share(row)
        if per_share is None or per_share <= 0:
            continue

        dedupe_key = (event_date.isoformat(), round(per_share, 6))
        if dedupe_key in dedupe_keys:
            continue
        dedupe_keys.add(dedupe_key)

        events.append(
            {
                "event_date": event_date.isoformat(),
                "ex_dividend_date": ex_dt.date().isoformat() if ex_dt else None,
                "record_date": record_dt.date().isoformat() if record_dt else None,
                "announcement_date": announce_dt.date().isoformat() if announce_dt else None,
                "cash_dividend_per_share": round(per_share, 6),
                "is_pre_tax": True,
            }
        )

    if not events:
        return {}

    events.sort(key=lambda item: item.get("event_date") or "", reverse=True)
    ttm_events: List[Dict[str, Any]] = []
    for item in events:
        event_dt = _safe_datetime(item.get("event_date"))
        if event_dt is None:
            continue
        event_date = event_dt.date()
        if ttm_start_date <= event_date <= now_date:
            ttm_events.append(item)

    return {
        "events": events[:max(1, max_events)],
        "ttm_event_count": len(ttm_events),
        "ttm_cash_dividend_per_share": (
            round(sum(float(item.get("cash_dividend_per_share") or 0.0) for item in ttm_events), 6)
            if ttm_events else None
        ),
        "coverage": "cash_dividend_pre_tax",
        "as_of": now_date.isoformat(),
    }


def _extract_latest_row(df: pd.DataFrame, stock_code: str) -> Optional[pd.Series]:
    """
    Select the most relevant row for the given stock.
    """
    if df is None or df.empty:
        return None

    code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码", "ts_code", "symbol"))]
    target = _normalize_code(stock_code)
    if code_cols:
        for col in code_cols:
            try:
                series = df[col].astype(str).map(_normalize_code)
                matched = df[series == target]
                if not matched.empty:
                    return matched.iloc[0]
            except Exception:
                continue
        return None

    # Fallback: use latest row
    return df.iloc[0]


def _capital_flow_market(stock_code: str) -> Optional[str]:
    """Return the AkShare/Eastmoney market argument for a CN symbol."""
    code = _normalize_code(stock_code)
    if not code.isdigit() or len(code) != 6:
        return None
    if code.startswith(("5", "6")):
        return "sh"
    if code.startswith(("0", "1", "2", "3")):
        return "sz"
    return None


def _normalized_column_name(value: Any) -> str:
    return re.sub(r"[\s_\-—－()（）%％]", "", str(value)).lower()


def _find_column(df: pd.DataFrame, aliases: List[str]) -> Optional[Any]:
    normalized_aliases = {_normalized_column_name(alias) for alias in aliases}
    for column in df.columns:
        if _normalized_column_name(column) in normalized_aliases:
            return column
    return None


def _sum_complete_window(values: List[Optional[float]], days: int, offset: int = 0) -> Optional[float]:
    window = values[offset:offset + days]
    if len(window) != days or any(value is None for value in window):
        return None
    return float(sum(value for value in window if value is not None))


def _build_daily_capital_flow(df: pd.DataFrame, stock_code: str) -> Dict[str, Any]:
    """Normalize Eastmoney daily fund-flow rows and calculate complete windows."""
    work_df = _filter_rows_by_code(df, stock_code)
    if work_df.empty:
        return {}

    date_col = _find_column(work_df, ["日期", "交易日期", "交易日", "date"])
    main_col = _find_column(work_df, ["主力净流入-净额", "主力净流入净额", "主力净流入", "主力净额"])
    if date_col is None or main_col is None:
        return {}

    work_df = work_df.copy()
    work_df["__flow_date"] = pd.to_datetime(work_df[date_col], errors="coerce")
    work_df = work_df.dropna(subset=["__flow_date"]).sort_values("__flow_date", ascending=False)
    if work_df.empty:
        return {}

    main_pct_col = _find_column(work_df, ["主力净流入-净占比", "主力净流入净占比", "主力净占比"])
    large_col = _find_column(work_df, ["大单净流入-净额", "大单净流入净额", "大单净流入", "大单净额"])
    large_pct_col = _find_column(work_df, ["大单净流入-净占比", "大单净流入净占比", "大单净占比"])
    super_large_col = _find_column(
        work_df,
        ["超大单净流入-净额", "超大单净流入净额", "超大单净流入", "超大单净额"],
    )
    super_large_pct_col = _find_column(
        work_df,
        ["超大单净流入-净占比", "超大单净流入净占比", "超大单净占比"],
    )

    rows = [row for _, row in work_df.iterrows()]
    main_values = [_safe_float(row.get(main_col)) for row in rows]
    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    latest_date = latest.get("__flow_date")
    previous_date = previous.get("__flow_date") if previous is not None else None

    return {
        "main_net_inflow": main_values[0],
        "main_net_inflow_pct": _safe_float(latest.get(main_pct_col)) if main_pct_col is not None else None,
        "previous_main_net_inflow": main_values[1] if len(main_values) > 1 else None,
        "previous_main_net_inflow_pct": (
            _safe_float(previous.get(main_pct_col))
            if previous is not None and main_pct_col is not None
            else None
        ),
        "inflow_3d": _sum_complete_window(main_values, 3),
        "previous_inflow_3d": _sum_complete_window(main_values, 3, offset=3),
        "positive_days_3d": (
            sum(1 for value in main_values[:3] if value is not None and value > 0)
            if len(main_values) >= 3 and all(value is not None for value in main_values[:3])
            else None
        ),
        "inflow_5d": _sum_complete_window(main_values, 5),
        "inflow_10d": _sum_complete_window(main_values, 10),
        "large_net_inflow": _safe_float(latest.get(large_col)) if large_col is not None else None,
        "large_net_inflow_pct": _safe_float(latest.get(large_pct_col)) if large_pct_col is not None else None,
        "super_large_net_inflow": (
            _safe_float(latest.get(super_large_col)) if super_large_col is not None else None
        ),
        "super_large_net_inflow_pct": (
            _safe_float(latest.get(super_large_pct_col)) if super_large_pct_col is not None else None
        ),
        "as_of": latest_date.date().isoformat() if latest_date is not None else None,
        "previous_as_of": previous_date.date().isoformat() if previous_date is not None else None,
        "scope": "daily",
        "source": "akshare.stock_individual_fund_flow",
        "data_quality": "complete" if main_values[0] is not None else "partial",
    }


def _aggregate_intraday_capital_flow(df: pd.DataFrame) -> Dict[str, Any]:
    """Aggregate only vendor-classified buy/sell/neutral intraday trades."""
    if df is None or df.empty:
        return {}

    side_col = _find_column(df, ["买卖盘性质", "性质", "方向", "side"])
    amount_col = _find_column(df, ["成交额", "成交金额", "金额", "amount"])
    price_col = _find_column(df, ["成交价", "价格", "price"])
    lots_col = _find_column(df, ["手数", "成交手数", "lots"])
    volume_col = _find_column(df, ["成交量", "volume"])
    time_col = _find_column(df, ["时间", "成交时间", "time"])
    if side_col is None or (amount_col is None and price_col is None):
        return {}

    totals = {"buy": 0.0, "sell": 0.0, "neutral": 0.0}
    counts = {"buy": 0, "sell": 0, "neutral": 0}
    unclassified_count = 0
    latest_time = ""

    for _, row in df.iterrows():
        raw_side = _safe_str(row.get(side_col)).strip().lower()
        if raw_side in {"买盘", "买入", "主动买入", "b", "buy"}:
            side = "buy"
        elif raw_side in {"卖盘", "卖出", "主动卖出", "s", "sell"}:
            side = "sell"
        elif raw_side in {"中性盘", "中性", "n", "neutral"}:
            side = "neutral"
        else:
            unclassified_count += 1
            continue

        amount = _safe_float(row.get(amount_col)) if amount_col is not None else None
        if amount is None:
            price = _safe_float(row.get(price_col)) if price_col is not None else None
            if lots_col is not None:
                quantity = _safe_float(row.get(lots_col))
                quantity = quantity * 100.0 if quantity is not None else None
            else:
                quantity = _safe_float(row.get(volume_col)) if volume_col is not None else None
            amount = price * quantity if price is not None and quantity is not None else None
        if amount is None or amount < 0:
            continue

        totals[side] += amount
        counts[side] += 1
        if time_col is not None:
            latest_time = max(latest_time, _safe_str(row.get(time_col)))

    classified_count = sum(counts.values())
    if classified_count == 0:
        return {}

    now = datetime.now().astimezone()
    as_of = now.isoformat(timespec="seconds")
    if latest_time and re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", latest_time):
        as_of = f"{now.date().isoformat()}T{latest_time}{now.strftime('%z')}"

    return {
        "active_buy_amount": totals["buy"],
        "active_sell_amount": totals["sell"],
        "active_net_inflow": totals["buy"] - totals["sell"],
        "neutral_amount": totals["neutral"],
        "trade_count": classified_count,
        "unclassified_trade_count": unclassified_count,
        "as_of": as_of,
        "scope": "intraday",
        "classification": "vendor_classified",
        "is_estimated": True,
        "source": "akshare.stock_intraday_em",
    }


class AkshareFundamentalAdapter:
    """AkShare adapter for fundamentals, capital flow and dragon-tiger signals."""

    def _call_df_candidates(
        self,
        candidates: List[Tuple[str, Dict[str, Any]]],
    ) -> Tuple[Optional[pd.DataFrame], Optional[str], List[str]]:
        errors: List[str] = []
        try:
            import akshare as ak
        except Exception as exc:
            return None, None, [f"import_akshare:{type(exc).__name__}"]

        for func_name, kwargs in candidates:
            fn = getattr(ak, func_name, None)
            if fn is None:
                continue
            try:
                df = fn(**kwargs)
                if isinstance(df, pd.Series):
                    df = df.to_frame().T
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df, func_name, errors
            except Exception as exc:
                errors.append(f"{func_name}:{type(exc).__name__}")
                continue
        return None, None, errors

    def get_fundamental_bundle(self, stock_code: str) -> Dict[str, Any]:
        """
        Return normalized fundamental blocks from AkShare with partial tolerance.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "growth": {},
            "earnings": {},
            "institution": {},
            "source_chain": [],
            "errors": [],
        }

        # Financial indicators
        fin_df, fin_source, fin_errors = self._call_df_candidates([
            ("stock_financial_abstract", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator", {}),
        ])
        result["errors"].extend(fin_errors)
        if fin_df is not None:
            row = _extract_latest_row(fin_df, stock_code)
            if row is not None:
                revenue_yoy = _safe_float(_pick_by_keywords(row, ["营业收入同比", "营收同比", "收入同比", "同比增长"]))
                profit_yoy = _safe_float(_pick_by_keywords(row, ["净利润同比", "净利同比", "归母净利润同比"]))
                roe = _safe_float(_pick_by_keywords(row, ["净资产收益率", "ROE", "净资产收益"]))
                gross_margin = _safe_float(_pick_by_keywords(row, ["毛利率"]))
                report_date = _normalize_report_date(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["report_date"]))
                revenue = _safe_float(_pick_by_keywords(row, ["营业总收入", "营业收入", "营收"]))
                net_profit_parent = _safe_float(_pick_by_keywords(row, ["归母净利润", "母公司股东净利润", "净利润"]))
                operating_cash_flow = _safe_float(
                    _pick_by_keywords(row, ["经营活动产生的现金流量净额", "经营现金流", "经营活动现金流"])
                )
                result["growth"] = {
                    "revenue_yoy": revenue_yoy,
                    "net_profit_yoy": profit_yoy,
                    "roe": roe,
                    "gross_margin": gross_margin,
                }
                financial_report_payload = {
                    "report_date": report_date,
                    "revenue": revenue,
                    "net_profit_parent": net_profit_parent,
                    "operating_cash_flow": operating_cash_flow,
                    "roe": roe,
                }
                if any(v is not None for v in financial_report_payload.values()):
                    result["earnings"]["financial_report"] = financial_report_payload
                result["source_chain"].append(f"growth:{fin_source}")

        # Earnings forecast
        forecast_df, forecast_source, forecast_errors = self._call_df_candidates([
            ("stock_yjyg_em", {"symbol": stock_code}),
            ("stock_yjyg_em", {}),
            ("stock_yjbb_em", {"symbol": stock_code}),
            ("stock_yjbb_em", {}),
        ])
        result["errors"].extend(forecast_errors)
        if forecast_df is not None:
            row = _extract_latest_row(forecast_df, stock_code)
            if row is not None:
                result["earnings"]["forecast_summary"] = _safe_str(
                    _pick_by_keywords(row, ["预告", "业绩变动", "内容", "摘要", "公告"])
                )[:200]
                result["source_chain"].append(f"earnings_forecast:{forecast_source}")

        # Earnings quick report
        quick_df, quick_source, quick_errors = self._call_df_candidates([
            ("stock_yjkb_em", {"symbol": stock_code}),
            ("stock_yjkb_em", {}),
        ])
        result["errors"].extend(quick_errors)
        if quick_df is not None:
            row = _extract_latest_row(quick_df, stock_code)
            if row is not None:
                result["earnings"]["quick_report_summary"] = _safe_str(
                    _pick_by_keywords(row, ["快报", "摘要", "公告", "说明"])
                )[:200]
                result["source_chain"].append(f"earnings_quick:{quick_source}")

        # Dividend details (cash dividend, pre-tax)
        dividend_df, dividend_source, dividend_errors = self._call_df_candidates([
            ("stock_fhps_detail_em", {"symbol": stock_code}),
            ("stock_history_dividend_detail", {"symbol": stock_code, "indicator": "分红", "date": ""}),
            ("stock_dividend_cninfo", {"symbol": stock_code}),
        ])
        result["errors"].extend(dividend_errors)
        if dividend_df is not None:
            dividend_payload = _build_dividend_payload(dividend_df, stock_code, max_events=5)
            if dividend_payload:
                result["earnings"]["dividend"] = dividend_payload
                result["source_chain"].append(f"dividend:{dividend_source}")

        # Institution / top shareholders
        inst_df, inst_source, inst_errors = self._call_df_candidates([
            ("stock_institute_hold", {}),
            ("stock_institute_recommend", {}),
        ])
        result["errors"].extend(inst_errors)
        if inst_df is not None:
            row = _extract_latest_row(inst_df, stock_code)
            if row is not None:
                inst_change = _safe_float(_pick_by_keywords(row, ["增减", "变化", "变动", "持股变化"]))
                result["institution"]["institution_holding_change"] = inst_change
                result["source_chain"].append(f"institution:{inst_source}")

        top10_df, top10_source, top10_errors = self._call_df_candidates([
            ("stock_gdfx_top_10_em", {"symbol": stock_code}),
            ("stock_gdfx_top_10_em", {}),
            ("stock_zh_a_gdhs_detail_em", {"symbol": stock_code}),
            ("stock_zh_a_gdhs_detail_em", {}),
        ])
        result["errors"].extend(top10_errors)
        if top10_df is not None:
            row = _extract_latest_row(top10_df, stock_code)
            if row is not None:
                holder_change = _safe_float(_pick_by_keywords(row, ["增减", "变化", "持股变化", "变动"]))
                result["institution"]["top10_holder_change"] = holder_change
                result["source_chain"].append(f"top10:{top10_source}")

        has_content = bool(result["growth"] or result["earnings"] or result["institution"])
        result["status"] = "partial" if has_content else "not_supported"
        return result

    def get_intraday_capital_flow(self, stock_code: str) -> Dict[str, Any]:
        """Return an ETF intraday flow estimate without affecting complete-day flow."""
        result: Dict[str, Any] = {
            "status": "not_supported",
            "intraday_flow": {},
            "source_chain": [],
            "errors": [],
            "limitations": [],
        }
        if not is_cn_etf_symbol(stock_code):
            result["limitations"].append("intraday_trade_direction_not_applicable")
            return result

        intraday_df, intraday_source, intraday_errors = self._call_df_candidates([
            ("stock_intraday_em", {"symbol": stock_code}),
        ])
        result["errors"].extend(intraday_errors)
        if intraday_df is not None:
            result["intraday_flow"] = _aggregate_intraday_capital_flow(intraday_df)
        if result["intraday_flow"]:
            result["status"] = "ok"
            result["source_chain"].append(f"capital_intraday:{intraday_source}")
        else:
            result["status"] = "failed" if result["errors"] else "partial"
            result["limitations"].append("intraday_trade_direction_unavailable")
        return result

    def get_capital_flow(
        self,
        stock_code: str,
        top_n: int = 5,
        *,
        include_intraday: bool = True,
    ) -> Dict[str, Any]:
        """
        Return stock + sector capital flow.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "stock_flow": {},
            "intraday_flow": {},
            "sector_rankings": {"top": [], "bottom": []},
            "source_chain": [],
            "errors": [],
            "limitations": [],
        }

        market = _capital_flow_market(stock_code)
        individual_candidates: List[Tuple[str, Dict[str, Any]]] = []
        if market is not None:
            individual_candidates.extend([
                ("stock_individual_fund_flow", {"stock": stock_code, "market": market}),
                ("stock_individual_fund_flow", {"symbol": stock_code, "market": market}),
            ])
        individual_candidates.extend([
            ("stock_individual_fund_flow", {"stock": stock_code}),
            ("stock_individual_fund_flow", {"symbol": stock_code}),
            ("stock_main_fund_flow", {"symbol": stock_code}),
            ("stock_main_fund_flow", {}),
        ])
        stock_df, stock_source, stock_errors = self._call_df_candidates(individual_candidates)
        result["errors"].extend(stock_errors)
        if stock_df is not None:
            daily_flow = _build_daily_capital_flow(stock_df, stock_code)
            if daily_flow:
                result["stock_flow"] = daily_flow
                result["source_chain"].append(f"capital_stock:{stock_source}")
            else:
                row = _extract_latest_row(stock_df, stock_code)
                if row is not None:
                    result["stock_flow"] = {
                        "main_net_inflow": _safe_float(_pick_by_keywords(row, ["主力净流入", "净流入", "净额"])),
                        "inflow_5d": _safe_float(_pick_by_keywords(row, ["5日", "五日"])),
                        "inflow_10d": _safe_float(_pick_by_keywords(row, ["10日", "十日"])),
                        "scope": "daily",
                        "source": stock_source,
                        "data_quality": "partial",
                    }
                    result["source_chain"].append(f"capital_stock:{stock_source}")

        intraday_status = "not_requested"
        if is_cn_etf_symbol(stock_code) and include_intraday:
            intraday_result = self.get_intraday_capital_flow(stock_code)
            intraday_status = str(intraday_result.get("status") or "partial")
            result["intraday_flow"] = intraday_result.get("intraday_flow", {})
            result["source_chain"].extend(intraday_result.get("source_chain", []))
            result["errors"].extend(intraday_result.get("errors", []))
            result["limitations"].extend(intraday_result.get("limitations", []))

        if not is_cn_etf_symbol(stock_code):
            sector_df, sector_source, sector_errors = self._call_df_candidates([
                ("stock_sector_fund_flow_rank", {}),
                ("stock_sector_fund_flow_summary", {}),
            ])
            result["errors"].extend(sector_errors)
            if sector_df is not None:
                name_col = next(
                    (c for c in sector_df.columns if any(k in str(c) for k in ("板块", "行业", "名称", "name"))),
                    None,
                )
                flow_col = next(
                    (c for c in sector_df.columns if any(k in str(c) for k in ("净流入", "主力", "flow", "净额"))),
                    None,
                )
                if name_col and flow_col:
                    work_df = sector_df[[name_col, flow_col]].copy()
                    work_df[flow_col] = pd.to_numeric(work_df[flow_col], errors="coerce")
                    work_df = work_df.dropna(subset=[flow_col])
                    top_df = work_df.nlargest(top_n, flow_col)
                    bottom_df = work_df.nsmallest(top_n, flow_col)
                    result["sector_rankings"] = {
                        "top": [
                            {"name": _safe_str(r[name_col]), "net_inflow": float(r[flow_col])}
                            for _, r in top_df.iterrows()
                        ],
                        "bottom": [
                            {"name": _safe_str(r[name_col]), "net_inflow": float(r[flow_col])}
                            for _, r in bottom_df.iterrows()
                        ],
                    }
                    result["source_chain"].append(f"capital_sector:{sector_source}")

        has_content = bool(
            result["stock_flow"]
            or result["intraday_flow"]
            or result["sector_rankings"]["top"]
            or result["sector_rankings"]["bottom"]
        )
        if has_content:
            main_flow = result["stock_flow"].get("main_net_inflow") if result["stock_flow"] else None
            result["status"] = "ok" if main_flow is not None else "partial"
            if stock_errors or intraday_status == "partial" or (is_cn_etf_symbol(stock_code) and result["errors"]):
                result["status"] = "partial"
        else:
            result["status"] = "failed" if result["errors"] else "not_supported"
        return result

    def get_dragon_tiger_flag(self, stock_code: str, lookback_days: int = 20) -> Dict[str, Any]:
        """
        Return dragon-tiger signal in lookback window.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "is_on_list": False,
            "recent_count": 0,
            "latest_date": None,
            "source_chain": [],
            "errors": [],
        }

        df, source, errors = self._call_df_candidates([
            ("stock_lhb_stock_statistic_em", {}),
            ("stock_lhb_detail_em", {}),
            ("stock_lhb_jgmmtj_em", {}),
        ])
        result["errors"].extend(errors)
        if df is None:
            return result

        # Try code filter
        code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码"))]
        target = _normalize_code(stock_code)
        matched = pd.DataFrame()
        for col in code_cols:
            try:
                series = df[col].astype(str).map(_normalize_code)
                cur = df[series == target]
                if not cur.empty:
                    matched = cur
                    break
            except Exception:
                continue
        if matched.empty:
            result["source_chain"].append(f"dragon_tiger:{source}")
            result["status"] = "ok" if code_cols else "partial"
            return result

        date_col = next((c for c in matched.columns if any(k in str(c) for k in ("日期", "上榜", "交易日", "time"))), None)
        parsed_dates: List[datetime] = []
        if date_col is not None:
            for val in matched[date_col].astype(str).tolist():
                try:
                    parsed_dates.append(pd.to_datetime(val).to_pydatetime())
                except Exception:
                    continue
        now = datetime.now()
        start = now - timedelta(days=max(1, lookback_days))
        recent_dates = [d for d in parsed_dates if start <= d <= now]

        result["is_on_list"] = bool(recent_dates)
        result["recent_count"] = len(recent_dates) if recent_dates else int(len(matched))
        result["latest_date"] = max(recent_dates).date().isoformat() if recent_dates else (
            max(parsed_dates).date().isoformat() if parsed_dates else None
        )
        result["status"] = "ok"
        result["source_chain"].append(f"dragon_tiger:{source}")
        return result
