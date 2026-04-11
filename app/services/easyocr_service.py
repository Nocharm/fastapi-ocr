"""
[읽기 순서 5/7] app/services/easyocr_service.py

이 파일의 역할:
  이미지 파일을 받아서 EasyOCR로 텍스트를 추출하고
  extractor.py의 응답 형식(pages/total/success_count/failed_pages)과
  통일된 dict를 반환한다.

┌─────────────────────────────────────────────────────────┐
│  비유: 음식점의 "이미지 담당 주방"                       │
│                                                         │
│  홀 직원(routes/ocr.py)이 "이미지 주문이요!" 라고 하면  │
│  이 주방이 받아서:                                      │
│   1. 이미지를 OCR이 이해할 수 있는 형태로 변환          │
│   2. EasyOCR로 텍스트 인식                              │
│   3. 신뢰도 필터링 후 결과를 표준 형식으로 포장해서 반환│
│                                                         │
│  PDF 주방(extractor.py)과 응답 형식을 일치시켜          │
│  라우터가 두 종류를 동일하게 처리할 수 있게 한다.       │
└─────────────────────────────────────────────────────────┘
"""

import io
# io : 바이트 데이터를 파일처럼 다루는 파이썬 표준 라이브러리.
# 디스크에 파일을 저장하지 않고 메모리에서 파일처럼 동작시킬 때 사용.

from dataclasses import asdict
# asdict : dataclass 객체를 딕셔너리로 변환하는 함수.
# 예) asdict(PageResult(page_num=0, text="안녕")) → {"page_num": 0, "text": "안녕", ...}
# JSON 응답에서는 딕셔너리가 필요하므로 변환이 필요하다.

import easyocr
# EasyOCR : 딥러닝 기반 이미지 텍스트 인식 라이브러리.
# 한국어, 영어 등 80개 이상의 언어를 지원한다.

import numpy as np
# numpy : 수치 계산 라이브러리. 이미지를 숫자 배열(행렬)로 다룰 때 사용.
# 이미지를 픽셀값의 2D/3D 배열로 표현:
#   흑백 이미지 → shape (높이, 너비)
#   컬러 이미지 → shape (높이, 너비, 3)  ← 3 = R, G, B 채널

from fastapi import UploadFile
# 타입 힌트를 위한 import

from PIL import Image
# PIL (Pillow) : 이미지 파일을 열고, 변환하고, 저장하는 라이브러리.
# EasyOCR은 numpy 배열을 입력으로 받으므로
# PIL로 이미지를 열고 np.array()로 변환하는 중간 단계가 필요하다.

from app.core.config import settings
# settings.easyocr_languages : 인식할 언어 목록
# settings.ocr_word_conf_min : 최소 신뢰도 기준값 (0~100)

from app.schemas.ocr import PageResult
# OCR 결과를 담는 페이지 단위 데이터 구조

# ---------------------------------------------------------------
# 싱글턴 패턴 (Singleton Pattern)
#
# 비유: "EasyOCR 모델이 현재 메모리에 올라가 있는가?" 를 기록하는 칠판
#   None   → 아직 로딩 전
#   Reader → 이미 로딩됨 (재사용 가능)
#
# 모델 로딩은 수 초~수십 초가 걸리고, 파일 크기도 수백 MB다.
# 매 요청마다 새로 로딩하면 서버가 느려지므로
# 최초 1회만 로딩하고 이후에는 그 객체를 재사용한다.
# ---------------------------------------------------------------
_reader = None


def get_reader() -> easyocr.Reader:
    # -> easyocr.Reader : 이 함수의 반환 타입 힌트
    global _reader
    # global : 함수 안에서 함수 밖의 _reader 변수를 수정하겠다는 선언.
    # 선언하지 않으면 함수 안에서 새 지역 변수로 취급되어 밖의 _reader가 바뀌지 않는다.

    if _reader is None:
        # 모델이 아직 메모리에 없을 때만 새로 로딩
        _reader = easyocr.Reader(settings.easyocr_languages, gpu=False)
        # gpu=False : CPU만 사용. Docker 기본 환경에는 GPU가 없으므로 CPU 모드.
        #             GPU가 있다면 True로 바꾸면 10배 이상 빠름.

    return _reader
    # 이미 로딩된 Reader를 반환 (두 번째 요청부터는 if 조건이 False라 바로 여기로 옴)


async def extract_image(file: UploadFile) -> dict:
    """
    이미지 파일에서 텍스트를 추출하고 OCRResponse 호환 dict를 반환.

    이미지는 단일 페이지로 취급해 extractor.py의 응답 형식과 통일한다:
        { pages, total, success_count, failed_pages }
    """
    # ---------------------------------------------------------------
    # 처리 흐름:
    #   bytes → PIL Image (RGB) → numpy 배열 → EasyOCR → 필터링 → dict
    # ---------------------------------------------------------------

    contents = await file.read()
    # await : 파일을 비동기로 읽음. 읽는 동안 다른 요청도 처리 가능.

    image    = Image.open(io.BytesIO(contents)).convert("RGB")
    # io.BytesIO(contents) : bytes를 메모리 안의 "가상 파일"로 포장.
    #   PIL.Image.open()이 파일 객체를 기대하기 때문에 필요.
    # .convert("RGB") : 이미지를 RGB 모드로 통일.
    #   PNG는 투명도(RGBA), 스캔 문서는 흑백(L)일 수 있어서 통일이 필요.

    img_array = np.array(image)
    # PIL Image → numpy 배열 변환.
    # EasyOCR의 readtext()는 numpy 배열을 입력으로 받는다.

    reader  = get_reader()         # 싱글턴 Reader 가져오기
    results = reader.readtext(img_array)
    # readtext() 반환값: [(바운딩박스, 텍스트, 신뢰도), ...]
    # 예) [([[10,5],[100,5],[100,20],[10,20]], "Hello", 0.97), ...]

    text, confidence = _parse_results(results)
    # 신뢰도 필터링 후 텍스트 문자열과 평균 신뢰도 추출

    page = PageResult(
        page_num=0,              # 이미지는 단일 페이지 → 0번
        text=text,
        method="ocr",            # 이미지는 항상 OCR 방식
        confidence=confidence,
        quality_flag=_classify_quality(confidence),
        success=True,
    )

    # dataclass → dict 변환 후 OCRResponse 호환 구조로 포장
    return {
        "pages":         [asdict(page)],
        # asdict : PageResult를 JSON 직렬화 가능한 딕셔너리로 변환
        "total":         1,           # 이미지는 항상 1페이지
        "success_count": 1,
        "failed_pages":  [],
    }


def _parse_results(results: list) -> tuple[str, float]:
    """
    EasyOCR 결과에서 신뢰도 필터링 후 텍스트와 평균 신뢰도를 반환.

    EasyOCR 반환 형식: [(바운딩박스, 텍스트, 신뢰도), ...]
    신뢰도는 0.0~1.0 범위 → Tesseract와 맞추기 위해 0~100으로 변환.

    함수 이름 앞의 _ (언더스코어):
        이 파일 내부에서만 쓰는 비공개 함수라는 관례적 표시.
    """
    threshold = settings.ocr_word_conf_min / 100
    # settings.ocr_word_conf_min 은 0~100 기준 (예: 30)
    # EasyOCR 신뢰도는 0.0~1.0 기준이므로 100으로 나눠서 맞춤
    # 예) 30 / 100 = 0.3 → 신뢰도 0.3 미만은 제외

    valid = [(text, conf) for (_, text, conf) in results if conf >= threshold]
    # 리스트 컴프리헨션 + 튜플 언패킹:
    #   (_, text, conf) : 바운딩박스(_)는 필요 없으므로 버림
    #   if conf >= threshold : 기준 미만은 제외

    if not valid:
        # 모든 결과가 기준 미달이면 빈 텍스트와 0 신뢰도 반환
        return "", 0.0

    text       = "\n\n".join(t for t, _ in valid)
    # "\n\n" : 마크다운의 단락 구분. 각 인식 텍스트를 빈 줄로 구분.

    avg_conf   = round(sum(c for _, c in valid) / len(valid) * 100, 2)
    # 유효한 텍스트들의 평균 신뢰도를 계산.
    # * 100 : EasyOCR(0.0~1.0) → Tesseract 기준(0~100)으로 변환
    # round(..., 2) : 소수점 2자리로 반올림. 예) 91.333... → 91.33

    return text, avg_conf


def _classify_quality(avg_conf: float) -> str:
    """Tesseract 기준(0~100)과 동일한 품질 등급 분류."""
    # config.py의 CONFIDENCE_THRESHOLDS와 동일한 기준을 사용
    if avg_conf >= 80: return "high"
    if avg_conf >= 60: return "medium"
    if avg_conf >= 40: return "low"
    return "very_low"
