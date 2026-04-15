"""VLM 엔진 인터페이스.

로컬 모델(LLaVA, Qwen-VL 등) 연동 예정.
모델 연결 시 run_vlm() 내부만 교체한다. 호출부 수정 불필요.
"""
import numpy as np


def run_vlm(image: np.ndarray) -> dict:
    """VLM으로 이미지에서 텍스트 추출.

    Returns:
        {"text": str, "confidence": float, "quality_flag": str}
        — run_ocr()과 동일한 키 구조.

    로컬 모델 연동 전까지 NotImplementedError 발생.
    호출부(run_ocr_with_fallback)가 이를 잡아 Tesseract 결과로 폴백한다.
    """
    raise NotImplementedError
