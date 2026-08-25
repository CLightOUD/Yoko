from __future__ import annotations

from backend.app.schemas import ChatImageInput
from backend.app.services.vision_contract import VisionAnalyzer, VisionObservation


class StubVisionAnalyzer:
    def analyze(
        self,
        *,
        image: ChatImageInput,
        message: str,
    ) -> VisionObservation:
        return VisionObservation(
            summary=f"已分析：{message}",
            visible_text=["每日一次"],
            possible_dates=[],
            confidence=0.8,
            warnings=["药品名称不清晰"],
            medical_content=True,
            instruction_like_text=False,
        )


def test_vision_analyzer_contract_is_runtime_checkable() -> None:
    analyzer = StubVisionAnalyzer()
    image = ChatImageInput(media_type="image/jpeg", data="AA==")

    assert isinstance(analyzer, VisionAnalyzer)
    observation = analyzer.analyze(image=image, message="看看这个药盒")
    assert observation.confidence == 0.8
    assert observation.medical_content is True
    assert observation.visible_text == ["每日一次"]
