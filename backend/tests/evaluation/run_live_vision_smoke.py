from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from backend.app.schemas import ChatImageInput
from backend.app.services.errors import ModelUnavailableError
from backend.app.services.vision_service import VISION_MODEL_NAME, VisionService


MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one explicitly enabled, billable vision-model smoke check."
    )
    parser.add_argument("image", type=Path, help="Local JPEG, PNG, or WebP image")
    parser.add_argument(
        "--message",
        default="请简要说明图片中的主要内容和可见文字。",
        help="Text sent with the image",
    )
    args = parser.parse_args()

    if os.getenv("YOKO_RUN_LIVE_VISION_SMOKE") != "1":
        print("未执行：请先显式设置 YOKO_RUN_LIVE_VISION_SMOKE=1。")
        return 2

    load_dotenv()
    suffix = args.image.suffix.lower()
    media_type = MEDIA_TYPES.get(suffix)
    if media_type is None:
        print("仅支持 .jpg、.jpeg、.png 和 .webp。")
        return 2

    image_bytes = args.image.read_bytes()
    image = ChatImageInput(
        media_type=media_type,
        data=base64.b64encode(image_bytes).decode("ascii"),
        detail="original",
    )
    try:
        observation = VisionService().analyze(image=image, message=args.message)
    except ModelUnavailableError:
        print("真实视觉模型冒烟失败：模型服务暂不可用，请检查配置后重试。")
        return 1

    # Do not print extracted text or the image payload. The smoke output is
    # intentionally limited to structural acceptance evidence.
    print(
        json.dumps(
            {
                "model": VISION_MODEL_NAME,
                "media_type": media_type,
                "image_bytes": len(image_bytes),
                "confidence": observation.confidence,
                "visible_text_count": len(observation.visible_text),
                "possible_date_count": len(observation.possible_dates),
                "warning_count": len(observation.warnings),
                "medical_content": observation.medical_content,
                "instruction_like_text": observation.instruction_like_text,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
