# -*- coding: utf-8 -*-
"""Shared text sanitizers for logs, diagnostics, and API payloads."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Mapping, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = {
    "authorization",
    "cookie",
    "password",
    "secret",
    "sendkey",
    "token",
    "webhook",
}
_SENSITIVE_KEY_PHRASES = {
    "access_token",
    "accesstoken",
    "api_key",
    "apikey",
    "api_token",
    "apitoken",
    "auth_token",
    "authtoken",
    "authorization_header",
    "authorizationheader",
    "license_key",
    "licensekey",
    "private_key",
    "privatekey",
    "refresh_token",
    "refreshtoken",
    "secret_key",
    "secretkey",
    "session_token",
    "sessiontoken",
    "send_key",
    "sendkey",
    "webhook_url",
    "webhookurl",
}
_SENSITIVE_COMPACT_KEY_PHRASES = {
    phrase.replace("_", "") for phrase in _SENSITIVE_KEY_PHRASES
}
_SENSITIVE_COMPACT_KEY_PATTERN = re.compile(
    r"authorization|cookie|password|secret|sendkey|token(?!s)|webhook"
)
_URL_PATTERN = re.compile(r"https?://[^\s,;)\]}]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\b(bearer\s+)[^\s,;&]+", re.IGNORECASE)
_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"\b(authorization|proxy[_-]?authorization)(\s*[:=]\s*)"
    r"(?:(?:Bearer|Basic|Token|Digest)\s+)?[^\s,;&]+",
    re.IGNORECASE,
)
_COOKIE_HEADER_PATTERN = re.compile(
    r"\b(cookie|set[_-]?cookie)(\s*[:=]\s*)[^\s,;&]+",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b(token|secret|password|sendkey|api[_-]?key|apikey|api[_-]?token|auth[_-]?token|"
    r"access[_-]?token|refresh[_-]?token|session[_-]?token|license[_-]?key|private[_-]?key|"
    r"secret[_-]?key|webhook[_-]?url|authorization|proxy[_-]?authorization|cookie|set[_-]?cookie)"
    r"([=:]\s*)[^\s,;&]+",
    re.IGNORECASE,
)
_TOKEN_LIKE_PATTERN = re.compile(
    r"\b(?:sk-[a-z0-9_\-]{16,}|xox[baprs]-[a-z0-9\-]{16,}|gh[pousr]_[a-z0-9_]{20,})\b",
    re.IGNORECASE,
)

_SEARCH_REQUEST_HEADER_ALLOWLIST = {
    "accept",
    "content-type",
    "user-agent",
    "x-request-id",
    "x-trace-id",
    "x-correlation-id",
    "mm-api-source",
}
_SEARCH_RESPONSE_HEADER_ALLOWLIST = {
    "content-type",
    "content-length",
    "date",
    "retry-after",
    "x-request-id",
    "x-trace-id",
    "x-correlation-id",
    "request-id",
    "trace-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
}


def sanitize_diagnostic_text(text: Any, *, max_length: int = 300) -> str:
    """Redact common secrets and URLs from diagnostic text."""
    sanitized = str(text or "").strip()
    if not sanitized:
        return ""
    sanitized = _AUTHORIZATION_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _COOKIE_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _BEARER_PATTERN.sub(r"\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(token|secret|password|sendkey)([=:]\s*)[^\s,;&]+", r"\1\2[REDACTED]", sanitized)
    sanitized = re.sub(r"https?://[^\s]+", "[REDACTED_URL]", sanitized)
    return " ".join(sanitized.split())[:max_length]


def redact_sensitive_mapping(obj: Any) -> Any:
    """Recursively redact sensitive values from mappings by key name only.

    This helper intentionally does not inspect arbitrary string values. P1 only
    needs a deterministic serializer for AnalysisContextPack dictionaries.
    """
    if isinstance(obj, dict):
        redacted = {}
        for key, value in obj.items():
            if _is_sensitive_mapping_key(key):
                redacted[key] = _REDACTED
            else:
                redacted[key] = redact_sensitive_mapping(value)
        return redacted
    if isinstance(obj, list):
        return [redact_sensitive_mapping(item) for item in obj]
    return obj


def sanitize_decision_signal_text(text: Any) -> str:
    """Redact obvious secrets from persisted decision-signal text without truncating."""
    sanitized = str(text or "").strip()
    if not sanitized:
        return ""
    sanitized = _URL_PATTERN.sub(_redact_sensitive_url_match, sanitized)
    sanitized = _AUTHORIZATION_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _COOKIE_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _BEARER_PATTERN.sub(r"\1[REDACTED]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _TOKEN_LIKE_PATTERN.sub("[REDACTED]", sanitized)
    return " ".join(sanitized.split())


def sanitize_decision_signal_payload(obj: Any) -> Any:
    """Redact decision-signal JSON payloads by sensitive keys and string values."""
    redacted = redact_sensitive_mapping(obj)
    return _sanitize_decision_signal_payload_values(redacted)


def sanitize_search_snapshot_value(obj: Any) -> Any:
    """Deep-redact a search request/response value while preserving business data."""
    if isinstance(obj, Mapping):
        result: Dict[str, Any] = {}
        for key, value in obj.items():
            key_text = str(key)
            if _is_sensitive_mapping_key(key_text):
                result[key_text] = _REDACTED
            else:
                result[key_text] = sanitize_search_snapshot_value(value)
        return result
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_search_snapshot_value(item) for item in obj]
    if isinstance(obj, bytes):
        return sanitize_search_snapshot_text(obj.decode("utf-8", errors="replace"))
    if isinstance(obj, str):
        return sanitize_search_snapshot_text(obj)
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return sanitize_search_snapshot_text(str(obj))


def sanitize_search_snapshot_text(text: Any) -> str:
    """Redact credentials from persisted search payload text without truncating."""
    sanitized = str(text or "")
    sanitized = _URL_PATTERN.sub(_sanitize_search_url_match, sanitized)
    sanitized = _AUTHORIZATION_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _COOKIE_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _BEARER_PATTERN.sub(r"\1[REDACTED]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    return _TOKEN_LIKE_PATTERN.sub(_REDACTED, sanitized)


def sanitize_search_url(url: Any) -> str:
    """Keep a URL useful for auditing while redacting credential-like query values."""
    value = str(url or "")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return sanitize_search_snapshot_text(value)
    if not parsed.scheme or not parsed.netloc:
        return sanitize_search_snapshot_text(value)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    query = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, _REDACTED if _is_sensitive_mapping_key(key) else sanitize_search_snapshot_text(item_value)))
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query, doseq=True), ""))


def sanitize_search_headers(headers: Any, *, response: bool = False) -> Dict[str, str]:
    """Return an allowlisted and redacted header mapping for audit snapshots."""
    if not isinstance(headers, Mapping):
        try:
            headers = dict(headers or {})
        except Exception:
            return {}
    allowed = _SEARCH_RESPONSE_HEADER_ALLOWLIST if response else _SEARCH_REQUEST_HEADER_ALLOWLIST
    result: Dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key)
        normalized = key_text.lower()
        if _is_sensitive_mapping_key(normalized):
            continue
        if normalized not in allowed and not normalized.startswith("x-ratelimit-"):
            continue
        result[key_text] = sanitize_search_snapshot_text(value)
    return result


def serialize_search_snapshot(value: Any, *, max_bytes: int) -> Tuple[str, int, bool, str]:
    """Serialize a redacted snapshot with deterministic size/hash/truncation metadata."""
    sanitized = sanitize_search_snapshot_value(value)
    payload = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    raw = payload.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) <= max_bytes:
        return payload, len(raw), False, digest
    preview = raw[:max_bytes].decode("utf-8", errors="ignore")
    truncated_payload = json.dumps(
        {"truncated": True, "preview": preview},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return truncated_payload, len(raw), True, digest


def _sanitize_search_url_match(match: re.Match[str]) -> str:
    return sanitize_search_url(match.group(0))


def _sanitize_decision_signal_payload_values(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            key: _sanitize_decision_signal_payload_values(value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_sanitize_decision_signal_payload_values(item) for item in obj]
    if isinstance(obj, str):
        return sanitize_decision_signal_text(obj)
    return obj


def _redact_sensitive_url_match(match: re.Match[str]) -> str:
    url = match.group(0)
    if _is_sensitive_url(url):
        return "[REDACTED_URL]"
    return url


def _is_sensitive_url(url: str) -> bool:
    if _TOKEN_LIKE_PATTERN.search(url):
        return True
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.username or parsed.password:
        return True
    if _is_webhook_url(parsed.hostname or "", parsed.path):
        return True
    return (
        _has_sensitive_url_params(parsed.query)
        or _has_sensitive_url_params(parsed.fragment)
    )


def _is_webhook_url(hostname: str, path: str) -> bool:
    hostname = str(hostname or "").lower().strip(".")
    normalized_path = f"/{path.lstrip('/').lower()}"
    path_segments = [segment for segment in normalized_path.split("/") if segment]

    if hostname == "hooks.slack.com" and normalized_path.startswith("/services/"):
        return True
    if hostname in {"discord.com", "discordapp.com"} and "/api/webhooks/" in normalized_path:
        return True
    if hostname == "open.feishu.cn" and "/open-apis/bot/" in normalized_path and "/hook/" in normalized_path:
        return True
    if hostname == "oapi.dingtalk.com" and normalized_path.startswith("/robot/send"):
        return True
    if hostname == "qyapi.weixin.qq.com" and normalized_path.startswith("/cgi-bin/webhook/send"):
        return True
    if hostname in {"sctapi.ftqq.com", "sc.ftqq.com"}:
        return True
    if hostname.startswith("hooks."):
        return True
    if {"hook", "webhook", "webhooks"} & set(path_segments):
        return True
    return False


def _has_sensitive_url_params(params_text: str) -> bool:
    if not params_text:
        return False
    try:
        params = parse_qsl(params_text, keep_blank_values=True)
    except ValueError:
        return False
    for key, value in params:
        key_text = str(key or "").strip().lower()
        if _is_sensitive_mapping_key(key_text):
            return True
        if _TOKEN_LIKE_PATTERN.search(str(value or "")):
            return True
    return False


def _is_sensitive_mapping_key(key: Any) -> bool:
    key_text = str(key or "").strip()
    if not key_text:
        return False
    parts = _mapping_key_parts(key_text)
    if _has_sensitive_phrase("_".join(parts)):
        return True
    return bool(set(parts) & _SENSITIVE_KEY_PARTS)


def _has_sensitive_phrase(normalized_key: str) -> bool:
    padded_key = f"_{normalized_key}_"
    if any(f"_{phrase}_" in padded_key for phrase in _SENSITIVE_KEY_PHRASES):
        return True
    compact_key = normalized_key.replace("_", "")
    if any(phrase in compact_key for phrase in _SENSITIVE_COMPACT_KEY_PHRASES):
        return True
    return bool(_SENSITIVE_COMPACT_KEY_PATTERN.search(compact_key))


def _mapping_key_parts(key_text: str) -> list[str]:
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key_text)
    return [
        part.lower()
        for part in re.split(r"[^A-Za-z0-9]+", split_camel)
        if part
    ]
