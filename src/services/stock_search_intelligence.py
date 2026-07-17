# -*- coding: utf-8 -*-
"""Deterministic query grouping and routing for non-ETF stock intelligence."""

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence


STOCK_INTEL_TEMPLATE_VERSION = "stock-intel-v1"
FRESH_GROUP = "fresh_events"
ANALYSIS_GROUP = "analysis"
FRESH_DIMENSIONS = ("latest_news", "risk_check", "announcements")
ANALYSIS_DIMENSIONS = ("market_analysis", "earnings", "industry")


@dataclass(frozen=True)
class StockSearchDimension:
    name: str
    query: str
    desc: str
    group_name: str
    strict_freshness: bool
    tavily_topic: Optional[str]


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def build_stock_dimensions(
    stock_code: str,
    stock_name: str,
    *,
    foreign: bool,
) -> tuple[StockSearchDimension, ...]:
    """Return the existing five Pipeline dimensions without changing Agent behavior."""
    if foreign:
        return (
            StockSearchDimension(
                "latest_news",
                f"{stock_name} {stock_code} latest news events",
                "最新消息",
                FRESH_GROUP,
                True,
                "news",
            ),
            StockSearchDimension(
                "market_analysis",
                f"{stock_name} {stock_code} analyst rating target price report",
                "机构分析",
                ANALYSIS_GROUP,
                False,
                None,
            ),
            StockSearchDimension(
                "risk_check",
                f"{stock_name} {stock_code} risk insider selling lawsuit litigation",
                "风险排查",
                FRESH_GROUP,
                True,
                "news",
            ),
            StockSearchDimension(
                "earnings",
                f"{stock_name} {stock_code} earnings revenue profit growth forecast",
                "业绩预期",
                ANALYSIS_GROUP,
                False,
                None,
            ),
            StockSearchDimension(
                "industry",
                f"{stock_name} {stock_code} industry competitors market share outlook",
                "行业分析",
                ANALYSIS_GROUP,
                False,
                None,
            ),
        )

    return (
        StockSearchDimension(
            "latest_news",
            f"{stock_name} {stock_code} 最新 新闻 重大 事件",
            "最新消息",
            FRESH_GROUP,
            True,
            "news",
        ),
        StockSearchDimension(
            "market_analysis",
            f"{stock_name} {stock_code} 研报 目标价 评级 深度分析",
            "机构分析",
            ANALYSIS_GROUP,
            False,
            None,
        ),
        StockSearchDimension(
            "risk_check",
            f"{stock_name} {stock_code} 减持 处罚 违规 诉讼 利空 风险",
            "风险排查",
            FRESH_GROUP,
            True,
            "news",
        ),
        StockSearchDimension(
            "announcements",
            f"{stock_name} {stock_code} 公司公告 重要公告 上交所 深交所 cninfo",
            "公司公告",
            FRESH_GROUP,
            True,
            "news",
        ),
        StockSearchDimension(
            "earnings",
            f"{stock_name} {stock_code} 业绩预告 财报 营收 净利润 同比增长",
            "业绩预期",
            ANALYSIS_GROUP,
            False,
            None,
        ),
    )


def enabled_stock_dimensions(
    stock_code: str,
    stock_name: str,
    *,
    foreign: bool,
    max_searches: int,
) -> tuple[StockSearchDimension, ...]:
    dimensions = build_stock_dimensions(stock_code, stock_name, foreign=foreign)
    return dimensions[: max(0, int(max_searches))]


def dimensions_for_group(
    dimensions: Sequence[StockSearchDimension],
    group_name: str,
) -> tuple[StockSearchDimension, ...]:
    return tuple(dimension for dimension in dimensions if dimension.group_name == group_name)


def build_stock_group_query(
    stock_code: str,
    stock_name: str,
    *,
    foreign: bool,
    group_name: str,
    dimensions: Sequence[StockSearchDimension],
) -> str:
    names = {dimension.name for dimension in dimensions}
    identity = " ".join(_unique((stock_name, stock_code)))
    if foreign:
        intents = {
            "latest_news": "latest news major events",
            "risk_check": "risk insider selling lawsuit litigation penalty",
            "announcements": "company announcements filings exchange SEC HKEX",
            "market_analysis": "analyst rating target price research report",
            "earnings": "earnings revenue profit guidance forecast",
            "industry": "industry competitors market share outlook",
        }
    else:
        intents = {
            "latest_news": "最新消息 重大事件",
            "risk_check": "减持 处罚 违规 诉讼 风险",
            "announcements": "公司公告 重要公告 交易所 cninfo",
            "market_analysis": "机构研报 评级 目标价 深度分析",
            "earnings": "业绩预告 财报 营收 净利润",
            "industry": "所在行业 竞争对手 市场份额 行业前景",
        }
    group_order = FRESH_DIMENSIONS if group_name == FRESH_GROUP else ANALYSIS_DIMENSIONS
    intent = " ".join(intents[name] for name in group_order if name in names)
    return " ".join(value for value in (identity, intent) if value).strip()


_ANNOUNCEMENT_TERMS = (
    "公告",
    "披露",
    "交易所",
    "上交所",
    "深交所",
    "港交所",
    "cninfo",
    "announcement",
    "filing",
    "sec form",
    "exchange notice",
)
_RISK_TERMS = (
    "减持",
    "处罚",
    "违规",
    "诉讼",
    "立案",
    "调查",
    "风险",
    "利空",
    "insider selling",
    "penalty",
    "lawsuit",
    "litigation",
    "investigation",
    "risk",
)
_EARNINGS_TERMS = (
    "业绩",
    "财报",
    "营收",
    "净利润",
    "盈利",
    "亏损",
    "earnings",
    "revenue",
    "profit",
    "results",
    "guidance",
)
_ANALYSIS_TERMS = (
    "研报",
    "评级",
    "目标价",
    "机构观点",
    "深度分析",
    "analyst",
    "rating",
    "target price",
    "research report",
    "outlook",
)
_INDUSTRY_TERMS = (
    "行业",
    "竞争对手",
    "市场份额",
    "产业链",
    "industry",
    "competitors",
    "market share",
    "sector outlook",
)


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def classify_stock_evidence(
    *,
    group_name: str,
    dimensions: Sequence[str],
    title: str,
    snippet: str,
) -> Optional[str]:
    """Assign one result to one enabled dimension, using deterministic precedence."""
    enabled = set(dimensions)
    text = " ".join((title or "", snippet or "")).strip()
    if not text:
        return None

    if group_name == FRESH_GROUP:
        if "announcements" in enabled and _contains_any(text, _ANNOUNCEMENT_TERMS):
            return "announcements"
        if "risk_check" in enabled and _contains_any(text, _RISK_TERMS):
            return "risk_check"
        return "latest_news" if "latest_news" in enabled else None

    if group_name == ANALYSIS_GROUP:
        if "earnings" in enabled and _contains_any(text, _EARNINGS_TERMS):
            return "earnings"
        if "industry" in enabled and _contains_any(text, _INDUSTRY_TERMS):
            return "industry"
        if "market_analysis" in enabled and _contains_any(text, _ANALYSIS_TERMS):
            return "market_analysis"
        if "market_analysis" in enabled:
            return "market_analysis"
        return "industry" if "industry" in enabled else None
    return None
