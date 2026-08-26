from __future__ import annotations

import base64
import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from backend.app.schemas import ChatImageInput
from backend.app.services.errors import InvalidRequestError


MAX_IMAGE_DIMENSION = 8192
MAX_IMAGE_PIXELS = 25_000_000
MEDIA_TYPE_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


@dataclass(frozen=True)
class ValidatedChatImage:
    sha256: str
    width: int
    height: int
    media_type: str


def validate_chat_image(image_input: ChatImageInput) -> ValidatedChatImage:
    raw = base64.b64decode(image_input.data, validate=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                actual_media_type = MEDIA_TYPE_BY_FORMAT.get(image.format or "")
                if actual_media_type is None:
                    raise InvalidRequestError("不支持的图片格式")
                if actual_media_type != image_input.media_type:
                    raise InvalidRequestError("图片内容与声明格式不一致")
                width, height = image.size
                if width < 1 or height < 1:
                    raise InvalidRequestError("图片尺寸无效")
                if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                    raise InvalidRequestError("图片尺寸超过限制")
                if width * height > MAX_IMAGE_PIXELS:
                    raise InvalidRequestError("图片像素总量超过限制")
                if getattr(image, "is_animated", False) or getattr(
                    image, "n_frames", 1
                ) != 1:
                    raise InvalidRequestError("暂不支持动态图")
                image.verify()
    except InvalidRequestError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise InvalidRequestError("图片文件损坏或无法识别") from exc

    return ValidatedChatImage(
        sha256=hashlib.sha256(raw).hexdigest(),
        width=width,
        height=height,
        media_type=actual_media_type,
    )
