# -*- coding: utf-8 -*-
"""Shared image validation and Vision model invocation helpers."""

from __future__ import annotations

import base64
import logging
import random
import sys
import time
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.config import (
    VISION_API_MODE_RESPONSES,
    Config,
    extra_litellm_params,
    get_config,
    get_exact_llm_route_deployments,
)
from src.llm.hermes import build_hermes_redaction_values, route_has_hermes, sanitize_hermes_error_text
from src.utils.sanitize import sanitize_diagnostic_text

logger = logging.getLogger(__name__)


class VisionExtractionError(ValueError):
    """Safe Vision boundary error with a stable client-facing code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


class _LiteLLMPlaceholder:
    """Provide a patchable placeholder before litellm is imported."""

    completion = None
    Router = None


litellm = sys.modules.get("litellm") or _LiteLLMPlaceholder()

ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_SIZE_BYTES = 5 * 1024 * 1024
VISION_API_TIMEOUT = 300
VISION_MAX_ATTEMPTS = 2

_IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}


def _verify_image_magic_bytes(image_bytes: bytes, mime_type: str) -> None:
    if len(image_bytes) < 12:
        raise VisionExtractionError("图片文件过小或损坏", code="invalid_image")
    if mime_type == "image/webp":
        if image_bytes[:4] != b"RIFF" or image_bytes[8:12] != b"WEBP":
            raise VisionExtractionError(
                "文件内容与声明的类型 image/webp 不匹配，可能被篡改",
                code="invalid_image",
            )
        return
    signatures = _IMAGE_SIGNATURES.get(mime_type)
    if not signatures:
        raise VisionExtractionError(f"无法验证类型: {mime_type}", code="unsupported_type")
    if not any(image_bytes.startswith(signature) for signature in signatures):
        raise VisionExtractionError(
            f"文件内容与声明的类型 {mime_type} 不匹配，可能被篡改",
            code="invalid_image",
        )


def validate_image(image_bytes: bytes, mime_type: str) -> str:
    """Validate an uploaded image and return its normalized MIME type."""
    normalized_mime = (mime_type or "image/jpeg").strip().lower().split(";", 1)[0].strip()
    if normalized_mime not in ALLOWED_MIME:
        raise VisionExtractionError(
            f"不支持的图片类型: {normalized_mime}。允许: {list(ALLOWED_MIME)}",
            code="unsupported_type",
        )
    if not image_bytes:
        raise VisionExtractionError("图片内容为空", code="invalid_image")
    if len(image_bytes) > MAX_SIZE_BYTES:
        raise VisionExtractionError(
            f"Image too large (max {MAX_SIZE_BYTES // (1024 * 1024)}MB)",
            code="file_too_large",
        )
    _verify_image_magic_bytes(image_bytes, normalized_mime)
    return normalized_mime


def resolve_vision_model(config: Config | None = None) -> str:
    """Resolve only explicitly configured Vision model settings."""
    cfg = config or get_config()
    return (cfg.vision_model or cfg.openai_vision_model or "").strip()


def get_vision_api_keys(model: str, config: Config) -> List[str]:
    """Return managed API keys for the selected Vision provider."""
    deployment_keys = [
        str((deployment.get("litellm_params") or {}).get("api_key") or "").strip()
        for deployment in get_exact_llm_route_deployments(
            getattr(config, "llm_model_list", []) or [],
            model,
        )
    ]
    if model.startswith("gemini/") or model.startswith("vertex_ai/"):
        keys = config.gemini_api_keys
    elif model.startswith("anthropic/"):
        keys = config.anthropic_api_keys
    else:
        keys = config.openai_api_keys
    return list(dict.fromkeys(
        key for key in [*deployment_keys, *keys] if key and len(key) >= 8
    ))


def _load_litellm():
    global litellm
    if getattr(litellm, "completion", None) is None:
        import litellm as litellm_module

        litellm = litellm_module
    return litellm


def _mapping_or_attr(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def build_vision_responses_input(data_url: str, prompt: str) -> List[Dict[str, Any]]:
    """Build the shared Responses API multimodal input shape."""
    return [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url},
            ],
        }
    ]


def extract_vision_responses_text(response: Any) -> str:
    """Normalize LiteLLM Responses output across mapping and object shapes."""
    direct_text = _mapping_or_attr(response, "output_text", None)
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    for output_item in _mapping_or_attr(response, "output", None) or []:
        for content_item in _mapping_or_attr(output_item, "content", None) or []:
            item_type = str(_mapping_or_attr(content_item, "type", "") or "").strip()
            if item_type not in {"output_text", "text"}:
                continue
            text = _mapping_or_attr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise VisionExtractionError("LiteLLM vision returned empty response", code="vision_failed")


def _extract_chat_completion_text(response: Any) -> str:
    choices = _mapping_or_attr(response, "choices", None) or []
    if choices:
        message = _mapping_or_attr(choices[0], "message", None)
        content = _mapping_or_attr(message, "content", None) if message is not None else None
        if isinstance(content, str) and content.strip():
            return content
    raise VisionExtractionError("LiteLLM vision returned empty response", code="vision_failed")


def _build_vision_router(
    deployments: Sequence[Dict[str, Any]],
    completion_module: Any,
) -> Any:
    router_class = getattr(completion_module, "Router", None)
    if not callable(router_class):
        raise VisionExtractionError(
            "当前 LiteLLM 不支持 Vision 渠道路由，请升级依赖后重试。",
            code="vision_not_configured",
        )
    try:
        return router_class(
            model_list=list(deployments),
            routing_strategy="simple-shuffle",
            num_retries=0,
            max_fallbacks=0,
            disable_cooldowns=True,
        )
    except Exception as exc:
        raise VisionExtractionError(
            "Vision 渠道路由初始化失败，请检查 LLM Channel 配置。",
            code="vision_not_configured",
        ) from exc


def _vision_route_redaction_values(deployments: Sequence[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for deployment in deployments:
        params = deployment.get("litellm_params") or {}
        api_key = str(params.get("api_key") or "").strip()
        if api_key:
            values.append(api_key)
        for header_value in (params.get("extra_headers") or {}).values():
            text = str(header_value or "").strip()
            if text:
                values.append(text)
    return values


def _call_vision_once(
    image_b64: str,
    mime_type: str,
    prompt: str,
    *,
    max_tokens: int,
    config: Config,
    completion_module=None,
    api_key: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    router: Any = None,
) -> str:
    model = resolve_vision_model(config)
    if not model:
        raise VisionExtractionError(
            "未配置 Vision 模型，请前往设置页配置 VISION_MODEL。",
            code="vision_not_configured",
        )
    if route_has_hermes(getattr(config, "llm_model_list", []) or [], model):
        raise VisionExtractionError(
            "Hermes Vision 未验证：VISION_MODEL 不能选择包含 Hermes deployment 的 route。",
            code="vision_unsupported",
        )

    deployments = get_exact_llm_route_deployments(
        getattr(config, "llm_model_list", []) or [],
        model,
    )
    api_mode = getattr(config, "vision_api_mode", "chat_completions")
    keys = get_vision_api_keys(model, config)
    if api_mode == VISION_API_MODE_RESPONSES and not deployments:
        raise VisionExtractionError(
            "VISION_API_MODE=responses 需要 VISION_MODEL 精确匹配一个 LLM Channel route。",
            code="vision_not_configured",
        )
    if not keys:
        raise VisionExtractionError(
            f"No API key found for vision model {model}",
            code="vision_not_configured",
        )
    key = api_key if api_key and api_key in keys else random.choice(keys)

    data_url = f"data:{mime_type};base64,{image_b64}"
    timeout = timeout_seconds if timeout_seconds is not None else VISION_API_TIMEOUT
    call_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "timeout": timeout,
    }

    client = completion_module or _load_litellm()
    route_client = router
    if deployments and route_client is None:
        route_client = _build_vision_router(deployments, client)
    if api_mode == VISION_API_MODE_RESPONSES:
        responses_method = getattr(route_client, "responses", None)
        if not callable(responses_method):
            raise VisionExtractionError(
                "当前 LiteLLM Router 不支持 Responses API，请升级依赖后重试。",
                code="vision_not_configured",
            )
        response = responses_method(
            model=model,
            input=build_vision_responses_input(data_url, prompt),
            max_output_tokens=max_tokens,
            timeout=timeout,
        )
        return extract_vision_responses_text(response)

    if route_client is not None:
        response = route_client.completion(**call_kwargs)
    else:
        call_kwargs["api_key"] = key
        call_kwargs.update(extra_litellm_params(model, config))
        response = client.completion(**call_kwargs)
    return _extract_chat_completion_text(response)


def complete_vision(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    *,
    max_tokens: int = 1024,
    attempt_callback: Optional[Callable[[int, int], None]] = None,
    deadline_monotonic: Optional[float] = None,
    _config: Config | None = None,
    _completion_module=None,
) -> str:
    """Validate an image and call the configured Vision model with retries."""
    normalized_mime = validate_image(image_bytes, mime_type)
    cfg = _config or get_config()
    model = resolve_vision_model(cfg)
    if not model:
        raise VisionExtractionError(
            "未配置 Vision 模型，请前往设置页配置 VISION_MODEL。",
            code="vision_not_configured",
        )
    if route_has_hermes(getattr(cfg, "llm_model_list", []) or [], model):
        raise VisionExtractionError(
            "Hermes Vision 未验证：VISION_MODEL 不能选择包含 Hermes deployment 的 route。",
            code="vision_unsupported",
        )
    deployments = get_exact_llm_route_deployments(
        getattr(cfg, "llm_model_list", []) or [],
        model,
    )
    if getattr(cfg, "vision_api_mode", "chat_completions") == VISION_API_MODE_RESPONSES and not deployments:
        raise VisionExtractionError(
            "VISION_API_MODE=responses 需要 VISION_MODEL 精确匹配一个 LLM Channel route。",
            code="vision_not_configured",
        )
    if not get_vision_api_keys(model, cfg):
        raise VisionExtractionError(
            f"No API key found for vision model {model}",
            code="vision_not_configured",
        )

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    last_error: Optional[Exception] = None
    last_safe_error = "unknown provider error"
    completion_module = _completion_module or _load_litellm()
    router = _build_vision_router(deployments, completion_module) if deployments else None
    redaction_values = build_hermes_redaction_values(
        *get_vision_api_keys(model, cfg),
        *_vision_route_redaction_values(deployments),
    )
    for attempt in range(VISION_MAX_ATTEMPTS):
        if attempt_callback is not None:
            attempt_callback(attempt + 1, VISION_MAX_ATTEMPTS)
        timeout_seconds = float(VISION_API_TIMEOUT)
        if deadline_monotonic is not None:
            remaining = deadline_monotonic - time.monotonic()
            if remaining <= 0:
                raise VisionExtractionError("Vision 任务已超过整体运行上限", code="vision_timeout")
            timeout_seconds = min(timeout_seconds, remaining)
        try:
            return _call_vision_once(
                image_b64,
                normalized_mime,
                prompt,
                max_tokens=max_tokens,
                config=cfg,
                completion_module=completion_module,
                timeout_seconds=timeout_seconds,
                router=router,
            )
        except Exception as exc:
            if isinstance(exc, VisionExtractionError):
                raise
            last_error = exc
            provider_error = sanitize_hermes_error_text(exc, redaction_values=redaction_values)
            last_safe_error = sanitize_diagnostic_text(provider_error) or type(exc).__name__
            if attempt < VISION_MAX_ATTEMPTS - 1 and _is_transient_vision_error(exc, last_safe_error):
                delay = 1
                if deadline_monotonic is not None:
                    remaining = deadline_monotonic - time.monotonic()
                    if remaining <= 0:
                        break
                    delay = min(delay, remaining)
                logger.warning(
                    "Vision 调用尝试 %s/%s 失败，%ss 后重试: %s",
                    attempt + 1,
                    VISION_MAX_ATTEMPTS,
                    delay,
                    last_safe_error,
                )
                time.sleep(delay)
                continue
            break

    error_lower = f"{type(last_error).__name__} {last_safe_error}".lower()
    if "timeout" in error_lower or "timed out" in error_lower:
        error_code = "vision_timeout"
    elif "rate" in error_lower or "429" in error_lower:
        error_code = "vision_rate_limited"
    elif any(token in error_lower for token in ("authentication", "unauthorized", "invalid api key", "401", "403")):
        error_code = "vision_auth_failed"
    elif any(token in error_lower for token in ("unsupported", "does not support", "image input")):
        error_code = "vision_unsupported"
    elif any(token in error_lower for token in ("connection", "network", "dns", "name resolution")):
        error_code = "vision_network_error"
    else:
        error_code = "vision_failed"
    raise VisionExtractionError(
        f"Vision API 调用失败，请检查 API Key 与网络: {last_safe_error}",
        code=error_code,
    ) from last_error


def _is_transient_vision_error(exc: Exception, safe_error: str) -> bool:
    """Return whether a provider failure is safe to retry once."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    error_text = f"{type(exc).__name__} {safe_error}".lower()
    if any(token in error_text for token in ("rate limit", "ratelimit", "429", "authentication", "unauthorized")):
        return False
    if any(token in error_text for token in ("unsupported", "invalid image", "bad request", "empty response")):
        return False
    return any(
        token in error_text
        for token in (
            "timeout",
            "timed out",
            "connection",
            "connecterror",
            "readerror",
            "remote disconnected",
            "network is unreachable",
            "temporary failure",
        )
    )
