"""结构化日线形态报告与策略推荐。

检测器复用 Agent 的日线形态实现；本模块只负责稳定的报告契约、状态和
确定性推荐，不调用模型，也不改变主分析结论。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from src.agent.tools.analysis_tools import detect_patterns_from_df
from src.services.history_loader import load_history_df

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "kline-pattern-v1"
WINDOW_DAYS = 60
MIN_DAYS = 10

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

_RECOMMENDATION_RULES = (
    ("volume_breakout", ("放量突破20日高点", "大阳线"), "analysis"),
    ("bull_trend", ("放量突破20日高点", "大阳线"), "analysis"),
    ("one_yang_three_yin", ("一阳夹三阴",), "analysis"),
    ("shrink_pullback", ("缩量回踩",), "analysis"),
    ("bottom_volume", ("早晨之星", "看涨吞没", "双底", "锤子线"), "analysis"),
    ("ma_golden_cross", ("早晨之星", "看涨吞没", "双底", "锤子线"), "analysis"),
    ("box_oscillation", ("箱体震荡",), "analysis"),
    ("emotion_cycle", ("黄昏之星", "看跌吞没", "流星线", "上吊线", "大阴线"), "risk_review"),
)

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


def recommend_pattern_strategies(
    patterns: Iterable[Dict[str, Any]],
    skill_catalog: Optional[Iterable[Any]] = None,
    *,
    language: str = "zh",
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """按固定映射推荐当前可调用策略，最多返回 ``limit`` 项。"""
    catalog = {
        str(_skill_value(item, "name", _skill_value(item, "id", ""))).strip(): item
        for item in (skill_catalog or [])
        if str(_skill_value(item, "name", _skill_value(item, "id", ""))).strip()
        and bool(_skill_value(item, "user_invocable", True))
    }
    normalized_patterns = []
    for pattern in patterns or []:
        if not isinstance(pattern, dict):
            continue
        name = normalize_pattern_name(pattern.get("name", pattern.get("pattern")))
        if name and name not in normalized_patterns:
            normalized_patterns.append(name)

    result: List[Dict[str, Any]] = []
    seen = set()
    lang = language if language in {"zh", "en", "ko"} else "zh"
    for skill_id, matches, mode in _RECOMMENDATION_RULES:
        if skill_id not in catalog or skill_id in seen:
            continue
        matched = [name for name in normalized_patterns if name in matches]
        if not matched:
            continue
        skill_name = str(_skill_value(catalog[skill_id], "display_name", _skill_value(catalog[skill_id], "name", skill_id)))
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
        seen.add(skill_id)
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


class KlinePatternService:
    """面向流水线的薄封装，便于测试和替换数据源。"""

    def build_report(self, stock_code: str, *, language: str = "zh", skill_catalog: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
        return build_pattern_report(stock_code, language=language, skill_catalog=skill_catalog)
