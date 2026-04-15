"""app/services/vlm.py — VLM 엔진 인터페이스.

현재 구현: OpenAI GPT-4V (gpt-4o).
로컬 Qwen 모델로 전환 시 run_vlm() 내부만 교체한다. 호출부 수정 불필요.
"""
import base64

import cv2
import numpy as np

from app.core.config import settings

# 신뢰도 100에 대응하는 텍스트 길이 상한 (문자 수)
# 실제 문서는 수백~수천 자이므로 500자를 넘으면 충분히 추출된 것으로 간주한다.
VLM_CONF_TEXT_LIMIT = 500

_OCR_SYSTEM_PROMPT = (
    "You are an OCR engine. Extract all text from the image exactly as it appears.\n"
    "- Preserve the original layout, line breaks, and spacing.\n"
    "- Support Korean and English text.\n"
    "- Accurately transcribe numbers, symbols, and table content.\n"
    "- Output only the extracted text. No explanations, no markdown formatting."
)


def run_vlm(image: np.ndarray) -> dict:
    """GPT-4V로 이미지에서 텍스트 추출.

    Returns:
        {"text": str, "confidence": float, "quality_flag": str}
        — run_ocr()과 동일한 키 구조.

    API 키 미설정 시 NotImplementedError → 호출부에서 Tesseract 결과 유지.
    API 오류는 예외를 그대로 전파 → 호출부(except Exception)에서 Tesseract 폴백.
    """
    if not settings.openai_api_key:
        raise NotImplementedError("OPENAI_API_KEY가 설정되지 않아 VLM을 사용할 수 없습니다.")

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)

    # BGR numpy 배열 → PNG bytes → base64 (OpenCV는 BGR, OpenAI는 RGB 무관하게 PNG로 전송)
    _, buf = cv2.imencode(".png", image)
    b64_image = base64.b64encode(buf.tobytes()).decode("utf-8")

    response = client.chat.completions.create(
        model=settings.vlm_model,
        messages=[
            {"role": "system", "content": _OCR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                    }
                ],
            },
        ],
        max_tokens=settings.vlm_max_tokens,
    )

    text = response.choices[0].message.content or ""
    confidence = _get_vlm_confidence(text)

    return {
        "text": text,
        "confidence": round(confidence, 2),
        "quality_flag": _get_quality_flag(confidence),
    }


def _get_vlm_confidence(text: str) -> float:
    """텍스트 길이를 0~100 신뢰도로 선형 매핑.

    VLM_CONF_TEXT_LIMIT 이상이면 100.0으로 고정.
    GPT-4V는 단어별 신뢰도를 반환하지 않으므로 텍스트 길이로 근사한다.
    """
    return min(len(text) / VLM_CONF_TEXT_LIMIT * 100, 100.0)


def _get_quality_flag(confidence: float) -> str:
    """신뢰도 점수를 quality_flag 문자열로 변환. extractor._get_quality_flag()와 동일한 임계값."""
    ct = settings.confidence_thresholds
    if confidence >= ct["high"]:   return "high"
    if confidence >= ct["medium"]: return "medium"
    if confidence >= ct["low"]:    return "low"
    return "very_low"
