# -*- coding: utf-8 -*-
"""Audited HTTP transport for real outbound search-provider requests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import requests

from src.schemas.search_usage import (
    SearchAuditContext,
    SearchErrorCategory,
    current_search_audit_context,
)
from src.services.search_usage_service import (
    SearchUsageService,
    fingerprint_search_value,
)
from src.utils.sanitize import (
    sanitize_diagnostic_text,
    sanitize_search_headers,
    sanitize_search_snapshot_text,
    sanitize_search_url,
    serialize_search_snapshot,
)


logger = logging.getLogger(__name__)

REQUEST_SNAPSHOT_MAX_BYTES = 256 * 1024
RESPONSE_SNAPSHOT_MAX_BYTES = 2 * 1024 * 1024

_QUOTA_TERMS = (
    "余额不足", "余额为0", "余额为 0", "余额 0", "额度不足", "额度耗尽", "免费额度 0",
    "充值余额 0", "quota exceeded", "quota exhausted", "insufficient balance", "credit exhausted",
    "no remaining credits", "out of credits",
)
_AUTH_TERMS = ("invalid api key", "api key invalid", "apikey invalid", "key无效", "key 无效", "unauthorized")
_PERMISSION_TERMS = ("permission denied", "forbidden", "无权限", "权限不足")
_DISABLED_TERMS = ("account disabled", "account suspended", "账户停用", "账号停用", "账户禁用")
_RATE_LIMIT_TERMS = ("rate limit", "too many requests", "频率达到限制", "请求过于频繁", "限流")


def audited_request_once(
    method: str,
    url: str,
    *,
    provider: str,
    api_key: Optional[str],
    query: Optional[str],
    headers: Optional[Mapping[str, Any]] = None,
    params: Optional[Mapping[str, Any]] = None,
    json_body: Any = None,
    data: Any = None,
    timeout: Any = None,
    credential_identity: Optional[str] = None,
    request_func: Optional[Callable[..., requests.Response]] = None,
    **kwargs: Any,
) -> requests.Response:
    """Send exactly one HTTP attempt and synchronously persist its audit row."""
    context = current_search_audit_context() or SearchAuditContext()
    physical_attempt = context.next_physical_attempt()
    requested_at = datetime.now(timezone.utc).replace(tzinfo=None)
    started = time.monotonic()
    request_snapshot = _redact_known_secret({
        "url": sanitize_search_url(url),
        "method": method.upper(),
        "headers": sanitize_search_headers(headers or {}, response=False),
        "query_params": params or {},
        "json": json_body,
        "body": data,
    }, api_key)
    request_json, request_size, request_truncated, request_sha = serialize_search_snapshot(
        request_snapshot,
        max_bytes=REQUEST_SNAPSHOT_MAX_BYTES,
    )
    key_source = api_key or credential_identity or sanitize_search_url(url)
    key_fingerprint = fingerprint_search_value(key_source, domain="search_api_key")
    query_hmac = fingerprint_search_value(query or "", domain="search_query") if query is not None else None

    response: Optional[requests.Response] = None
    error: Optional[BaseException] = None
    try:
        if request_func is not None:
            request_kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout, **kwargs}
            if params is not None:
                request_kwargs["params"] = params
            if json_body is not None:
                request_kwargs["json"] = json_body
            if data is not None:
                request_kwargs["data"] = data
            response = request_func(url, **request_kwargs)
        else:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                data=data,
                timeout=timeout,
                **kwargs,
            )
        return response
    except BaseException as exc:
        error = exc
        raise
    finally:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        response_data, response_text = _response_payload(response, error)
        success, category, provider_code = classify_search_response(
            provider=provider,
            response=response,
            payload=response_data,
            text=response_text,
            error=error,
        )
        response_snapshot = _redact_known_secret({
            "status": getattr(response, "status_code", None),
            "headers": sanitize_search_headers(getattr(response, "headers", {}) or {}, response=True),
            "body": response_data if response_data is not None else response_text,
            "exception": None if error is None else sanitize_diagnostic_text(error, max_length=500),
        }, api_key)
        response_json, response_size, response_truncated, response_sha = serialize_search_snapshot(
            response_snapshot,
            max_bytes=RESPONSE_SNAPSHOT_MAX_BYTES,
        )
        values = {
            **context.public_dict(),
            "trace_id": _provider_request_id(response, response_data),
            "provider": provider,
            "endpoint": sanitize_search_url(url),
            "http_method": method.upper(),
            "physical_attempt": physical_attempt,
            "key_fingerprint": key_fingerprint,
            "query_hmac": query_hmac,
            "success": success,
            "http_status": getattr(response, "status_code", None),
            "provider_code": provider_code,
            "provider_request_id": _provider_request_id(response, response_data),
            "duration_ms": duration_ms,
            "result_count": _result_count(response_data),
            "error_category": None if success else category,
            "error_summary": None if success else _error_summary(response_data, response_text, error, api_key),
            "request_snapshot_json": request_json,
            "request_size_bytes": request_size,
            "request_truncated": request_truncated,
            "request_sha256": request_sha,
            "response_snapshot_json": response_json,
            "response_size_bytes": response_size,
            "response_truncated": response_truncated,
            "response_sha256": response_sha,
            "requested_at": requested_at,
            "completed_at": completed_at,
        }
        try:
            SearchUsageService().record_physical_call(values)
        except Exception as audit_exc:
            logger.error(
                "[Search audit] 审计服务异常 provider=%s: %s",
                provider,
                sanitize_diagnostic_text(audit_exc),
                exc_info=True,
            )


class AuditedRequestsSession(requests.Session):
    """Requests session that audits every SDK HTTP attempt."""

    def __init__(self, *, provider: str, api_key: Optional[str], query: Optional[str]):
        super().__init__()
        self._audit_provider = provider
        self._audit_api_key = api_key
        self._audit_query = query

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        original_request = super().request
        return audited_request_once(
            method,
            url,
            provider=self._audit_provider,
            api_key=self._audit_api_key,
            query=self._audit_query,
            headers=kwargs.pop("headers", None),
            params=kwargs.pop("params", None),
            json_body=kwargs.pop("json", None),
            data=kwargs.pop("data", None),
            timeout=kwargs.pop("timeout", None),
            request_func=lambda request_url, **request_kwargs: original_request(method, request_url, **request_kwargs),
            **kwargs,
        )


def classify_search_response(
    *,
    provider: str = "Unknown",
    response: Optional[requests.Response],
    payload: Any,
    text: str,
    error: Optional[BaseException],
) -> Tuple[bool, Optional[str], Optional[str]]:
    provider_code = _provider_code(payload)
    payload_text = json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else ""
    semantic_text = f"{text} {payload_text}".lower()
    if error is not None:
        if isinstance(error, requests.exceptions.Timeout):
            return False, SearchErrorCategory.TIMEOUT.value, provider_code
        if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.SSLError)):
            return False, SearchErrorCategory.CONNECTION_ERROR.value, provider_code
        return False, SearchErrorCategory.OTHER.value, provider_code
    if any(term.lower() in semantic_text for term in _QUOTA_TERMS):
        return False, SearchErrorCategory.QUOTA_EXHAUSTED.value, provider_code
    if any(term.lower() in semantic_text for term in _DISABLED_TERMS):
        return False, SearchErrorCategory.ACCOUNT_DISABLED.value, provider_code
    status = getattr(response, "status_code", None)
    if status == 429 or any(term.lower() in semantic_text for term in _RATE_LIMIT_TERMS):
        return False, SearchErrorCategory.RATE_LIMITED.value, provider_code
    if status == 401 or any(term.lower() in semantic_text for term in _AUTH_TERMS):
        return False, SearchErrorCategory.AUTH_INVALID.value, provider_code
    if status == 403 or any(term.lower() in semantic_text for term in _PERMISSION_TERMS):
        return False, SearchErrorCategory.PERMISSION_DENIED.value, provider_code
    if status is not None and status >= 500:
        return False, SearchErrorCategory.PROVIDER_5XX.value, provider_code
    if status is not None and not 200 <= status < 300:
        return False, SearchErrorCategory.OTHER.value, provider_code
    if _provider_payload_failed(payload):
        return False, SearchErrorCategory.OTHER.value, provider_code
    if provider == "Anspire" and isinstance(payload, Mapping) and "results" not in payload:
        return False, SearchErrorCategory.INVALID_RESPONSE.value, provider_code
    if response is not None and _looks_json(response) and payload is None:
        return False, SearchErrorCategory.INVALID_RESPONSE.value, provider_code
    return True, None, provider_code


def _response_payload(
    response: Optional[requests.Response], error: Optional[BaseException]
) -> Tuple[Any, str]:
    if response is None:
        return None, "" if error is None else str(error)
    text = str(getattr(response, "text", "") or "")
    try:
        return response.json(), text
    except Exception:
        return None, text


def _looks_json(response: requests.Response) -> bool:
    content_type = str((getattr(response, "headers", {}) or {}).get("content-type", "")).lower()
    return "json" in content_type


def _provider_code(payload: Any) -> Optional[str]:
    if not isinstance(payload, Mapping):
        return None
    for key in ("code", "status_code", "error_code"):
        if key in payload and payload[key] is not None:
            return str(payload[key])[:64]
    base_resp = payload.get("base_resp")
    if isinstance(base_resp, Mapping) and base_resp.get("status_code") is not None:
        return str(base_resp["status_code"])[:64]
    return None


def _provider_payload_failed(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    code = payload.get("code")
    if code is not None and str(code) not in {"0", "200", "success", "ok"}:
        return True
    base_resp = payload.get("base_resp")
    if isinstance(base_resp, Mapping) and str(base_resp.get("status_code", 0)) != "0":
        return True
    return False


def _result_count(payload: Any) -> Optional[int]:
    if not isinstance(payload, Mapping):
        return None
    candidates = [
        payload.get("results"),
        payload.get("organic"),
        (payload.get("web") or {}).get("results") if isinstance(payload.get("web"), Mapping) else None,
        (((payload.get("data") or {}).get("webPages") or {}).get("value"))
        if isinstance(payload.get("data"), Mapping)
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return len(candidate)
    return None


def _provider_request_id(response: Optional[requests.Response], payload: Any) -> Optional[str]:
    headers = getattr(response, "headers", {}) or {}
    for key in ("x-request-id", "request-id", "x-trace-id", "trace-id", "x-correlation-id"):
        value = headers.get(key) or headers.get(key.title())
        if value:
            return sanitize_search_snapshot_text(value)[:128]
    if isinstance(payload, Mapping):
        for key in ("request_id", "requestId", "trace_id", "traceId"):
            if payload.get(key):
                return sanitize_search_snapshot_text(payload[key])[:128]
    return None


def _error_summary(payload: Any, text: str, error: Optional[BaseException], api_key: Optional[str]) -> str:
    if error is not None:
        value = str(error)
    elif isinstance(payload, Mapping):
        value = payload.get("message") or payload.get("msg") or text or str(payload)
    else:
        value = text
    if api_key:
        value = str(value).replace(api_key, "[REDACTED]")
    return sanitize_diagnostic_text(value, max_length=500) or "搜索供应商请求失败"


def _redact_known_secret(value: Any, secret: Optional[str]) -> Any:
    if not secret:
        return value
    if isinstance(value, dict):
        return {key: _redact_known_secret(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_known_secret(item, secret) for item in value]
    if isinstance(value, tuple):
        return [_redact_known_secret(item, secret) for item in value]
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    return value
