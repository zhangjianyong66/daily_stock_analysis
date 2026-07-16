# -*- coding: utf-8 -*-
"""LLM usage tracking endpoint."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse

from api.deps import get_database_manager, require_enabled_admin_session
from api.v1.errors import api_error
from api.v1.schemas.usage import (
    SearchFaultStatusResponse,
    SearchUsageCallDetail,
    SearchUsageDashboardResponse,
    UsageDashboardResponse,
    UsageSummaryResponse,
)
from src.services.search_usage_service import SearchUsageService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))  # Beijing time (UTC+8)

router = APIRouter()

_VALID_PERIODS = {"today", "month", "all"}
_SEARCH_VALID_PERIODS = {"today", "7d", "month", "all", "custom"}


def _date_range(period: str):
    """Return (from_dt, to_dt) as naive datetimes in Beijing time (UTC+8)."""
    now = datetime.now(tz=_CST).replace(tzinfo=None)  # naive, Beijing local
    if period == "today":
        from_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        from_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # all
        from_dt = datetime(2000, 1, 1)
    return from_dt, now


def _normalize_period(period: str) -> str:
    return period if period in _VALID_PERIODS else "month"


def _search_date_range(period: str, from_time: Optional[str], to_time: Optional[str]) -> tuple[datetime, datetime]:
    normalized = period if period in _SEARCH_VALID_PERIODS else "month"
    now_cst = datetime.now(tz=_CST)
    if normalized == "custom":
        if not from_time or not to_time:
            raise api_error(400, "validation_error", "自定义时间范围必须同时提供 from_time 和 to_time")
        try:
            start = datetime.fromisoformat(from_time)
            end = datetime.fromisoformat(to_time)
        except ValueError as exc:
            raise api_error(400, "validation_error", "时间格式无效，请使用 ISO 8601") from exc
        start = start.replace(tzinfo=_CST) if start.tzinfo is None else start.astimezone(_CST)
        end = end.replace(tzinfo=_CST) if end.tzinfo is None else end.astimezone(_CST)
    elif normalized == "today":
        start = now_cst.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now_cst
    elif normalized == "7d":
        start = now_cst - timedelta(days=7)
        end = now_cst
    elif normalized == "month":
        start = now_cst.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now_cst
    else:
        start = datetime(2000, 1, 1, tzinfo=_CST)
        end = now_cst
    if start > end:
        raise api_error(400, "validation_error", "开始时间不能晚于结束时间")
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _search_filters(
    *,
    period: str,
    from_time: Optional[str],
    to_time: Optional[str],
    provider: Optional[str],
    source: Optional[str],
    success: Optional[bool],
    error_category: Optional[str],
    key_fingerprint: Optional[str],
) -> dict[str, Any]:
    from_dt, to_dt = _search_date_range(period, from_time, to_time)
    return {
        "from_dt": from_dt,
        "to_dt": to_dt,
        "provider": provider,
        "call_source": source,
        "success": success,
        "error_category": error_category,
        "key_fingerprint": key_fingerprint,
    }


def _enrich_call_record(row: dict[str, Any]) -> dict[str, Any]:
    called_at = row.get("called_at")
    if isinstance(called_at, datetime):
        called_at_value = called_at.isoformat()
    else:
        called_at_value = str(called_at or "")
    return {
        **row,
        "called_at": called_at_value,
    }


def _build_summary_payload(period: str, from_dt: datetime, to_dt: datetime, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": period,
        "from_date": from_dt.date().isoformat(),
        "to_date": to_dt.date().isoformat(),
        "total_calls": data.get("total_calls", 0),
        "total_prompt_tokens": data.get("total_prompt_tokens", 0),
        "total_completion_tokens": data.get("total_completion_tokens", 0),
        "total_tokens": data.get("total_tokens", 0),
        "by_call_type": data.get("by_call_type", []),
        "by_model": data.get("by_model", []),
    }


@router.get(
    "/summary",
    response_model=UsageSummaryResponse,
    summary="LLM token usage summary",
    description="Aggregate token consumption by period, call type, and model.",
)
def get_usage_summary(
    period: str = Query("month", description="'today' | 'month' | 'all'"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> UsageSummaryResponse:
    normalized_period = _normalize_period(period)
    from_dt, to_dt = _date_range(normalized_period)
    data = db_manager.get_llm_usage_summary(from_dt, to_dt)
    return UsageSummaryResponse(**_build_summary_payload(normalized_period, from_dt, to_dt, data))


@router.get(
    "/dashboard",
    response_model=UsageDashboardResponse,
    summary="LLM token usage monitoring dashboard",
    description="Return token totals, model breakdowns, and recent LLM call records.",
)
def get_usage_dashboard(
    period: str = Query("month", description="'today' | 'month' | 'all'"),
    limit: int = Query(50, ge=1, le=200, description="Recent call records to include"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> UsageDashboardResponse:
    normalized_period = _normalize_period(period)
    from_dt, to_dt = _date_range(normalized_period)
    data = db_manager.get_llm_usage_summary(from_dt, to_dt)
    records = db_manager.get_llm_usage_records(from_dt, to_dt, limit=limit)
    payload = _build_summary_payload(normalized_period, from_dt, to_dt, data)
    payload["recent_calls"] = [_enrich_call_record(row) for row in records]
    return UsageDashboardResponse(**payload)


@router.get(
    "/search/dashboard",
    response_model=SearchUsageDashboardResponse,
    summary="搜索供应商调用用量分析",
)
def get_search_usage_dashboard(
    period: str = Query("month", description="today | 7d | month | all | custom"),
    from_time: Optional[str] = Query(None),
    to_time: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    error_category: Optional[str] = Query(None),
    key_fingerprint: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> SearchUsageDashboardResponse:
    filters = _search_filters(
        period=period,
        from_time=from_time,
        to_time=to_time,
        provider=provider,
        source=source,
        success=success,
        error_category=error_category,
        key_fingerprint=key_fingerprint,
    )
    return SearchUsageDashboardResponse(
        **SearchUsageService().dashboard(**filters, page=page, page_size=page_size)
    )


@router.get(
    "/search/faults",
    response_model=SearchFaultStatusResponse,
    summary="当前搜索供应商故障状态",
)
def get_search_faults() -> SearchFaultStatusResponse:
    return SearchFaultStatusResponse(**SearchUsageService().fault_status())


@router.get(
    "/search/calls/{call_id}",
    response_model=SearchUsageCallDetail,
    dependencies=[Depends(require_enabled_admin_session)],
    summary="搜索调用脱敏出入参详情",
)
def get_search_call_detail(call_id: int) -> SearchUsageCallDetail:
    detail = SearchUsageService().get_call_detail(call_id)
    if detail is None:
        raise api_error(404, "not_found", "搜索调用记录不存在")
    return SearchUsageCallDetail(**detail)


@router.get(
    "/search/calls/{call_id}/export.json",
    dependencies=[Depends(require_enabled_admin_session)],
    summary="下载单条搜索调用 JSON",
)
def export_search_call_json(call_id: int) -> Response:
    detail = SearchUsageService().get_call_detail(call_id)
    if detail is None:
        raise api_error(404, "not_found", "搜索调用记录不存在")
    filename = f"search-call-{call_id}.json"
    return Response(
        content=json.dumps(detail, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get(
    "/search/export.csv",
    dependencies=[Depends(require_enabled_admin_session)],
    summary="按筛选条件导出搜索调用摘要 CSV",
)
def export_search_usage_csv(
    period: str = Query("month"),
    from_time: Optional[str] = Query(None),
    to_time: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    error_category: Optional[str] = Query(None),
    key_fingerprint: Optional[str] = Query(None),
) -> StreamingResponse:
    filters = _search_filters(
        period=period,
        from_time=from_time,
        to_time=to_time,
        provider=provider,
        source=source,
        success=success,
        error_category=error_category,
        key_fingerprint=key_fingerprint,
    )
    filename = f"search-usage-{datetime.now(_CST).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        SearchUsageService().iter_csv(**filters),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
