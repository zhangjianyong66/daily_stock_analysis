# -*- coding: utf-8 -*-
"""Schemas for LLM usage tracking API."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class CallTypeBreakdown(BaseModel):
    call_type: str = Field(..., description="'analysis' | 'agent' | 'market_review'")
    calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int


class ModelBreakdown(BaseModel):
    model: str
    calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int
    max_total_tokens: int = 0


class UsageCallRecord(BaseModel):
    id: int
    called_at: str = Field(..., description="ISO datetime string")
    call_type: str
    model: str
    stock_code: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class UsageSummaryResponse(BaseModel):
    period: str = Field(..., description="'today' | 'month' | 'all'")
    from_date: str = Field(..., description="ISO date string")
    to_date: str = Field(..., description="ISO date string")
    total_calls: int
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int
    by_call_type: List[CallTypeBreakdown]
    by_model: List[ModelBreakdown]


class UsageDashboardResponse(UsageSummaryResponse):
    recent_calls: List[UsageCallRecord]


class SearchUsageBreakdown(BaseModel):
    value: str
    count: int


class SearchUsageSummary(BaseModel):
    physical_requests: int
    business_searches: int
    success_count: int
    failure_count: int
    success_rate: float


class SearchUsageCallSummary(BaseModel):
    id: int
    business_search_id: str
    logical_request_id: str
    provider: str
    endpoint: str
    http_method: str
    call_source: str
    operation: str
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    dimension: Optional[str] = None
    lookback_days: Optional[int] = None
    provider_attempt: int
    physical_attempt: int
    key_fingerprint: str
    success: bool
    http_status: Optional[int] = None
    provider_code: Optional[str] = None
    provider_request_id: Optional[str] = None
    duration_ms: int
    result_count: Optional[int] = None
    error_category: Optional[str] = None
    error_summary: Optional[str] = None
    request_truncated: bool
    request_size_bytes: int
    request_sha256: str
    response_truncated: bool
    response_size_bytes: int
    response_sha256: str
    requested_at: str
    completed_at: str


class SearchUsagePage(BaseModel):
    items: List[SearchUsageCallSummary]
    total: int
    page: int
    page_size: int


class SearchProviderFault(BaseModel):
    id: int
    provider: str
    key_fingerprint: str
    error_category: str
    active: bool
    severity: str
    first_seen_at: str
    last_seen_at: str
    resolved_at: Optional[str] = None
    consecutive_count: int
    last_notified_at: Optional[str] = None
    last_notification_status: Optional[str] = None
    recovery_notified_at: Optional[str] = None
    last_error_summary: Optional[str] = None
    last_call_id: Optional[int] = None


class SearchProviderStatus(BaseModel):
    provider: str
    status: str
    configured_keys: int
    failed_keys: int


class SearchAuditHealth(BaseModel):
    healthy: bool
    process_lost_count: int
    persisted_lost_count: int
    last_gap_at: Optional[str] = None


class SearchFaultStatusResponse(BaseModel):
    active_faults: List[SearchProviderFault]
    providers: List[SearchProviderStatus]
    audit_health: SearchAuditHealth


class SearchUsageDashboardResponse(BaseModel):
    audit_started_at: Optional[str] = None
    summary: SearchUsageSummary
    by_provider: List[SearchUsageBreakdown]
    by_key: List[SearchUsageBreakdown]
    by_source: List[SearchUsageBreakdown]
    calls: SearchUsagePage
    faults: SearchFaultStatusResponse
    audit_health: SearchAuditHealth


class SearchUsageCallDetail(SearchUsageCallSummary):
    trace_id: Optional[str] = None
    query_hmac: Optional[str] = None
    request_snapshot: Any
    response_snapshot: Any
