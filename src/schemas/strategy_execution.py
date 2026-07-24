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


def build_strategy_execution_snapshot(
    *,
    requested: Any = None,
    effective: Any = None,
    source: str = "unknown",
    status: str = "normal",
    rejected: Any = None,
    message: Optional[str] = None,
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
    return localized


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
    source_label = labels.get(snapshot.get("source", "unknown"), labels["unknown"])
    status_label = labels.get(snapshot.get("status", "normal"), "")
    suffix = f" · {status_label}" if status_label else ""
    text = f"{labels['strategy']}：{'、'.join(names)} · {labels['source']}：{source_label}{suffix}"
    if snapshot.get("status") in {"fallback", "partial", "degraded"}:
        message_key = f"{snapshot['status']}_message"
        text += f"（{labels[message_key]}）"
    return text
