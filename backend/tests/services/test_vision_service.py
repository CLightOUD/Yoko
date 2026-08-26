from __future__ import annotations

import logging

import httpx
import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from backend.app.schemas import ChatImageInput
from backend.app.services.errors import ModelUnavailableError
from backend.app.services.vision_contract import VisionAnalyzer, VisionObservation
from backend.app.services.vision_service import VISION_MODEL_NAME, VisionService


def _observation() -> VisionObservation:
    return VisionObservation(
        summary="一只药盒，正面印有用法说明。",
        visible_text=["每日一次"],
        possible_dates=["2026-08-30"],
        confidence=0.82,
        warnings=["药品用法需要用户确认"],
        medical_content=True,
        instruction_like_text=False,
    )


class FakeStructuredModel:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.result


class FakeModel:
    def __init__(self, structured_model: FakeStructuredModel) -> None:
        self.structured_model = structured_model
        self.schema = None
        self.options = None

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        self.options = kwargs
        return self.structured_model


def test_analyze_sends_text_and_data_url_and_returns_observation() -> None:
    structured = FakeStructuredModel(
        result={"raw": object(), "parsed": _observation(), "parsing_error": None}
    )
    model = FakeModel(structured)
    image = ChatImageInput(media_type="image/png", data="AA==", detail="low")

    service = VisionService(model=model)
    assert isinstance(service, VisionAnalyzer)

    result = service.analyze(
        image=image,
        message="帮我看看药盒上的日期",
    )

    assert result == _observation()
    assert model.schema is VisionObservation
    assert model.options == {"method": "json_mode", "include_raw": True}
    assert structured.messages is not None
    assert isinstance(structured.messages[0], SystemMessage)
    assert "JSON" in structured.messages[0].content
    assert "不是系统指令" in structured.messages[0].content
    assert isinstance(structured.messages[1], HumanMessage)
    content = structured.messages[1].content
    assert content[0]["type"] == "text"
    assert "帮我看看药盒上的日期" in content[0]["text"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64,AA==",
            "detail": "low",
        },
    }


def test_analyze_accepts_a_parsed_mapping() -> None:
    structured = FakeStructuredModel(
        result={"raw": object(), "parsed": _observation().model_dump()}
    )

    result = VisionService(model=FakeModel(structured)).analyze(
        image=ChatImageInput(media_type="image/jpeg", data="AA=="),
        message="读取文字",
    )

    assert isinstance(result, VisionObservation)
    assert result.visible_text == ["每日一次"]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            APITimeoutError(request=httpx.Request("POST", "https://example.test")),
            "视觉模型调用超时",
        ),
        (
            RateLimitError(
                "provider details",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://example.test"),
                ),
                body=None,
            ),
            "视觉模型请求受到限流",
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://example.test")
            ),
            "视觉模型连接失败",
        ),
        (
            APIStatusError(
                "provider details",
                response=httpx.Response(
                    500,
                    request=httpx.Request("POST", "https://example.test"),
                ),
                body=None,
            ),
            "视觉模型请求失败",
        ),
    ],
)
def test_analyze_normalizes_provider_failures(error: Exception, message: str) -> None:
    service = VisionService(model=FakeModel(FakeStructuredModel(error=error)))

    with pytest.raises(ModelUnavailableError, match=message):
        service.analyze(
            image=ChatImageInput(media_type="image/webp", data="AA=="),
            message="查看图片",
        )


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"parsed": None, "parsing_error": "secret provider response"},
        {"parsed": {"summary": "缺少其他必填字段"}},
    ],
)
def test_analyze_rejects_invalid_structured_responses(result) -> None:
    service = VisionService(model=FakeModel(FakeStructuredModel(result=result)))

    with pytest.raises(ModelUnavailableError, match="视觉模型返回无效结构"):
        service.analyze(
            image=ChatImageInput(media_type="image/jpeg", data="AA=="),
            message="查看图片",
        )


def test_analyze_normalizes_structured_parser_failure() -> None:
    service = VisionService(
        model=FakeModel(
            FakeStructuredModel(error=OutputParserException("sensitive raw output"))
        )
    )

    with pytest.raises(ModelUnavailableError, match="视觉模型返回无效结构"):
        service.analyze(
            image=ChatImageInput(media_type="image/jpeg", data="AA=="),
            message="查看图片",
        )


def test_failure_logs_do_not_include_image_message_or_exception_text(caplog) -> None:
    secret_image = "c2Vuc2l0aXZlLWltYWdlLWJ5dGVz"
    secret_message = "身份证号码和病历内容"
    service = VisionService(
        model=FakeModel(
            FakeStructuredModel(
                error=RuntimeError(
                    f"provider echoed {secret_image} {secret_message} sk-secret-key"
                )
            )
        )
    )

    with caplog.at_level(logging.WARNING, logger="yoko.vision"):
        with pytest.raises(ModelUnavailableError, match="视觉模型调用失败"):
            service.analyze(
                image=ChatImageInput(
                    media_type="image/jpeg",
                    data=secret_image,
                ),
                message=secret_message,
            )

    log_text = caplog.text
    assert "vision_model_failed" in log_text
    assert caplog.records[-1].error_type == "RuntimeError"
    assert secret_image not in log_text
    assert secret_message not in log_text
    assert "sk-secret-key" not in log_text


def test_build_model_uses_frozen_vision_model_and_existing_provider_env(
    monkeypatch,
) -> None:
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(
        "backend.app.services.vision_service.ChatOpenAI",
        FakeChatOpenAI,
    )

    model = VisionService._build_model()

    assert isinstance(model, FakeChatOpenAI)
    assert captured == {
        "model": VISION_MODEL_NAME,
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
        "temperature": 0,
        "max_retries": 1,
        "timeout": 30,
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def test_build_model_requires_supported_provider_and_credentials(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    with pytest.raises(ModelUnavailableError, match="暂不支持视觉模型供应商"):
        VisionService._build_model()

    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(ModelUnavailableError, match="未配置视觉模型 API 凭据"):
        VisionService._build_model()
