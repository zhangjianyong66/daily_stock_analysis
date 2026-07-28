"""结构化日线形态报告与策略推荐。

检测器复用 Agent 的日线形态实现；本模块只负责稳定的报告契约、状态和
确定性推荐，不调用模型，也不改变主分析结论。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from src.agent.tools.analysis_tools import detect_patterns_from_df
from src.services.history_loader import load_history_df

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "kline-pattern-v1"
WINDOW_DAYS = 60
MIN_DAYS = 10

AUTO_MATCH_REASON_CODES = {
    "calendar_unavailable",
    "history_unavailable",
    "insufficient_data",
    "invalid_daily_bars",
    "stale_daily_bars",
    "pattern_detection_failed",
    "no_reliable_pattern",
    "candidate_unavailable",
}

_PATTERN_ALIASES = {
    "十字星 (Doji)": "十字星",
    "锤子线 (Hammer)": "锤子线",
    "上吊线 (Hanging Man)": "上吊线",
    "流星线 (Shooting Star)": "流星线",
    "早晨之星 (Morning Star)": "早晨之星",
    "黄昏之星 (Evening Star)": "黄昏之星",
    "看涨吞没 (Bullish Engulfing)": "看涨吞没",
    "看跌吞没 (Bearish Engulfing)": "看跌吞没",
    "双底 (Double Bottom)": "双底",
}

_PATTERN_TRANSLATIONS = {
    "放量突破20日高点": {"en": "high-volume 20-day breakout", "ko": "거래량 동반 20일 고점 돌파"},
    "大阳线": {"en": "large bullish candle", "ko": "큰 양봉"},
    "大阴线": {"en": "large bearish candle", "ko": "큰 음봉"},
    "看跌吞没": {"en": "bearish engulfing", "ko": "하락 장악형"},
    "看涨吞没": {"en": "bullish engulfing", "ko": "상승 장악형"},
    "黄昏之星": {"en": "evening star", "ko": "석별형"},
    "早晨之星": {"en": "morning star", "ko": "샛별형"},
    "双底": {"en": "double bottom", "ko": "이중 바닥"},
    "锤子线": {"en": "hammer", "ko": "망치형"},
    "流星线": {"en": "shooting star", "ko": "유성형"},
    "上吊线": {"en": "hanging man", "ko": "매달린 사람형"},
    "箱体震荡": {"en": "box consolidation", "ko": "박스권 횡보"},
    "缩量回踩": {"en": "low-volume pullback", "ko": "거래량 감소 눌림목"},
    "一阳夹三阴": {"en": "one bullish candle with three bearish candles", "ko": "일양삼음"},
    "十字星": {"en": "doji", "ko": "십자형"},
}

@dataclass(frozen=True)
class RecommendationRule:
    skill_id: str
    patterns: tuple[str, ...]
    mode: str
    priority: int


# 报告推荐和自动执行必须共用此映射，顺序也是非风险候选的稳定优先级。
_RECOMMENDATION_RULES = (
    RecommendationRule("volume_breakout", ("放量突破20日高点", "大阳线"), "analysis", 10),
    RecommendationRule("one_yang_three_yin", ("一阳夹三阴",), "analysis", 20),
    RecommendationRule("shrink_pullback", ("缩量回踩",), "analysis", 30),
    RecommendationRule("bottom_volume", ("早晨之星", "看涨吞没", "双底", "锤子线"), "analysis", 40),
    RecommendationRule("box_oscillation", ("箱体震荡",), "analysis", 50),
    RecommendationRule(
        "emotion_cycle",
        ("黄昏之星", "看跌吞没", "流星线", "上吊线", "大阴线"),
        "risk_review",
        60,
    ),
)

_STRENGTH_RANK = {"强": 3, "中": 2, "弱": 1, "strong": 3, "medium": 2, "weak": 1}

_REASON_TEXT = {
    "analysis": {
        "zh": "识别到{patterns}，可用{skill}继续核对趋势、量能和风险边界。",
        "en": "Detected {patterns}; use {skill} to verify trend, volume, and risk boundaries.",
        "ko": "{patterns}이(가) 감지되었습니다. {skill}로 추세, 거래량과 위험 경계를 확인하세요.",
    },
    "risk_review": {
        "zh": "识别到{patterns}，建议使用{skill}做过热与风险复核，不构成进攻性买入建议。",
        "en": "Detected {patterns}; use {skill} for an overheating and risk review, not an aggressive buy signal.",
        "ko": "{patterns}이(가) 감지되었습니다. {skill}로 과열과 위험을 검토하며 공격적 매수 신호로 보지 않습니다.",
    },
}

_STATUS_TEXT = {
    "zh": {"ok": "形态识别完成", "insufficient_data": "日线数据不足", "unavailable": "形态数据暂不可用", "not_supported": "该市场暂不支持日线形态识别"},
    "en": {"ok": "Pattern scan completed", "insufficient_data": "Insufficient daily data", "unavailable": "Pattern data unavailable", "not_supported": "Daily pattern scanning is not supported for this market"},
    "ko": {"ok": "패턴 분석 완료", "insufficient_data": "일봉 데이터 부족", "unavailable": "패턴 데이터를 사용할 수 없음", "not_supported": "이 시장은 일봉 패턴 분석을 지원하지 않음"},
}

_NO_EVIDENCE_TEXT = {
    "zh": "证据不足",
    "en": "Insufficient evidence",
    "ko": "근거 부족",
}


def normalize_pattern_name(value: Any) -> str:
    text = str(value or "").strip()
    return _PATTERN_ALIASES.get(text, text)


def _localize_pattern_name(name: str, language: str) -> str:
    return _PATTERN_TRANSLATIONS.get(name, {}).get(language, name)


def _skill_value(skill: Any, key: str, default: Any = None) -> Any:
    if isinstance(skill, dict):
        return skill.get(key, default)
    return getattr(skill, key, default)


def _canonical_patterns(patterns: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name: dict[str, Dict[str, Any]] = {}
    for pattern in patterns or []:
        if not isinstance(pattern, dict):
            continue
        name = normalize_pattern_name(pattern.get("name", pattern.get("pattern")))
        if not name:
            continue
        item = {
            "name": name,
            "type": str(pattern.get("type") or "unknown"),
            "strength": str(pattern.get("strength") or "unknown"),
            "day_offset": int(pattern.get("day_offset") or 0),
            "description": str(pattern.get("description") or pattern.get("desc") or ""),
        }
        existing = by_name.get(name)
        if existing is None or (
            item["day_offset"],
            _STRENGTH_RANK.get(item["strength"], 0),
        ) > (
            existing["day_offset"],
            _STRENGTH_RANK.get(existing["strength"], 0),
        ):
            by_name[name] = item
    return list(by_name.values())


def build_pattern_candidates(
    patterns: Iterable[Dict[str, Any]],
    skill_catalog: Optional[Iterable[Any]] = None,
) -> List[Dict[str, Any]]:
    """从唯一规则表生成稳定候选；首项同时是自动执行 winner。"""
    catalog = {
        str(_skill_value(item, "name", _skill_value(item, "id", ""))).strip(): item
        for item in (skill_catalog or [])
        if str(_skill_value(item, "name", _skill_value(item, "id", ""))).strip()
        and bool(_skill_value(item, "user_invocable", True))
    }
    canonical = _canonical_patterns(patterns)
    candidates: List[Dict[str, Any]] = []
    for rule in _RECOMMENDATION_RULES:
        matched = [item for item in canonical if item["name"] in rule.patterns]
        if not matched or rule.skill_id not in catalog:
            continue
        strength = max((_STRENGTH_RANK.get(item["strength"], 0) for item in matched), default=0)
        latest_offset = max((item["day_offset"] for item in matched), default=-999)
        latest_strong_risk = bool(
            rule.mode == "risk_review"
            and any(
                item["day_offset"] == 0
                and _STRENGTH_RANK.get(item["strength"], 0) >= _STRENGTH_RANK["强"]
                for item in matched
            )
        )
        latest_strong = any(
            item["day_offset"] == 0
            and _STRENGTH_RANK.get(item["strength"], 0) >= _STRENGTH_RANK["强"]
            for item in matched
        )
        skill = catalog[rule.skill_id]
        candidates.append(
            {
                "skill_id": rule.skill_id,
                "display_name": str(
                    _skill_value(skill, "display_name", _skill_value(skill, "name", rule.skill_id))
                ),
                "matched_patterns": [item["name"] for item in matched],
                "mode": rule.mode,
                "strength_rank": strength,
                "day_offset": latest_offset,
                "rule_priority": rule.priority,
                "latest_strong_risk": latest_strong_risk,
                "latest_strong": latest_strong,
            }
        )
    candidates.sort(
        key=lambda item: (
            -int(item["latest_strong_risk"]),
            -int(item["latest_strong"]),
            int(item["rule_priority"]),
            -int(item["strength_rank"]),
            -int(item["day_offset"]),
            str(item["skill_id"]),
        )
    )
    return candidates


def recommend_pattern_strategies(
    patterns: Iterable[Dict[str, Any]],
    skill_catalog: Optional[Iterable[Any]] = None,
    *,
    language: str = "zh",
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """按固定映射推荐当前可调用策略，最多返回 ``limit`` 项。"""
    result: List[Dict[str, Any]] = []
    lang = language if language in {"zh", "en", "ko"} else "zh"
    for candidate in build_pattern_candidates(patterns, skill_catalog):
        skill_id = candidate["skill_id"]
        mode = candidate["mode"]
        skill_name = candidate["display_name"]
        matched = candidate["matched_patterns"]
        localized_matched = [_localize_pattern_name(name, lang) for name in matched]
        pattern_text = "、".join(localized_matched) if lang == "zh" else ", ".join(localized_matched)
        reason = _REASON_TEXT[mode][lang].format(patterns=pattern_text, skill=skill_name)
        result.append({
            "skill_id": skill_id,
            "display_name": skill_name,
            "matched_patterns": localized_matched,
            "reason": reason,
            "mode": mode,
        })
        if len(result) >= max(1, min(limit, 3)):
            break
    return result


def build_pattern_report(
    stock_code: str,
    *,
    language: str = "zh",
    skill_catalog: Optional[Iterable[Any]] = None,
    df: Any = None,
    source: str = "unknown",
    as_of: Optional[str] = None,
    detected: Optional[Dict[str, Any]] = None,
    reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    """生成一份可持久化的日线形态报告；异常只影响该附件。"""
    report_language = language if language in {"zh", "en", "ko"} else "zh"
    base = {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "period": "daily",
        "window_days": WINDOW_DAYS,
        "source": source or "unknown",
        "as_of": as_of,
        "current_price": None,
        "patterns": [],
        "summary": _STATUS_TEXT[report_language]["unavailable"],
        "recommendations": [],
    }
    if reason_code in AUTO_MATCH_REASON_CODES:
        base["reason_code"] = reason_code
    try:
        if df is None:
            df, source = load_history_df(stock_code, days=WINDOW_DAYS)
            base["source"] = source or "unknown"
        if df is None or df.empty:
            base["status"] = "unavailable"
            return base
        if len(df) < MIN_DAYS:
            base["status"] = "insufficient_data"
            base["summary"] = _STATUS_TEXT[report_language]["insufficient_data"]
            return base
        if detected is None:
            detected = detect_patterns_from_df(df, stock_code, source=base["source"], days=WINDOW_DAYS)
        if "error" in detected:
            base["status"] = "insufficient_data" if "Insufficient" in str(detected["error"]) else "unavailable"
            base["summary"] = _STATUS_TEXT[report_language][base["status"]]
            return base
        patterns = []
        for item in detected.get("patterns", []):
            patterns.append({
                "name": normalize_pattern_name(item.get("pattern")),
                "type": item.get("type", "unknown"),
                "strength": item.get("strength", "unknown"),
                "day_offset": item.get("day_offset", 0),
                "description": item.get("description") or item.get("desc") or "",
            })
        recommendations = recommend_pattern_strategies(patterns, skill_catalog, language=report_language)
        localized_patterns = [
            {**item, "name": _localize_pattern_name(item["name"], report_language)}
            for item in patterns
        ]
        base.update({
            "status": "ok",
            "current_price": detected.get("current_price"),
            "patterns": localized_patterns,
            "summary": (
                _STATUS_TEXT[report_language]["ok"]
                + (
                    ": "
                    + ("、".join(p["name"] for p in localized_patterns) if report_language == "zh" else ", ".join(p["name"] for p in localized_patterns))
                    if localized_patterns
                    else f"{'；' if report_language == 'zh' else ': '}{_NO_EVIDENCE_TEXT[report_language]}"
                )
            ),
            "recommendations": recommendations,
        })
        if as_of is None:
            try:
                if "date" in df.columns and len(df["date"]):
                    candidate = df["date"].iloc[-1]
                    base["as_of"] = candidate.date().isoformat() if hasattr(candidate, "date") else str(candidate)[:10]
                    return base
                last = df.index[-1]
                base["as_of"] = last.date().isoformat() if hasattr(last, "date") else str(last)[:10]
            except Exception:
                base["as_of"] = None
        return base
    except Exception as exc:
        logger.warning("构建 %s 形态报告失败: %s", stock_code, exc, exc_info=True)
        return base


@dataclass(frozen=True)
class PatternMatchResolution:
    """一次完整日线识别产物，供策略选择和报告附件共同复用。"""

    pattern_report: Dict[str, Any]
    candidates: tuple[Dict[str, Any], ...]
    winner: Optional[Dict[str, Any]]
    reason_code: Optional[str]
    matched_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutoStrategyResolution:
    """单只股票、单次任务的不可变策略运行状态。"""

    mode: str
    skills: tuple[str, ...]
    prompt_state: Any
    pattern_report: Optional[Dict[str, Any]]
    selection_context: Optional[Dict[str, Any]]


def _coerce_target_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _prepare_complete_daily_bars(df: Any, target_date: date) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None, "history_unavailable"
    frame = df.copy()
    required = ("open", "high", "low", "close")
    if any(column not in frame.columns for column in required):
        return None, "invalid_daily_bars"

    if "date" in frame.columns:
        dates = pd.to_datetime(frame["date"], errors="coerce")
    else:
        dates = pd.to_datetime(frame.index, errors="coerce")
    if dates.isna().any():
        return None, "invalid_daily_bars"
    frame["__bar_date"] = pd.Series(dates, index=frame.index).dt.date
    frame = frame[frame["__bar_date"] <= target_date]
    if frame.empty:
        return None, "history_unavailable"
    frame = frame.sort_values("__bar_date").drop_duplicates("__bar_date", keep="last")

    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    numeric = frame[list(required)].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        return None, "invalid_daily_bars"
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        return None, "invalid_daily_bars"
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        return None, "invalid_daily_bars"
    if frame["__bar_date"].iloc[-1] != target_date:
        return None, "stale_daily_bars"
    if len(frame) < MIN_DAYS:
        return None, "insufficient_data"
    return frame.tail(WINDOW_DAYS).drop(columns=["__bar_date"]), None


def build_runtime_pattern_match(
    stock_code: str,
    *,
    target_date: Any,
    language: str = "zh",
    skill_catalog: Optional[Iterable[Any]] = None,
    df: Any = None,
    source: str = "unknown",
) -> PatternMatchResolution:
    """校验最近完整日线并只识别一次，返回可持久化报告和唯一 winner。"""
    resolved_target = _coerce_target_date(target_date)
    if resolved_target is None:
        report = build_pattern_report(
            stock_code,
            language=language,
            skill_catalog=skill_catalog,
            df=pd.DataFrame(),
            source=source,
            reason_code="calendar_unavailable",
        )
        return PatternMatchResolution(report, (), None, "calendar_unavailable")
    try:
        if df is None:
            df, source = load_history_df(
                stock_code,
                days=WINDOW_DAYS,
                target_date=resolved_target,
                minimum_records=MIN_DAYS,
            )
        prepared, reason_code = _prepare_complete_daily_bars(df, resolved_target)
        if reason_code:
            status = "insufficient_data" if reason_code == "insufficient_data" else "unavailable"
            report = build_pattern_report(
                stock_code,
                language=language,
                skill_catalog=skill_catalog,
                df=pd.DataFrame() if prepared is None else prepared,
                source=source,
                as_of=resolved_target.isoformat(),
                reason_code=reason_code,
            )
            report["status"] = status
            report["summary"] = _STATUS_TEXT[language if language in _STATUS_TEXT else "zh"][status]
            return PatternMatchResolution(report, (), None, reason_code)

        detected = detect_patterns_from_df(prepared, stock_code, source=source, days=WINDOW_DAYS)
        if "error" in detected:
            report = build_pattern_report(
                stock_code,
                language=language,
                skill_catalog=skill_catalog,
                df=prepared,
                source=source,
                as_of=resolved_target.isoformat(),
                detected=detected,
                reason_code="pattern_detection_failed",
            )
            return PatternMatchResolution(report, (), None, "pattern_detection_failed")
        raw_patterns = _canonical_patterns(detected.get("patterns", []))
        candidates = build_pattern_candidates(raw_patterns, skill_catalog)
        mapped_patterns = {
            pattern_name
            for rule in _RECOMMENDATION_RULES
            for pattern_name in rule.patterns
        }
        has_mapped_pattern = any(item["name"] in mapped_patterns for item in raw_patterns)
        reason_code = None if candidates else ("candidate_unavailable" if has_mapped_pattern else "no_reliable_pattern")
        report = build_pattern_report(
            stock_code,
            language=language,
            skill_catalog=skill_catalog,
            df=prepared,
            source=source,
            as_of=resolved_target.isoformat(),
            detected=detected,
            reason_code=reason_code,
        )
        frozen_candidates = tuple(dict(candidate) for candidate in candidates)
        return PatternMatchResolution(
            pattern_report=report,
            candidates=frozen_candidates,
            winner=dict(frozen_candidates[0]) if frozen_candidates else None,
            reason_code=reason_code,
            matched_patterns=tuple(item["name"] for item in raw_patterns),
        )
    except Exception as exc:
        logger.warning("构建 %s 自动策略匹配失败: %s", stock_code, exc, exc_info=True)
        report = build_pattern_report(
            stock_code,
            language=language,
            skill_catalog=skill_catalog,
            df=pd.DataFrame(),
            source=source,
            as_of=resolved_target.isoformat(),
            reason_code="pattern_detection_failed",
        )
        return PatternMatchResolution(report, (), None, "pattern_detection_failed")


class KlinePatternService:
    """面向流水线的薄封装，便于测试和替换数据源。"""

    def build_report(self, stock_code: str, *, language: str = "zh", skill_catalog: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
        return build_pattern_report(stock_code, language=language, skill_catalog=skill_catalog)

    def build_runtime_match(
        self,
        stock_code: str,
        *,
        target_date: Any,
        language: str = "zh",
        skill_catalog: Optional[Iterable[Any]] = None,
    ) -> PatternMatchResolution:
        return build_runtime_pattern_match(
            stock_code,
            target_date=target_date,
            language=language,
            skill_catalog=skill_catalog,
        )
