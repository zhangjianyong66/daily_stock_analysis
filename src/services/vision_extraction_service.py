# -*- coding: utf-8 -*-
"""Shared image validation and Vision model invocation helpers."""

from __future__ import annotations

import base64
import logging
import random
import sys
import time
from typing import List, Optional

from src.config import Config, extra_litellm_params, get_config
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


litellm = sys.modules.get("litellm") or _LiteLLMPlaceholder()

ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_SIZE_BYTES = 5 * 1024 * 1024
VISION_API_TIMEOUT = 60

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
    if model.startswith("gemini/") or model.startswith("vertex_ai/"):
        keys = config.gemini_api_keys
    elif model.startswith("anthropic/"):
        keys = config.anthropic_api_keys
    else:
        keys = config.openai_api_keys
    return [key for key in keys if key and len(key) >= 8]


def _load_litellm():
    global litellm
    if getattr(litellm, "completion", None) is None:
        import litellm as litellm_module

        litellm = litellm_module
    return litellm


def _call_vision_once(
    image_b64: str,
    mime_type: str,
    prompt: str,
    *,
    max_tokens: int,
    config: Config,
    completion_module=None,
    api_key: Optional[str] = None,
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

    keys = get_vision_api_keys(model, config)
    if not keys:
        raise VisionExtractionError(
            f"No API key found for vision model {model}",
            code="vision_not_configured",
        )
    key = api_key if api_key and api_key in keys else random.choice(keys)

    data_url = f"data:{mime_type};base64,{image_b64}"
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
        "api_key": key,
        "timeout": VISION_API_TIMEOUT,
    }
    call_kwargs.update(extra_litellm_params(model, config))

    client = completion_module or _load_litellm()
    response = client.completion(**call_kwargs)
    if response and response.choices and response.choices[0].message.content:
        return response.choices[0].message.content
    raise ValueError("LiteLLM vision returned empty response")


def complete_vision(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    *,
    max_tokens: int = 1024,
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
    if not get_vision_api_keys(model, cfg):
        raise VisionExtractionError(
            f"No API key found for vision model {model}",
            code="vision_not_configured",
        )

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    last_error: Optional[Exception] = None
    last_safe_error = "unknown provider error"
    redaction_values = build_hermes_redaction_values(*get_vision_api_keys(model, cfg))
    for attempt in range(3):
        try:
            return _call_vision_once(
                image_b64,
                normalized_mime,
                prompt,
                max_tokens=max_tokens,
                config=cfg,
                completion_module=_completion_module,
            )
        except Exception as exc:
            last_error = exc
            provider_error = sanitize_hermes_error_text(exc, redaction_values=redaction_values)
            last_safe_error = sanitize_diagnostic_text(provider_error) or type(exc).__name__
            if attempt < 2:
                delay = 2**attempt
                logger.warning(
                    "Vision 调用尝试 %s/3 失败，%ss 后重试: %s",
                    attempt + 1,
                    delay,
                    last_safe_error,
                )
                time.sleep(delay)

    error_lower = f"{type(last_error).__name__} {last_safe_error}".lower()
    if "timeout" in error_lower or "timed out" in error_lower:
        error_code = "vision_timeout"
    elif "rate" in error_lower or "429" in error_lower:
        error_code = "vision_rate_limited"
    else:
        error_code = "vision_failed"
    raise VisionExtractionError(
        f"Vision API 调用失败，请检查 API Key 与网络: {last_safe_error}",
        code=error_code,
    ) from last_error
