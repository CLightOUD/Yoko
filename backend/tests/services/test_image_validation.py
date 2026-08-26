from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from backend.app.schemas import ChatImageInput
from backend.app.services.errors import InvalidRequestError
from backend.app.services.image_validation import validate_chat_image


def encoded_image(image_format: str = "PNG", *, size: tuple[int, int] = (2, 3)) -> str:
    output = BytesIO()
    Image.new("RGB", size, color="white").save(output, format=image_format)
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_validate_chat_image_checks_real_content_and_returns_safe_metadata() -> None:
    validated = validate_chat_image(
        ChatImageInput(media_type="image/png", data=encoded_image())
    )

    assert validated.media_type == "image/png"
    assert (validated.width, validated.height) == (2, 3)
    assert len(validated.sha256) == 64


def test_validate_chat_image_rejects_declared_type_mismatch_and_corruption() -> None:
    with pytest.raises(InvalidRequestError, match="声明格式"):
        validate_chat_image(
            ChatImageInput(media_type="image/jpeg", data=encoded_image("PNG"))
        )

    with pytest.raises(InvalidRequestError, match="损坏或无法识别"):
        validate_chat_image(ChatImageInput(media_type="image/png", data="AA=="))


def test_validate_chat_image_rejects_excessive_dimensions() -> None:
    with pytest.raises(InvalidRequestError, match="尺寸超过限制"):
        validate_chat_image(
            ChatImageInput(
                media_type="image/png",
                data=encoded_image(size=(8193, 1)),
            )
        )
