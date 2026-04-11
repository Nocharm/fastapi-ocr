"""
[읽기 순서 6/7] app/services/extractor.py

이 파일의 역할:
  PDF 파일을 페이지 단위로 분석해서 텍스트와 표(테이블)를 추출한다.

전략 (Hybrid Extraction):
  각 페이지를 독립적으로 처리한다.
  - 직접 추출(pdfplumber)로 충분한 텍스트를 얻으면 → "direct" 방식 사용
  - 텍스트가 OCR_TEXT_THRESHOLD 미만이면 → pdf2image + Tesseract OCR 폴백

절대 문서 전체를 단일 단위로 처리하지 말 것.
첫 페이지가 임계값을 통과해도 나머지 페이지는 각자 독립적으로 판단한다.

┌─────────────────────────────────────────────────────────┐
│  비유: 음식점의 "PDF 담당 주방"                          │
│                                                         │
│  각 재료(페이지)를 독립적으로 확인:                      │
│    재료가 신선하면(텍스트 충분) → 바로 사용 (direct)     │
│    재료가 부족하면(스캔 이미지) → 다른 방법으로 처리 (OCR)│
│                                                         │
│  한 재료가 상했다고 요리 전체를 버리지 않음.             │
│  나쁜 재료만 따로 기록하고 나머지는 정상 진행.           │
└─────────────────────────────────────────────────────────┘

사용하는 주요 라이브러리:
  pdfplumber  : PDF에서 텍스트/표를 직접 추출 (텍스트 레이어 있는 PDF)
  pdf2image   : PDF 페이지를 이미지로 변환 (스캔 PDF용)
  pytesseract : Tesseract OCR 엔진 파이썬 래퍼 (이미지에서 텍스트 인식)
  cv2 (OpenCV): 이미지 전처리 및 분석 라이브러리
  pandas      : 데이터를 표(DataFrame) 형태로 다루는 라이브러리
"""

import os
import tempfile
from dataclasses import asdict
# asdict : PageResult(dataclass) → dict 변환 (JSON 응답에 필요)

from concurrent.futures import ThreadPoolExecutor, as_completed
# ThreadPoolExecutor : 여러 작업을 동시에 실행하는 스레드 풀.
#   비유: 주방에 요리사를 여러 명 고용해서 각 페이지를 동시에 처리하는 것.
#
# as_completed : 여러 Future 중 먼저 완료된 것부터 순서대로 처리.
#   비유: 여러 요리사가 동시에 일하다가 완성되는 순서대로 내보내는 것.

import cv2
# cv2 (OpenCV) : 이미지 처리 라이브러리.
# OCR 전 이미지 품질 개선(전처리)과 표 영역 감지에 사용.

import numpy as np
# numpy : 이미지를 숫자 배열로 다루는 수치 계산 라이브러리.

import pandas as pd
# pandas : 데이터를 표(DataFrame) 형태로 다루는 라이브러리.
# Tesseract의 image_to_data() 결과를 표로 만들어 신뢰도 필터링에 사용.

import pdfplumber
# pdfplumber : PDF에서 텍스트, 표, 이미지를 추출하는 라이브러리.
# 텍스트 레이어가 있는 "일반 PDF"(워드/한글 등에서 생성한 PDF)에 적합.
# 스캔한 PDF(이미지 PDF)는 텍스트 레이어가 없어서 이 방법으로는 텍스트를 못 읽음.

import pytesseract
# pytesseract : Google의 Tesseract OCR 엔진을 파이썬에서 호출하는 래퍼.
# Tesseract는 이미지에서 텍스트를 인식하는 오픈소스 OCR 엔진.
# 단어별 신뢰도(0~100)를 함께 반환하는 image_to_data()를 주로 사용.

from pdf2image import convert_from_path
# pdf2image : PDF 페이지를 PIL 이미지로 변환하는 라이브러리.
# 스캔 PDF에서 Tesseract OCR을 쓰려면 먼저 PDF→이미지 변환이 필요하다.
# dpi(해상도)가 높을수록 OCR 정확도가 올라가지만 처리 시간도 늘어난다.

from pytesseract import Output
# Output.DICT : image_to_data()의 반환 형식을 딕셔너리로 지정하는 상수.

from app.core.config import (
    CONFIDENCE_THRESHOLDS,  # 신뢰도 등급 기준 딕셔너리 {"high": 80, ...}
    TESSERACT_CONFIG,       # Tesseract CLI 옵션 문자열 "--psm 6 --oem 3 ..."
    TESSERACT_LANG,         # Tesseract 인식 언어 "kor+eng"
    settings,               # 앱 설정 객체 (ocr_text_threshold, ocr_max_workers 등)
)
from app.schemas.ocr import PageResult
# 페이지 단위 OCR 결과 데이터 구조


# ================================================================
# 1. 진입점 — 페이지별 추출 전략 결정
# ================================================================

def extract_page(page, page_num: int, pdf_path: str) -> PageResult:
    """
    단일 페이지 처리. 직접 추출을 먼저 시도하고 부족하면 OCR 폴백.

    Args:
        page    : pdfplumber의 페이지 객체
        page_num: 0-based 페이지 번호
        pdf_path: 원본 PDF 경로 (OCR 폴백 시 이미지 변환에 사용)
    """
    text = page.extract_text() or ""
    # page.extract_text() : PDF 페이지의 텍스트 레이어에서 텍스트를 추출.
    # 텍스트 레이어가 없으면 None을 반환 → or "" 로 빈 문자열로 대체.

    if len(text.strip()) >= settings.ocr_text_threshold:
        # text.strip() : 앞뒤 공백/줄바꿈 제거 후 글자 수 확인
        # settings.ocr_text_threshold = 50 (기본값)
        # 50자 이상이면 "텍스트 레이어에 충분한 내용이 있다" → 직접 추출 사용

        tables = extract_tables_with_fallback(page, page_image=None)
        # 텍스트는 직접 추출했지만 표(테이블)는 별도로 추출
        # page_image=None : 이미지 변환 없이 pdfplumber만 시도

        return PageResult(
            page_num=page_num,
            text=text,
            tables=tables,
            method="direct",    # "직접 추출" 표시
            success=True,
            # confidence, quality_flag 는 기본값(None, "") 유지
            # → 직접 추출은 OCR을 쓰지 않으므로 신뢰도가 없음
        )

    # 텍스트가 부족 → 스캔 PDF로 판단 → OCR 폴백
    image = _convert_page_to_image(pdf_path, page_num)
    # PDF 페이지를 이미지(numpy 배열)로 변환

    ocr_result = ocr_with_confidence(image)
    # 이미지에 전처리 적용 후 Tesseract OCR 실행
    # 반환: {"text": ..., "confidence": ..., "quality_flag": ...}

    tables = extract_tables_with_fallback(page, page_image=image)
    # 텍스트가 부족한 페이지에서 표를 추출 (이미지도 함께 전달)

    return PageResult(
        page_num=page_num,
        text=ocr_result["text"],
        tables=tables,
        method="ocr",                        # "OCR 방식" 표시
        confidence=ocr_result["confidence"],
        quality_flag=ocr_result["quality_flag"],
        success=True,
    )


# ================================================================
# 2. 이미지 품질 평가 및 전처리
# ================================================================

def assess_image_quality(image: np.ndarray) -> float:
    """
    Laplacian 분산으로 이미지 선명도를 측정한다.
    값이 높을수록 선명(OCR 정확도 높음), 낮을수록 흐림.
    """
    # Laplacian(라플라시안)이란?
    #   이미지의 "경계(엣지)"를 감지하는 수학적 연산.
    #   선명한 이미지 = 경계가 뚜렷 = 라플라시안 값이 크게 변함 = 분산이 큼.
    #   흐린 이미지   = 경계가 흐림 = 라플라시안 값 변화 적음 = 분산이 작음.
    #
    # 비유: 사진을 확대했을 때 글자 테두리가 선명하면 품질이 좋은 것.

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    # image.ndim == 3 : 컬러 이미지(채널 3개) → 그레이스케일로 변환
    # image.ndim == 2 : 이미 흑백 → 그대로 사용
    # cv2.COLOR_BGR2GRAY : OpenCV는 기본적으로 BGR 순서 사용 (일반 RGB와 반대)

    return cv2.Laplacian(gray, cv2.CV_64F).var()
    # cv2.CV_64F : 64비트 부동소수점으로 계산 (정밀도 확보)
    # .var() : numpy 배열의 분산(variance) 계산


def adaptive_preprocess(image: np.ndarray) -> np.ndarray:
    """
    전처리 전후 품질을 비교해서 더 나은 버전을 반환한다.
    전처리 후 품질이 원본의 90% 미만이면 원본을 그대로 사용한다.

    무조건 전처리를 적용하면 오히려 품질이 떨어질 수 있으므로
    반드시 비교 후 선택해야 한다.
    """
    # 비유: 사진을 보정하기 전후를 비교해서 더 잘 나온 쪽을 쓰는 것.
    #       무조건 보정한다고 항상 나아지는 게 아님.

    original_quality = assess_image_quality(image)
    # 전처리 전 원본 이미지의 선명도 점수 측정

    processed = _apply_preprocessing(image)
    # 전처리(그레이스케일 → 노이즈 제거 → 이진화) 적용

    if assess_image_quality(processed) >= original_quality * 0.9:
        # 전처리 후 품질이 원본의 90% 이상이면 전처리 결과 사용
        return processed

    return image  # 전처리가 오히려 품질을 낮춘 경우 원본 사용


def _apply_preprocessing(image: np.ndarray) -> np.ndarray:
    """그레이스케일 변환 → 노이즈 제거 → Otsu 이진화."""
    # 전처리의 목적:
    #   OCR이 텍스트를 더 정확하게 인식하도록 이미지를 "깔끔하게" 만드는 것.
    #   스캔 이미지는 노이즈(잡티), 배경 얼룩, 명도 불균일 등이 있을 수 있다.

    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # 컬러(BGR) → 흑백(그레이스케일) 변환
    # OCR은 색상 정보가 필요 없고, 명도(밝기)만 있어도 텍스트를 인식할 수 있다.

    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    # 노이즈 제거 (Non-local Means Denoising 알고리즘)
    # h=10 : 노이즈 제거 강도. 클수록 매끄러워지지만 디테일도 사라짐.
    # 비유: 사진의 잡티(노이즈)를 지우개로 지우는 것.

    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # 이진화(Binarization) : 이미지를 흑(0)과 백(255)으로만 만들기.
    # THRESH_OTSU : 최적 임계값을 자동으로 계산해주는 알고리즘.
    #   비유: "이 밝기 이상은 흰색, 미만은 검정"이라는 기준선을 자동으로 찾는 것.
    # _ : 계산된 임계값 (사용 안 함)

    return binary


# ================================================================
# 3. OCR + 신뢰도 검증
# ================================================================

def ocr_with_confidence(image: np.ndarray) -> dict:
    """
    image_to_string() 단독 사용 금지.
    반드시 image_to_data()로 단어별 신뢰도를 추출하고
    OCR_WORD_CONF_MIN 미만의 단어는 결과에서 제외한다.

    Returns:
        {
            "text":         필터링된 텍스트,
            "confidence":   평균 신뢰도 (0~100),
            "quality_flag": "high" | "medium" | "low" | "very_low",
        }
    """
    # image_to_string() vs image_to_data() 차이:
    #   image_to_string() : 인식된 텍스트만 반환. 신뢰도 정보 없음.
    #   image_to_data()   : 단어별 위치 + 텍스트 + 신뢰도를 모두 반환.
    #
    # 신뢰도가 낮은 단어를 포함하면 오인식이 결과에 섞인다.
    # 비유: 잘 들리지 않는 단어를 억지로 받아 적으면 틀린 내용이 섞이는 것.

    preprocessed = adaptive_preprocess(image)
    # 전처리 적용 (원본과 비교해서 더 나은 쪽 선택)

    data = pytesseract.image_to_data(
        preprocessed,
        lang=TESSERACT_LANG,       # "kor+eng"
        config=TESSERACT_CONFIG,   # "--psm 6 --oem 3 ..."
        output_type=Output.DICT,   # 딕셔너리 형태로 반환
    )
    # image_to_data() 반환값 (딕셔너리):
    #   "text"  : 인식된 단어 목록
    #   "conf"  : 각 단어의 신뢰도 (-1 = 텍스트 영역 아님, 0~100 = 신뢰도)
    #   "left", "top", "width", "height" : 단어 위치/크기

    df = pd.DataFrame(data)
    # 딕셔너리를 pandas DataFrame(표 형태)으로 변환
    # 비유: 엑셀 시트처럼 행(단어)과 열(텍스트, 신뢰도 등)로 정리

    valid = df[df["conf"] != -1]
    # conf == -1 인 행은 텍스트가 아닌 영역(구분선 등)이므로 제외
    # df[조건] : 조건에 맞는 행만 필터링하는 pandas 문법

    avg_conf      = float(valid["conf"].mean()) if not valid.empty else 0.0
    # 유효한 단어들의 신뢰도 평균
    # valid.empty : 유효한 행이 하나도 없으면 0.0 반환 (ZeroDivisionError 방지)

    filtered_text = " ".join(
        valid[valid["conf"] >= settings.ocr_word_conf_min]["text"].tolist()
    )
    # 신뢰도가 ocr_word_conf_min(30) 이상인 단어만 공백으로 연결
    # .tolist() : pandas Series → 파이썬 리스트 변환
    # " ".join([...]) : 리스트를 공백으로 연결해서 하나의 문자열로 만들기

    return {
        "text":         filtered_text,
        "confidence":   round(avg_conf, 2),  # 소수점 2자리 반올림
        "quality_flag": _classify_quality(avg_conf),
    }


def _classify_quality(avg_conf: float) -> str:
    # CONFIDENCE_THRESHOLDS 딕셔너리의 기준값으로 등급 분류
    # config.py에 정의된 {"high": 80, "medium": 60, "low": 40, "very_low": 0}
    if avg_conf >= CONFIDENCE_THRESHOLDS["high"]:   return "high"
    if avg_conf >= CONFIDENCE_THRESHOLDS["medium"]: return "medium"
    if avg_conf >= CONFIDENCE_THRESHOLDS["low"]:    return "low"
    return "very_low"


# ================================================================
# 4. 테이블 추출 — 3단계 폴백
# ================================================================

def extract_tables_with_fallback(page, page_image: np.ndarray | None) -> list[str]:
    """
    3단계 폴백 전략으로 테이블을 추출한다.
    하나라도 결과를 얻으면 이후 단계는 시도하지 않는다.

    Stage 1: pdfplumber (선 있는 표)
    Stage 2: 공백 휴리스틱 (선 없는 텍스트 표)
    Stage 3: 이미지 컨투어 + OCR (스캔된 표, 최후 수단)
    """
    # ---------------------------------------------------------------
    # 폴백(Fallback) 전략:
    #   "방법 A로 시도 → 실패하면 방법 B → 실패하면 방법 C"
    #   비유: 잠긴 문을 열 때 열쇠 → 카드 → 비상키 순서로 시도하는 것
    # ---------------------------------------------------------------

    # Stage 1 — pdfplumber 테이블 추출 (가장 빠르고 정확한 방법)
    try:
        tables = page.extract_tables()
        # 텍스트 레이어에서 표 데이터를 2D 리스트로 추출
        # 예) [["이름", "나이"], ["홍길동", "30"]]
        if tables:
            return [_table_to_markdown(t) for t in tables if t]
            # 각 표를 마크다운 형식으로 변환해서 문자열 리스트로 반환
    except Exception:
        pass  # 실패해도 다음 단계로 진행 (에러를 전파하지 않음)

    # Stage 2 — 공백 패턴으로 텍스트 표 감지 (선 없는 표)
    heuristic = _detect_table_by_whitespace(page.extract_text() or "")
    # 공백이 많은 줄이 연속되면 "정렬된 컬럼(표)이겠구나" 라고 추정
    if heuristic:
        return heuristic

    # Stage 3 — 이미지 기반 컨투어 검출 (스캔된 표, 최후 수단)
    if page_image is None:
        # 직접 추출 페이지는 이미지 없이 호출됨 → Stage 3 스킵
        return []

    results = []
    for region in _detect_table_regions_by_contour(page_image):
        # 이미지에서 사각형 영역(표 후보)을 감지
        y1, y2, x1, x2 = region["y"], region["y2"], region["x"], region["x2"]
        crop = page_image[y1:y2, x1:x2]
        # numpy 배열 슬라이싱으로 표 영역만 잘라냄
        # 비유: 사진에서 표 부분만 오려내는 것

        ocr_text = pytesseract.image_to_string(crop, lang=TESSERACT_LANG)
        # 잘라낸 영역에 Tesseract OCR 적용
        results.append(f"<!-- OCR table -->\n{ocr_text}")
        # HTML 주석으로 "이 표는 OCR로 추출됐다"는 표시를 붙임

    return results


def _table_to_markdown(table: list) -> str:
    """pdfplumber 테이블(2차원 리스트)을 마크다운 표로 변환."""
    # pdfplumber 반환 형식:
    #   [["이름", "나이"], ["홍길동", "30"], ["김철수", "25"]]
    #
    # 마크다운 표 형식:
    #   | 이름 | 나이 |
    #   | --- | --- |
    #   | 홍길동 | 30 |
    #   | 김철수 | 25 |

    if not table or not table[0]:
        return ""  # 빈 테이블이면 빈 문자열 반환

    header    = "| " + " | ".join(str(c or "") for c in table[0]) + " |"
    # 첫 번째 행 = 헤더. str(c or "") : None이면 빈 문자열로 처리.

    separator = "| " + " | ".join("---" for _ in table[0]) + " |"
    # 헤더와 본문을 구분하는 마크다운 구분선. 컬럼 수만큼 "---" 반복.

    rows      = [
        "| " + " | ".join(str(c or "") for c in row) + " |"
        for row in table[1:]   # 첫 번째 행(헤더)을 제외한 나머지
    ]

    return "\n".join([header, separator] + rows)
    # 모든 행을 줄바꿈으로 연결해서 하나의 마크다운 표 문자열로 반환


def _detect_table_by_whitespace(text: str) -> list[str]:
    """
    공백 패턴으로 텍스트 표를 감지하는 휴리스틱.
    연속된 공백(2개 이상)이 많은 줄이 3줄 이상 연속되면 표로 간주한다.
    """
    # 휴리스틱(Heuristic) : 완벽한 공식 없이 경험적 규칙으로 추정하는 방법.
    #
    # 예시:
    #   "홍길동  30  서울"  → 공백 2개 이상 포함 → 표 행 후보
    #   "김철수  25  부산"  → 공백 2개 이상 포함 → 표 행 후보
    #   "이 사람은 ..."   → 공백 1개만 → 일반 문장 → 구분선

    lines = text.splitlines()   # 텍스트를 줄 단위로 분리
    table_lines: list[str] = []  # 현재 수집 중인 표 행들
    result: list[str] = []       # 최종 반환할 표 목록

    for line in lines:
        if "  " in line:  # 연속 공백 2개 이상 = 컬럼 구분자 가능성
            table_lines.append(line)
        else:
            if len(table_lines) >= 3:
                # 3줄 이상 연속으로 공백 패턴이 있어야 표로 인정
                result.append("\n".join(table_lines))
            table_lines = []  # 다음 표 후보를 위해 초기화

    # 마지막 줄까지 처리 후 남은 표 후보 처리
    if len(table_lines) >= 3:
        result.append("\n".join(table_lines))

    return result


def _detect_table_regions_by_contour(image: np.ndarray) -> list[dict]:
    """
    컨투어 검출로 표 영역 후보를 찾는다.
    면적이 전체 이미지의 1% 이상인 직사각형 영역만 반환한다.
    """
    # 컨투어(Contour) : 이미지에서 같은 색/밝기의 경계를 따라 만들어지는 윤곽선.
    # 표의 선(테두리)이 이진화 이미지에서 검은색 영역으로 나타나므로
    # 그 윤곽을 감지해서 표 영역의 좌표를 얻는다.
    #
    # 비유: 사진에서 직사각형 영역을 자동으로 찾아내는 것.

    gray    = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    # THRESH_BINARY_INV : 반전 이진화 (밝은 배경 → 검정, 어두운 선 → 흰색)
    # 컨투어 감지는 "흰 물체"를 찾으므로 반전이 필요한 경우가 있음

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # findContours() : 이진화 이미지에서 모든 윤곽선 검출
    # RETR_EXTERNAL  : 가장 바깥쪽 윤곽선만 검출 (내부 중첩 제외)
    # CHAIN_APPROX_SIMPLE : 직선 부분의 중간 점을 제거해 저장 공간 절약

    h, w = image.shape[:2]
    # image.shape = (높이, 너비, 채널수)
    # [:2] : 높이(h)와 너비(w)만 가져옴

    min_area = h * w * 0.01  # 이미지 전체 면적의 1%
    # 너무 작은 영역(노이즈, 글자 테두리 등)을 표 후보에서 제외

    regions = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        # boundingRect() : 윤곽선을 감싸는 최소 직사각형의 좌표와 크기 반환
        # x, y : 왼쪽 상단 좌표 / cw, ch : 너비, 높이

        if cw * ch >= min_area:
            # 최소 면적 이상인 영역만 표 후보로 추가
            regions.append({"x": x, "y": y, "x2": x + cw, "y2": y + ch})
            # x2 = 오른쪽 끝 x좌표, y2 = 아래쪽 끝 y좌표

    return regions


# ================================================================
# 5. 페이지별 에러 격리 — 순차 처리
# ================================================================

def extract_all_pages(pdf_path: str) -> dict:
    """
    PDF 전체를 순차적으로 처리한다.
    한 페이지의 실패가 전체 작업을 중단시켜선 안 된다.
    모든 페이지를 처리하고 실패는 PageResult.success=False로 기록한다.
    """
    # 순차 처리 : 페이지 1 → 페이지 2 → 페이지 3 ... 순서대로 처리
    # 병렬 처리(extract_parallel)보다 느리지만 단순하고 안정적.
    # 소규모 PDF에는 이 방식이 더 적합할 수 있다.

    results: list[PageResult] = []

    with pdfplumber.open(pdf_path) as pdf:
        # pdfplumber.open() : PDF 파일 열기
        # with 블록 : 사용 후 자동으로 파일 닫기 (메모리 누수 방지)

        for page_num, page in enumerate(pdf.pages):
            # enumerate() : 인덱스(0, 1, 2...)와 값을 함께 순회
            try:
                results.append(extract_page(page, page_num, pdf_path))
            except Exception as e:
                # 개별 페이지 에러를 잡아서 기록하고 계속 진행
                # 전체 작업을 중단시키지 않는 "에러 격리" 패턴
                results.append(
                    PageResult(page_num=page_num, error=str(e), success=False)
                    # str(e) : 예외 객체를 에러 메시지 문자열로 변환
                )

    return _build_response(results)


# ================================================================
# 6. 병렬 처리 — 대용량 PDF용
# ================================================================

def extract_parallel(pdf_path: str) -> dict:
    """
    페이지를 ThreadPoolExecutor로 병렬 처리한다.
    OMP_THREAD_LIMIT=1 이 설정되어 있어야 Tesseract 내부 스레드와 충돌하지 않는다.
    (config.py 임포트 시 자동으로 설정됨)

    페이지가 적은 문서에서는 순차 처리(extract_all_pages)가 더 빠를 수 있다.
    """
    # ThreadPoolExecutor (스레드 풀 실행기):
    #
    # 비유: 여러 요리사를 고용해서 각 페이지를 동시에 처리하는 것.
    #   요리사 1명(순차처리) : 페이지1 → 페이지2 → 페이지3
    #   요리사 4명(병렬처리) : 페이지1, 2, 3, 4 를 동시에 처리
    #
    # max_workers : 동시에 실행할 스레드(요리사) 수
    # settings.ocr_max_workers : 기본값 4

    with pdfplumber.open(pdf_path) as pdf:
        pages = list(pdf.pages)
        # list() : pdfplumber의 페이지 이터레이터를 리스트로 변환
        # with 블록 안에서 pages를 미리 리스트로 변환해야
        # with 블록 밖에서도 페이지 객체를 참조할 수 있다.

    results: list[PageResult | None] = [None] * len(pages)
    # 결과를 페이지 번호 순서대로 저장하기 위한 리스트
    # [None, None, None, ...] 로 초기화 → 나중에 results[i] = 결과 로 채움
    # 병렬 처리는 순서 보장이 없으므로 인덱스로 관리

    with ThreadPoolExecutor(max_workers=settings.ocr_max_workers) as executor:
        futures = {
            executor.submit(_process_page_safe, page, i, pdf_path): i
            for i, page in enumerate(pages)
        }
        # executor.submit(함수, 인자...) : 스레드 풀에 작업을 제출
        # Future : 아직 완료되지 않은 비동기 작업의 "영수증" 같은 객체
        # futures = {Future: 페이지번호} 딕셔너리

        for future in as_completed(futures):
            # as_completed() : 완료된 Future부터 순서대로 반환
            i = futures[future]  # 이 Future가 몇 번 페이지인지 확인
            try:
                results[i] = future.result()
                # future.result() : 작업이 완료될 때까지 기다렸다가 반환값 가져오기
            except Exception as e:
                results[i] = PageResult(page_num=i, error=str(e), success=False)
                # 해당 페이지만 실패 처리, 다른 페이지는 계속 진행

    return _build_response([r for r in results if r is not None])
    # None이 아닌 결과만 모아서 응답 생성


def _process_page_safe(page, page_num: int, pdf_path: str) -> PageResult:
    """병렬 처리 시 단일 페이지 래퍼 — 예외를 호출자에게 전파한다."""
    return extract_page(page, page_num, pdf_path)
    # 이 함수가 별도로 있는 이유:
    #   executor.submit()에 직접 extract_page를 넘겨도 되지만
    #   래퍼 함수를 두면 나중에 전처리/후처리 로직을 추가하기 쉽다.


# ================================================================
# 내부 유틸
# ================================================================

def _convert_page_to_image(pdf_path: str, page_num: int) -> np.ndarray:
    """PDF 특정 페이지를 numpy 배열(BGR)로 변환."""
    images = convert_from_path(
        pdf_path,
        first_page=page_num + 1,  # pdf2image는 1-based 페이지 번호 사용
        last_page=page_num + 1,   # (0-based인 page_num에 +1 필요)
        dpi=300,
        # dpi(dots per inch) : 이미지 해상도.
        # 300 dpi = 고해상도 스캔 수준 → OCR 정확도 높음
        # 72 dpi = 화면 표시 수준 → OCR 정확도 낮음
    )
    return cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2BGR)
    # PIL Image → numpy 배열 변환 후 RGB → BGR 변환
    # PIL은 RGB 순서를 사용하지만 OpenCV(cv2)는 BGR 순서를 사용함


def _build_response(results: list[PageResult]) -> dict:
    """PageResult 목록을 API 응답 dict로 변환."""
    # 이 dict가 routes/ocr.py에서 **result 로 언패킹되어
    # OCRResponse(filename=..., **result) 형태로 사용된다.
    return {
        "pages":         [asdict(r) for r in results],
        # asdict() : PageResult dataclass → dict 변환 (JSON 직렬화 가능)

        "total":         len(results),
        # 전체 페이지 수

        "success_count": sum(1 for r in results if r.success),
        # 성공한 페이지 수 (success=True 인 것만 합산)
        # sum(1 for ...) : 조건에 맞는 항목마다 1씩 더하는 제너레이터 표현식

        "failed_pages":  [r.page_num for r in results if not r.success],
        # 실패한 페이지 번호 목록 (success=False 인 것만 수집)
    }
