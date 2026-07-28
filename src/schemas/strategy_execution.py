"""Strategy execution snapshots shared by analysis, history and reports.

The snapshot is deliberately a small JSON-compatible mapping.  It records the
server-side decision that was actually executed, so consumers never need to
infer historical strategy identity from current configuration or LLM text.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from src.report_language import localize_strategy_skill, normalize_report_language

STRATEGY_EXECUTION_SCHEMA_VERSION = 1
VALID_STRATEGY_EXECUTION_STATUSES = {"normal", "partial", "fallback", "degraded", "unrecorded"}
VALID_STRATEGY_EXECUTION_SOURCES = {"request", "default", "config", "auto", "fallback", "unknown"}
VALID_STRATEGY_ITEM_STATUSES = {"selected", "degraded", "not_executed"}
VALID_SELECTION_CONTEXT_STATUSES = {"matched", "fallback"}
VALID_SELECTION_CONTEXT_MODES = {"auto_match"}
VALID_AUTO_MATCH_REASONS = {
    "calendar_unavailable",
    "history_unavailable",
    "insufficient_data",
    "invalid_daily_bars",
    "stale_daily_bars",
    "pattern_detection_failed",
    "no_reliable_pattern",
    "candidate_unavailable",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _strategy_item(value: Any, *, default_status: str = "selected") -> Optional[dict[str, str]]:
    if isinstance(value, str):
        skill_id = value.strip()
        display_name = skill_id
        status = default_status
    elif isinstance(value, Mapping):
        skill_id = _clean_text(value.get("id") or value.get("skill_id") or value.get("name"))
        display_name = _clean_text(value.get("display_name") or value.get("displayName") or value.get("name"))
        status = _clean_text(value.get("status")) or default_status
    else:
        return None
    if not skill_id:
        return None
    if not display_name:
        display_name = skill_id
    if status not in VALID_STRATEGY_ITEM_STATUSES:
        status = default_status if default_status in VALID_STRATEGY_ITEM_STATUSES else "selected"
    return {"id": skill_id, "display_name": display_name, "status": status}


def _strategy_items(values: Any, *, default_status: str = "selected") -> list[dict[str, str]]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, Mapping)):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        item = _strategy_item(value, default_status=default_status)
        if item and item["id"] not in seen:
            result.append(item)
            seen.add(item["id"])
    return result


def _clean_text_list(values: Any) -> list[str]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, Mapping)):
        return []
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in result:
            result.append(text)
    return result


def normalize_selection_context(value: Any) -> Optional[dict[str, Any]]:
    """Normalize optional auto-match context without invalidating legacy snapshots."""
    if not isinstance(value, Mapping):
        return None
    mode = _clean_text(value.get("mode"))
    status = _clean_text(value.get("status"))
    if mode not in VALID_SELECTION_CONTEXT_MODES or status not in VALID_SELECTION_CONTEXT_STATUSES:
        return None
    as_of = _clean_text(value.get("as_of"))
    fallback_reason = _clean_text(value.get("fallback_reason"))
    if fallback_reason and fallback_reason not in VALID_AUTO_MATCH_REASONS:
        return None
    if status == "matched" and fallback_reason:
        return None
    candidates: list[dict[str, Any]] = []
    raw_candidates = value.get("candidates")
    if isinstance(raw_candidates, Iterable) and not isinstance(raw_candidates, (str, bytes, Mapping)):
        for candidate in raw_candidates:
            if not isinstance(candidate, Mapping):
                continue
            skill_id = _clean_text(candidate.get("skill_id") or candidate.get("id"))
            candidate_mode = _clean_text(candidate.get("mode"))
            if not skill_id or candidate_mode not in {"analysis", "risk_review"}:
                continue
            candidates.append(
                {
                    "skill_id": skill_id,
                    "mode": candidate_mode,
                    "matched_patterns": _clean_text_list(candidate.get("matched_patterns")),
                }
            )
    context: dict[str, Any] = {
        "mode": mode,
        "status": status,
        "as_of": as_of or None,
        "matched_patterns": _clean_text_list(value.get("matched_patterns")),
        "candidates": candidates,
        "selected_skill_id": _clean_text(value.get("selected_skill_id")) or None,
        "fallback_reason": fallback_reason or None,
    }
    return context


def build_strategy_execution_snapshot(
    *,
    requested: Any = None,
    effective: Any = None,
    source: str = "unknown",
    status: str = "normal",
    rejected: Any = None,
    message: Optional[str] = None,
    selection_context: Any = None,
) -> dict[str, Any]:
    """Build a normalized, JSON-safe execution snapshot."""
    normalized_source = _clean_text(source)
    if normalized_source not in VALID_STRATEGY_EXECUTION_SOURCES:
        normalized_source = "unknown"
    normalized_status = _clean_text(status)
    if normalized_status not in VALID_STRATEGY_EXECUTION_STATUSES:
        normalized_status = "unrecorded"

    requested_items = _strategy_items(requested)
    effective_items = _strategy_items(effective)
    rejected_items: list[dict[str, str]] = []
    if isinstance(rejected, Iterable) and not isinstance(rejected, (str, bytes, Mapping)):
        for value in rejected:
            if isinstance(value, str):
                skill_id = value.strip()
                reason = "unavailable"
            elif isinstance(value, Mapping):
                skill_id = _clean_text(value.get("id") or value.get("skill_id") or value.get("name"))
                reason = _clean_text(value.get("reason")) or "unavailable"
            else:
                continue
            if skill_id and not any(item["id"] == skill_id for item in rejected_items):
                rejected_items.append({"id": skill_id, "reason": reason})

    snapshot: dict[str, Any] = {
        "schema_version": STRATEGY_EXECUTION_SCHEMA_VERSION,
        "status": normalized_status,
        "source": normalized_source,
        "requested": requested_items,
        "effective": effective_items,
        "rejected": rejected_items,
    }
    cleaned_message = _clean_text(message)
    if cleaned_message:
        snapshot["message"] = cleaned_message
    normalized_context = normalize_selection_context(selection_context)
    if normalized_context is not None:
        snapshot["selection_context"] = normalized_context
    return snapshot


def normalize_strategy_execution(value: Any) -> Optional[dict[str, Any]]:
    """Normalize a persisted snapshot; malformed legacy data returns ``None``."""
    if not isinstance(value, Mapping):
        return None
    try:
        schema_version = int(value.get("schema_version"))
    except (TypeError, ValueError, OverflowError):
        return None
    if schema_version != STRATEGY_EXECUTION_SCHEMA_VERSION:
        return None
    if value.get("status") not in VALID_STRATEGY_EXECUTION_STATUSES:
        return None
    if value.get("source") not in VALID_STRATEGY_EXECUTION_SOURCES:
        return None
    effective = _strategy_items(value.get("effective"))
    requested = _strategy_items(value.get("requested"))
    rejected = value.get("rejected")
    snapshot = build_strategy_execution_snapshot(
        requested=requested,
        effective=effective,
        source=value.get("source", "unknown"),
        status=value.get("status", "unrecorded"),
        rejected=rejected,
        message=value.get("message"),
        selection_context=value.get("selection_context"),
    )
    if not effective and snapshot["status"] not in {"unrecorded", "fallback", "degraded"}:
        return None
    return snapshot


def strategy_execution_display_name(item: Mapping[str, Any], language: str = "zh") -> str:
    """Localize built-ins and fall back to the persisted custom-strategy name."""
    skill_id = _clean_text(item.get("id"))
    localized = localize_strategy_skill(skill_id, language)
    if localized and localized != skill_id:
        return localized
    name = _clean_text(item.get("display_name") or item.get("name"))
    if name:
        return name
    return skill_id or ("未命名策略" if normalize_report_language(language) == "zh" else "Unnamed strategy")


def localize_strategy_execution(value: Any, language: str = "zh") -> Optional[dict[str, Any]]:
    """Return a normalized snapshot with localized built-in display names."""
    snapshot = normalize_strategy_execution(value)
    if snapshot is None:
        return None
    localized = dict(snapshot)
    for key in ("requested", "effective"):
        localized[key] = [
            {**item, "display_name": strategy_execution_display_name(item, language)}
            for item in snapshot.get(key) or []
        ]
    status = snapshot.get("status")
    labels = strategy_execution_labels(language)
    if status in {"fallback", "partial", "degraded"}:
        localized["message"] = labels[f"{status}_message"]
    context = snapshot.get("selection_context")
    if context:
        localized_context = dict(context)
        localized_context["matched_patterns"] = [
            _localize_selection_pattern(name, language)
            for name in context.get("matched_patterns") or []
        ]
        localized_context["candidates"] = [
            {
                **candidate,
                "matched_patterns": [
                    _localize_selection_pattern(name, language)
                    for name in candidate.get("matched_patterns") or []
                ],
            }
            for candidate in context.get("candidates") or []
        ]
        localized_context["fallback_reason_label"] = labels.get(
            f"auto_reason_{context.get('fallback_reason')}",
            context.get("fallback_reason"),
        )
        localized["selection_context"] = localized_context
    return localized


def _localize_selection_pattern(name: str, language: str) -> str:
    from src.services.kline_pattern_service import _localize_pattern_name

    return _localize_pattern_name(name, normalize_report_language(language))


def strategy_execution_labels(language: str = "zh") -> dict[str, str]:
    lang = normalize_report_language(language)
    if lang == "en":
        return {
            "strategy": "Strategy",
            "source": "Source",
            "request": "Selected this time",
            "default": "System default",
            "config": "Fixed configuration",
            "auto": "Auto routing",
            "fallback": "System fallback",
            "unknown": "Not recorded",
            "normal": "",
            "partial": "Partial execution",
            "degraded": "Execution degraded",
            "unrecorded": "Strategy not recorded",
            "fallback_message": "The requested strategy was unavailable; the system used the final strategy below.",
            "partial_message": "Some requested strategies were unavailable and were not executed.",
            "degraded_message": "A selected strategy failed or timed out; no replacement strategy was claimed.",
            "unrecorded_message": "This report was created before strategy metadata was saved.",
            "auto_match": "Auto match",
            "auto_as_of": "Complete daily bars through",
            "auto_basis": "Matched patterns",
            "auto_reason_calendar_unavailable": "The trading calendar was unavailable",
            "auto_reason_history_unavailable": "Daily bars were unavailable",
            "auto_reason_insufficient_data": "Fewer than 10 complete daily bars were available",
            "auto_reason_invalid_daily_bars": "Daily bar fields were incomplete or invalid",
            "auto_reason_stale_daily_bars": "Daily bars did not reach the latest completed session",
            "auto_reason_pattern_detection_failed": "Pattern detection failed",
            "auto_reason_no_reliable_pattern": "No reliable mapped pattern was found",
            "auto_reason_candidate_unavailable": "Matched strategy was unavailable",
        }
    if lang == "ko":
        return {
            "strategy": "분석 전략",
            "source": "출처",
            "request": "이번에 지정",
            "default": "시스템 기본값",
            "config": "고정 설정",
            "auto": "자동 라우팅",
            "fallback": "시스템 대체",
            "unknown": "기록되지 않음",
            "normal": "",
            "partial": "일부 실행",
            "degraded": "실행 저하",
            "unrecorded": "전략 미기록",
            "fallback_message": "요청한 전략을 사용할 수 없어 아래 최종 전략을 적용했습니다.",
            "partial_message": "요청한 전략 중 일부를 사용할 수 없어 실행하지 않았습니다.",
            "degraded_message": "선택한 전략이 실패하거나 시간 초과되어 다른 전략으로 대체하지 않았습니다.",
            "unrecorded_message": "이 보고서 생성 당시 전략 정보가 저장되지 않았습니다.",
            "auto_match": "자동 매칭",
            "auto_as_of": "완료 일봉 기준일",
            "auto_basis": "매칭 근거",
            "auto_reason_calendar_unavailable": "거래일 달력을 사용할 수 없음",
            "auto_reason_history_unavailable": "일봉 데이터를 사용할 수 없음",
            "auto_reason_insufficient_data": "완료 일봉이 10개 미만임",
            "auto_reason_invalid_daily_bars": "일봉 필드가 불완전하거나 유효하지 않음",
            "auto_reason_stale_daily_bars": "일봉이 최근 완료 거래일까지 도달하지 않음",
            "auto_reason_pattern_detection_failed": "패턴 감지 실패",
            "auto_reason_no_reliable_pattern": "신뢰할 수 있는 매핑 패턴 없음",
            "auto_reason_candidate_unavailable": "매칭된 전략을 사용할 수 없음",
        }
    return {
        "strategy": "分析策略",
        "source": "来源",
        "request": "本次指定",
        "default": "系统默认",
        "config": "固定配置",
        "auto": "自动路由",
        "fallback": "系统回退",
        "unknown": "未记录",
        "normal": "",
        "partial": "部分执行",
        "degraded": "执行降级",
        "unrecorded": "策略未记录",
        "fallback_message": "请求的策略不可用，系统已改用以下最终策略。",
        "partial_message": "部分请求策略不可用，系统仅执行了可用策略。",
        "degraded_message": "已选择的策略执行失败或超时，系统未伪装为切换到其他策略。",
        "unrecorded_message": "该报告生成时未保存策略信息。",
        "auto_match": "自动匹配",
        "auto_as_of": "完整日线截止",
        "auto_basis": "匹配依据",
        "auto_reason_calendar_unavailable": "交易日历不可用",
        "auto_reason_history_unavailable": "日线数据不可用",
        "auto_reason_insufficient_data": "完整日线少于 10 根",
        "auto_reason_invalid_daily_bars": "日线字段不完整或无效",
        "auto_reason_stale_daily_bars": "日线未更新到最近完整交易日",
        "auto_reason_pattern_detection_failed": "形态识别失败",
        "auto_reason_no_reliable_pattern": "未识别到可靠的映射形态",
        "auto_reason_candidate_unavailable": "命中策略当前不可调用",
    }


def format_strategy_execution_text(value: Any, language: str = "zh") -> Optional[str]:
    """Format the snapshot for Markdown/notification output."""
    snapshot = normalize_strategy_execution(value)
    labels = strategy_execution_labels(language)
    if snapshot is None:
        return f"{labels['strategy']}：{labels['unrecorded']}（{labels['unrecorded_message']}）"
    if snapshot["status"] == "unrecorded":
        return f"{labels['strategy']}：{labels['unrecorded']}（{labels['unrecorded_message']}）"

    effective = snapshot.get("effective") or []
    names = [strategy_execution_display_name(item, language) for item in effective]
    if not names:
        names = [labels["unknown"]]
    source_label = (
        labels["auto_match"]
        if snapshot.get("selection_context")
        else labels.get(snapshot.get("source", "unknown"), labels["unknown"])
    )
    status_label = labels.get(snapshot.get("status", "normal"), "")
    suffix = f" · {status_label}" if status_label else ""
    text = f"{labels['strategy']}：{'、'.join(names)} · {labels['source']}：{source_label}{suffix}"
    if snapshot.get("status") in {"fallback", "partial", "degraded"}:
        message_key = f"{snapshot['status']}_message"
        text += f"（{labels[message_key]}）"
    context = snapshot.get("selection_context")
    if context:
        details: list[str] = [labels["auto_match"]]
        if context.get("as_of"):
            details.append(f"{labels['auto_as_of']} {context['as_of']}")
        patterns = [
            _localize_selection_pattern(name, language)
            for name in context.get("matched_patterns") or []
        ]
        if patterns:
            details.append(f"{labels['auto_basis']} {'、'.join(patterns)}")
        reason = context.get("fallback_reason")
        if reason:
            details.append(labels.get(f"auto_reason_{reason}", reason))
        text += f" · {' · '.join(details)}"
    return text
