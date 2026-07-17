# -*- coding: utf-8 -*-
"""Deterministic ETF search profiles and fail-closed evidence classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from src.data.stock_index_loader import get_stock_index_metadata


ETF_PROFILE_TEMPLATE_VERSION = "etf-short-v1"
FRESH_EVENTS_DAYS = 3
ANALYSIS_DAYS = 30
GROUP_TOP_K = 18

ETF_DIMENSION_ORDER_CN = (
    "latest_news",
    "market_analysis",
    "risk_check",
    "announcements",
    "earnings",
    "industry",
)
ETF_DIMENSION_ORDER_FOREIGN = (
    "latest_news",
    "market_analysis",
    "risk_check",
    "earnings",
    "industry",
)

FRESH_DIMENSIONS = frozenset({"latest_news", "risk_check", "announcements"})
ANALYSIS_DIMENSIONS = frozenset({"market_analysis", "earnings", "industry"})

_GENERIC_NAME_TERMS = {
    "etf", "基金", "交易型开放式指数基金", "联接", "指数", "增强", "主题",
}
_CROSS_BORDER_TERMS = (
    "港股", "恒生", "纳指", "纳斯达克", "中概", "标普", "道琼斯", "日经",
    "德国", "法国", "美国", "海外", "qdii",
)
_COMMODITY_TERMS = ("黄金", "白银", "原油", "豆粕", "有色金属期货", "商品期货")
_BOND_TERMS = ("国债", "债券", "信用债", "政金债", "可转债", "城投债", "短债")
_STRATEGY_TERMS = ("红利", "低波", "价值", "成长", "质量", "高股息", "等权", "策略")
_BROAD_INDEX_TERMS = (
    "沪深300", "中证500", "中证1000", "中证2000", "上证50", "科创50",
    "创业板", "深证100", "a500", "全指", "宽基",
)

_CONTROLLED_ALIASES = {
    "纳指": ("纳斯达克100", "纳斯达克指数", "nasdaq 100", "nasdaq"),
    "中概互联网": ("中国互联网", "中证海外中国互联网50", "china internet"),
    "港股通创新药": ("港股创新药", "恒生港股通创新药", "香港创新药"),
    "黄金": ("伦敦金", "comex黄金", "现货黄金", "gold"),
    "人工智能": ("ai", "人工智能产业"),
    "半导体设备": ("半导体设备", "芯片设备"),
    "工业母机": ("机床", "工业母机"),
    "证券": ("券商", "证券行业"),
    "军工龙头": ("军工", "国防军工"),
    "酒": ("白酒", "酒类"),
    "通信": ("通信设备", "通信行业"),
}

_PRODUCT_NOTICE_TERMS = (
    "基金公告", "申购", "赎回", "暂停", "恢复", "分红", "最小申赎单位",
    "指数调整", "成分调整", "停牌", "复牌", "清盘", "终止上市",
)
_FLOW_SCALE_TERMS = (
    "基金份额", "份额增加", "份额减少", "份额变化", "基金规模", "规模变化",
    "净流入", "净流出", "资金流入", "资金流出",
)
_RISK_TERMS = (
    "溢价风险", "高溢价", "折价风险", "暂停申购", "暂停赎回", "限购",
    "qdii额度", "流动性风险", "清盘", "终止上市", "异常波动风险提示",
)
_CATALYST_TERMS = (
    "政策", "监管", "补贴", "涨价", "降价", "价格", "供需", "库存", "订单",
    "出口", "制裁", "关税", "汇率", "美元", "美联储", "利率", "实际利率",
    "央行", "地缘", "产量", "销量", "景气", "催化", "指数调整",
)
_CONSTITUENT_TERMS = (
    "核心成分", "成分股", "权重股", "龙头", "第一大权重", "持仓股",
)
_CONSTITUENT_EVENT_TERMS = (
    "业绩", "财报", "营收", "利润", "订单", "并购", "回购", "处罚", "诉讼",
)
_STRUCTURE_TERMS = (
    "估值", "市盈率", "市净率", "权重", "调仓", "成分", "行业配置", "景气",
    "机构观点", "研报", "拥挤度", "股息率", "久期", "信用利差",
)
_PLAIN_MARKET_RECAP_TERMS = (
    "今日涨幅", "今日跌幅", "上涨", "下跌", "成交额", "换手率", "最新净值",
    "盘中", "收盘价", "实时行情",
)
_MARKETING_TERMS = (
    "哪个好", "值得买", "怎么买", "推荐购买", "排名第一", "稳赚", "必买",
)


@dataclass(frozen=True)
class ETFSearchProfile:
    code: str
    kind: str
    full_name: str
    short_name: str
    product_terms: tuple[str, ...]
    underlying_terms: tuple[str, ...]
    underlying_driver_enabled: bool
    market_language: str

    @property
    def fingerprint(self) -> str:
        return "|".join(
            (
                self.kind,
                self.full_name,
                self.short_name,
                ",".join(self.underlying_terms),
                "driver" if self.underlying_driver_enabled else "no-driver",
            )
        )


@dataclass(frozen=True)
class ETFEvidenceDecision:
    category: str
    evidence_scope: str
    priority: int
    reason: str


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def _short_product_name(name: str) -> str:
    cleaned = re.sub(r"[（(].*?[）)]", "", str(name or "")).strip()
    match = re.search(r"(?i)etf", cleaned)
    if match:
        return cleaned[: match.end()].strip()
    return cleaned


def _deterministic_name_rule_terms(base_name: str) -> tuple[str, ...]:
    """Extract only controlled, unambiguous underlying terms from a product name."""
    normalized = str(base_name or "").strip()
    lowered = normalized.lower()
    matched: list[str] = []
    for term in (
        *_CROSS_BORDER_TERMS,
        *_COMMODITY_TERMS,
        *_BOND_TERMS,
        *_STRATEGY_TERMS,
        *_BROAD_INDEX_TERMS,
        *_CONTROLLED_ALIASES.keys(),
    ):
        if term.lower() in lowered:
            matched.append(term)
    return _unique(matched)


def _underlying_candidates(
    short_name: str,
    aliases: Sequence[str],
    *,
    metadata_verified: bool,
) -> tuple[str, ...]:
    candidates: list[str] = list(aliases)
    base = re.sub(r"(?i)etf.*$", "", short_name).strip(" -_/（）()")
    if base and metadata_verified and aliases:
        candidates.append(base)
    elif base:
        candidates.extend(_deterministic_name_rule_terms(base))

    expanded: list[str] = []
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if not normalized or normalized.lower() in _GENERIC_NAME_TERMS:
            continue
        if len(normalized) >= 2:
            expanded.append(normalized)
        for key, values in _CONTROLLED_ALIASES.items():
            if key.lower() in normalized.lower():
                expanded.extend(values)
    return _unique(expanded)


def _profile_kind(text: str, underlying_terms: Sequence[str]) -> str:
    haystack = " ".join((text, *underlying_terms)).lower()
    if any(term.lower() in haystack for term in _COMMODITY_TERMS):
        return "commodity"
    if any(term.lower() in haystack for term in _CROSS_BORDER_TERMS):
        return "cross_border"
    if any(term.lower() in haystack for term in _BOND_TERMS):
        return "bond"
    if any(term.lower() in haystack for term in _STRATEGY_TERMS):
        return "strategy"
    if any(term.lower() in haystack for term in _BROAD_INDEX_TERMS):
        return "broad_index"
    if underlying_terms:
        return "cn_sector_theme"
    return "generic_etf"


def resolve_etf_profile(stock_code: str, stock_name: str) -> ETFSearchProfile:
    """Build a conservative ETF profile from trusted metadata and name rules."""
    code = str(stock_code or "").strip()
    metadata = get_stock_index_metadata(code)
    full_name = (
        metadata.name
        if metadata is not None and metadata.asset_type == "etf"
        else str(stock_name or "").strip()
    )
    short_name = _short_product_name(full_name)
    metadata_verified = metadata is not None and metadata.asset_type == "etf"
    aliases = metadata.aliases if metadata_verified else ()
    underlying_terms = _underlying_candidates(
        short_name,
        aliases,
        metadata_verified=metadata_verified,
    )
    kind = _profile_kind(full_name, underlying_terms)

    code_terms = [code]
    if code.isdigit() and len(code) == 6:
        code_terms.append(f"{code}.SH" if code.startswith("5") else f"{code}.SZ")
    name_terms = [
        value
        for value in (full_name, short_name)
        if value and value.strip().lower() not in _GENERIC_NAME_TERMS
        and re.sub(r"(?i)etf|基金|指数", "", value).strip()
    ]
    product_terms = _unique((*code_terms, *name_terms))
    driver_enabled = kind != "generic_etf" and bool(underlying_terms)
    market_language = "zh-CN" if code.isdigit() else "en"
    return ETFSearchProfile(
        code=code,
        kind=kind,
        full_name=full_name,
        short_name=short_name,
        product_terms=product_terms,
        underlying_terms=underlying_terms if driver_enabled else (),
        underlying_driver_enabled=driver_enabled,
        market_language=market_language,
    )


def enabled_etf_dimensions(*, foreign: bool, max_searches: int) -> tuple[str, ...]:
    order = ETF_DIMENSION_ORDER_FOREIGN if foreign else ETF_DIMENSION_ORDER_CN
    return order[: max(0, int(max_searches))]


def group_dimensions(enabled_dimensions: Sequence[str], group_name: str) -> tuple[str, ...]:
    allowed = FRESH_DIMENSIONS if group_name == "fresh_events" else ANALYSIS_DIMENSIONS
    return tuple(value for value in enabled_dimensions if value in allowed)


def build_group_query(
    profile: ETFSearchProfile,
    *,
    group_name: str,
    dimensions: Sequence[str],
) -> str:
    """Build one bounded query containing separate product and underlying identities."""
    product_identity = " ".join(_unique((profile.code, profile.full_name, profile.short_name)))
    underlying_identity = " ".join(profile.underlying_terms[:6])
    if group_name == "fresh_events":
        intent = "基金公告 申购 赎回 份额 规模 风险 政策 供需 价格 核心成分"
    else:
        intent = "趋势驱动 核心成分 估值 景气 供需 机构观点 指数权重"
    if "risk_check" not in dimensions:
        intent = intent.replace(" 风险", "")
    if "announcements" not in dimensions:
        intent = intent.replace("基金公告 申购 赎回 ", "")
    if not profile.underlying_driver_enabled:
        underlying_identity = ""
        intent = "基金公告 申购 赎回 份额 规模 风险" if group_name == "fresh_events" else "基金结构 估值 指数权重"
    return " ".join(value for value in (product_identity, underlying_identity, intent) if value).strip()


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms if term)


def _contains_identity(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    for term in terms:
        candidate = term.strip().lower()
        if not candidate:
            continue
        if candidate.isdigit():
            if re.search(rf"(?<!\d){re.escape(candidate)}(?!\d)", lowered):
                return True
        elif re.fullmatch(r"[a-z0-9 ._-]+", candidate) and len(candidate) <= 3:
            if re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", lowered):
                return True
        elif candidate in lowered:
            return True
    return False


def classify_etf_evidence(
    *,
    profile: ETFSearchProfile,
    group_name: str,
    title: str,
    snippet: str,
    source: str,
    url: str,
) -> Optional[ETFEvidenceDecision]:
    """Admit and classify one result; uncertainty always returns ``None``."""
    text = " ".join((title or "", snippet or "", source or "", url or "")).strip()
    if not text or _contains_any(text, _MARKETING_TERMS):
        return None

    evidence_text = " ".join((title or "", snippet or "")).strip()
    product_hit = _contains_identity(evidence_text, profile.product_terms)
    underlying_hit = profile.underlying_driver_enabled and _contains_identity(
        evidence_text,
        profile.underlying_terms,
    )

    if _contains_any(text, _PLAIN_MARKET_RECAP_TERMS):
        substantive_terms = (
            *_PRODUCT_NOTICE_TERMS,
            *_FLOW_SCALE_TERMS,
            *_RISK_TERMS,
            *_CONSTITUENT_EVENT_TERMS,
            *_STRUCTURE_TERMS,
            *(term for term in _CATALYST_TERMS if term not in {"价格", "涨价", "降价"}),
        )
        if not _contains_any(text, substantive_terms):
            return None

    if product_hit and _contains_any(text, _RISK_TERMS):
        return ETFEvidenceDecision("risk_event", "product", 0, "产品身份命中且存在官方风险/交易限制")
    if product_hit and _contains_any(text, _PRODUCT_NOTICE_TERMS):
        return ETFEvidenceDecision("product_notice", "product", 1, "产品身份命中且存在公告/申赎动作")
    if product_hit and _contains_any(text, _FLOW_SCALE_TERMS):
        return ETFEvidenceDecision("flow_scale", "product", 4, "产品身份命中且存在份额/规模确认信号")

    if not underlying_hit:
        return None
    if group_name == "fresh_events":
        if not _contains_any(text, _CATALYST_TERMS):
            return None
        return ETFEvidenceDecision("underlying_driver", "underlying", 2, "命中已验证底层映射与近期催化")

    if _contains_any(text, _CONSTITUENT_TERMS) and _contains_any(text, _CONSTITUENT_EVENT_TERMS):
        return ETFEvidenceDecision("constituent_impact", "underlying", 3, "命中核心成分及其重大事件")
    if _contains_any(text, _STRUCTURE_TERMS):
        return ETFEvidenceDecision("structure_valuation", "underlying", 5, "命中指数结构/估值/景气证据")
    if _contains_any(text, (*_CATALYST_TERMS, "趋势", "展望", "周期")):
        return ETFEvidenceDecision("underlying_driver", "underlying", 2, "命中已验证底层映射与趋势驱动")
    return None


def target_dimension(category: str, enabled_dimensions: Sequence[str]) -> Optional[str]:
    enabled = set(enabled_dimensions)
    candidates = {
        "risk_event": ("risk_check", "latest_news"),
        "product_notice": ("announcements", "latest_news"),
        "flow_scale": ("latest_news",),
        "underlying_driver": ("latest_news", "market_analysis"),
        "constituent_impact": ("earnings", "market_analysis"),
        "structure_valuation": ("industry", "market_analysis"),
    }.get(category, ())
    return next((candidate for candidate in candidates if candidate in enabled), None)
