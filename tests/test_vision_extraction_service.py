# -*- coding: utf-8 -*-
"""Tests for the shared Vision extraction boundary."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.services.vision_extraction_service import (
    MAX_SIZE_BYTES,
    VISION_API_TIMEOUT,
    complete_vision,
    resolve_vision_model,
    validate_image,
)


_GEMINI_KEY = "sk-gemini-testkey-1234"
_OPENAI_KEY = "sk-openai-testkey-1234"


def _cfg(**kwargs) -> Config:
    defaults = dict(
        stock_list=["600519"],
        tushare_token=None,
        llm_model_list=[],
        llm_channels=[],
        litellm_config_path=None,
        litellm_model="",
        litellm_fallback_models=[],
        vision_model="",
        vision_provider_priority="gemini,anthropic,openai",
        gemini_api_keys=[],
        gemini_model="gemini-3.1-pro-preview",
        anthropic_api_keys=[],
        anthropic_model="claude-sonnet-4-6",
        openai_api_keys=[],
        openai_model="gpt-5.5",
        openai_base_url=None,
        openai_vision_model=None,
        deepseek_api_keys=[],
        config_validate_mode="warn",
    )
    defaults.update(kwargs)
    return Config(**defaults)


def _image_bytes(mime_type: str) -> bytes:
    signatures = {
        "image/jpeg": b"\xff\xd8\xff" + b"\x00" * 20,
        "image/png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 12,
        "image/gif": b"GIF89a" + b"\x00" * 14,
        "image/webp": b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8,
    }
    return signatures[mime_type]


@pytest.mark.parametrize("mime_type", ["image/jpeg", "image/png", "image/gif", "image/webp"])
def test_validate_image_accepts_supported_magic_bytes(mime_type: str) -> None:
    assert validate_image(_image_bytes(mime_type), f"{mime_type}; charset=binary") == mime_type


def test_validate_image_rejects_unsupported_mime() -> None:
    with pytest.raises(ValueError, match="不支持的图片类型"):
        validate_image(_image_bytes("image/png"), "image/bmp")


def test_validate_image_rejects_empty_or_oversized_files() -> None:
    with pytest.raises(ValueError, match="图片内容为空"):
        validate_image(b"", "image/png")
    with pytest.raises(ValueError, match="Image too large"):
        validate_image(_image_bytes("image/png") + b"\x00" * MAX_SIZE_BYTES, "image/png")


def test_validate_image_rejects_mismatched_magic_bytes() -> None:
    with pytest.raises(ValueError, match="不匹配"):
        validate_image(_image_bytes("image/png"), "image/jpeg")


def test_resolve_vision_model_prefers_explicit_vision_model() -> None:
    cfg = _cfg(
        vision_model="gemini/gemini-2.0-flash",
        openai_vision_model="openai/gpt-4o",
        litellm_model="openai/gpt-5",
    )
    assert resolve_vision_model(cfg) == "gemini/gemini-2.0-flash"


def test_resolve_vision_model_does_not_fall_back_to_text_model_or_provider_keys() -> None:
    cfg = _cfg(
        litellm_model="openai/gpt-5",
        openai_api_keys=[_OPENAI_KEY],
        gemini_api_keys=[_GEMINI_KEY],
    )

    assert resolve_vision_model(cfg) == ""


def test_complete_vision_requires_explicit_vision_model() -> None:
    cfg = _cfg(litellm_model="openai/gpt-5", openai_api_keys=[_OPENAI_KEY])

    with patch("src.services.vision_extraction_service.get_config", return_value=cfg), patch(
        "src.services.vision_extraction_service.litellm.completion"
    ) as mock_completion:
        with pytest.raises(ValueError, match="VISION_MODEL"):
            complete_vision(_image_bytes("image/png"), "image/png", "return []")

    mock_completion.assert_not_called()


def test_complete_vision_builds_request_with_prompt_timeout_and_api_base() -> None:
    cfg = _cfg(
        vision_model="openai/gpt-4o-mini",
        openai_api_keys=[_OPENAI_KEY],
        openai_base_url="https://aihubmix.com/v1",
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="[]"))]
    )

    with patch("src.services.vision_extraction_service.get_config", return_value=cfg), patch(
        "src.services.vision_extraction_service.litellm.completion",
        return_value=response,
    ) as mock_completion:
        result = complete_vision(_image_bytes("image/png"), "image/png", "return []", max_tokens=128)

    assert result == "[]"
    kwargs = mock_completion.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-4o-mini"
    assert kwargs["max_tokens"] == 128
    assert kwargs["timeout"] == VISION_API_TIMEOUT
    assert kwargs["api_base"] == "https://aihubmix.com/v1"
    assert kwargs["extra_headers"] == {"APP-Code": "GPIJ3886"}
    content = kwargs["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "return []"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_complete_vision_retries_three_times_then_returns() -> None:
    cfg = _cfg(vision_model="gemini/gemini-2.0-flash", gemini_api_keys=[_GEMINI_KEY])
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="[]"))]
    )
    completion = MagicMock(side_effect=[RuntimeError("one"), RuntimeError("two"), response])

    with patch("src.services.vision_extraction_service.get_config", return_value=cfg), patch(
        "src.services.vision_extraction_service.litellm.completion", completion
    ), patch("src.services.vision_extraction_service.time.sleep") as mock_sleep:
        assert complete_vision(_image_bytes("image/jpeg"), "image/jpeg", "return []") == "[]"

    assert completion.call_count == 3
    assert [call.args[0] for call in mock_sleep.call_args_list] == [1, 2]


def test_complete_vision_rejects_hermes_route_before_calling_model() -> None:
    cfg = _cfg(
        vision_model="shared-route",
        openai_api_keys=[_OPENAI_KEY],
        llm_model_list=[
            {
                "model_name": "shared-route",
                "litellm_params": {
                    "model": "openai/hermes-agent",
                    "api_key": "sk-hermes-test-value",
                    "api_base": "http://127.0.0.1:8642/v1",
                },
                "model_info": {"dsa_channel": "hermes"},
            }
        ],
    )

    with patch("src.services.vision_extraction_service.get_config", return_value=cfg), patch(
        "src.services.vision_extraction_service.litellm.completion"
    ) as mock_completion:
        with pytest.raises(ValueError, match="Hermes Vision"):
            complete_vision(_image_bytes("image/jpeg"), "image/jpeg", "return []")

    mock_completion.assert_not_called()


def test_complete_vision_redacts_provider_secrets_from_errors_and_logs(caplog) -> None:
    cfg = _cfg(vision_model="openai/gpt-4o-mini", openai_api_keys=[_OPENAI_KEY])
    provider_error = RuntimeError(
        "request failed api_key=sk-provider-secret-1234567890 at https://provider.example/v1"
    )

    with patch("src.services.vision_extraction_service.get_config", return_value=cfg), patch(
        "src.services.vision_extraction_service.litellm.completion",
        side_effect=provider_error,
    ), patch("src.services.vision_extraction_service.time.sleep"):
        with pytest.raises(ValueError) as exc_info:
            complete_vision(_image_bytes("image/jpeg"), "image/jpeg", "return []")

    combined = f"{exc_info.value}\n{caplog.text}"
    assert "sk-provider-secret" not in combined
    assert "provider.example" not in combined
    assert "[REDACTED]" in combined
