"""
app/services/extractor.py

PDF 파일을 페이지 단위로 분석해서 텍스트와 표를 추출한다.

전략 (Hybrid Extraction):
  페이지마다 독립적으로 판단한다.
  - pdfplumber 추출 텍스트 ≥ ocr_text_threshold → "direct" 방식
  - 텍스트 부족 → pdf2image + Tesseract OCR 폴백 → "ocr" 방식

절대 문서 전체를 단일 단위로 처리하지 말 것.
첫 페이지가 임계값을 통과해도 나머지 페이지는 각자 독립적으로 판단한다.
"""

import logging
import traceback
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np
import pandas as pd
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from pytesseract import Output

from app.core.config import settings
from app.schemas.ocr import PageResult
from app.services.vlm import run_vlm

logger = logging.getLogger(__name__)


# --- 1. 진입점 — 페이지별 추출 전략 결정 ---

def extract_page(page, page_num: int, pdf_path: str) -> PageResult:
    """
    단일 페이지 처리. 직접 추출을 먼저 시도하고 부족하면 OCR 폴백.

    Args:
        page    : pdfplumber 페이지 객체
        page_num: 0-based 페이지 번호
        pdf_path: 원본 PDF 경로 (OCR 폴백 시 이미지 변환에 사용)
    """
    print(f"[DEBUG] extract_page 시작: page_num={page_num}", flush=True)
    text = page.extract_text() or ""
    print(f"[DEBUG] extract_text 완료: len={len(text)}", flush=True)

    if len(text.strip()) >= settings.ocr_text_threshold:
        tables = extract_tables(page, page_image=None)
        return PageResult(
            page_num=page_num,
            text=text,
            tables=tables,
            method="direct",
            success=True,
        )

    # 텍스트 부족 → 스캔 PDF로 판단 → OCR 폴백
    image      = _get_page_image(pdf_path, page_num)
    ocr_result = run_ocr_with_fallback(image)
    tables     = extract_tables(page, page_image=image)
    method     = "vlm" if ocr_result["engine"] == "vlm" else "ocr"

    return PageResult(
        page_num=page_num,
        text=ocr_result["text"],
        tables=tables,
        method=method,
        confidence=ocr_result["confidence"],
        quality_flag=ocr_result["quality_flag"],
        success=True,
    )


# --- 2. 이미지 품질 평가 및 전처리 ---

def get_image_quality(image: np.ndarray) -> float:
    """
    Laplacian 분산으로 이미지 선명도를 측정한다.
    값이 높을수록 선명 (OCR 정확도 높음), 낮을수록 흐림.

    Laplacian: 이미지의 경계(엣지)를 감지하는 2차 미분 연산.
    선명한 이미지는 경계가 뚜렷해 분산이 크고, 흐린 이미지는 분산이 작다.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    # image.ndim == 3: 컬러(BGR) → 그레이스케일 변환
    # image.ndim == 2: 이미 흑백 → 그대로 사용
    # OpenCV는 기본적으로 BGR 채널 순서를 사용한다 (일반 RGB와 반대).
    return cv2.Laplacian(gray, cv2.CV_64F).var()
    # cv2.CV_64F: 64비트 부동소수점으로 계산해 정밀도 확보


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    전처리 전후 품질을 비교해서 더 나은 버전을 반환한다.
    전처리 후 품질이 원본의 90% 미만이면 원본을 그대로 사용한다.

    무조건 전처리를 적용하면 오히려 품질이 떨어질 수 있으므로
    반드시 비교 후 선택한다.
    """
    original_quality = get_image_quality(image)
    processed        = _run_image_filters(image)

    if get_image_quality(processed) >= original_quality * 0.9:
        return processed
    return image


def _run_image_filters(image: np.ndarray) -> np.ndarray:
    """그레이스케일 변환 → 노이즈 제거 → Otsu 이진화."""
    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    # h=10: 노이즈 제거 강도. 클수록 매끄러워지지만 디테일도 사라짐.

    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu 이진화: 히스토그램 분석으로 흑/백 분리 최적 임계값을 자동 계산한다.
    # 수동으로 임계값을 지정하지 않아도 이미지 밝기 분포에 맞게 적응한다.
    # _ : 계산된 임계값 (이후 사용 불필요)
    return binary


# --- 3. OCR + 신뢰도 검증 ---

def run_ocr(image: np.ndarray) -> dict:
    """
    image_to_string() 단독 사용 금지.
    반드시 image_to_data()로 단어별 신뢰도를 추출하고
    ocr_word_conf_min 미만의 단어는 결과에서 제외한다.

    image_to_string() vs image_to_data():
      string: 인식된 텍스트만 반환, 신뢰도 정보 없음.
      data  : 단어별 위치 + 텍스트 + 신뢰도(0~100) 반환.

    Returns:
        {"text": str, "confidence": float, "quality_flag": str}
    """
    preprocessed = preprocess_image(image)

    data = pytesseract.image_to_data(
        preprocessed,
        lang=settings.tesseract_lang,
        config=settings.tesseract_config,
        output_type=Output.DICT,
    )

    df    = pd.DataFrame(data)
    valid = df[df["conf"] != -1]
    # conf == -1: Tesseract가 텍스트 외 영역(구분선, 여백 등)에 반환하는 값. 제외한다.

    avg_conf = float(valid["conf"].mean()) if not valid.empty else 0.0

    filtered_text = " ".join(
        valid[valid["conf"] >= settings.ocr_word_conf_min]["text"].tolist()
    )

    return {
        "text":         filtered_text,
        "confidence":   round(avg_conf, 2),
        "quality_flag": _get_quality_flag(avg_conf),
    }


def _get_quality_flag(avg_conf: float) -> str:
    """신뢰도 점수를 등급 문자열로 변환."""
    ct = settings.confidence_thresholds
    if avg_conf >= ct["high"]:   return "high"
    if avg_conf >= ct["medium"]: return "medium"
    if avg_conf >= ct["low"]:    return "low"
    return "very_low"


def run_ocr_with_fallback(image: np.ndarray) -> dict:
    """Tesseract 먼저 시도. quality_flag가 vlm_fallback_flags에 해당하면 VLM 재시도.

    VLM 실패(API 오류, 미구현 등) 시 Tesseract 결과를 그대로 반환.

    Returns:
        run_ocr() / run_vlm() 반환값에 "engine" 키 추가:
        {"text": str, "confidence": float, "quality_flag": str, "engine": "tesseract"|"vlm"}
    """
    result = run_ocr(image)
    result["engine"] = "tesseract"
    if result["quality_flag"] in settings.vlm_fallback_flags:
        try:
            vlm_result = run_vlm(image)
            vlm_result["engine"] = "vlm"
            return vlm_result
        except Exception:
            # NotImplementedError(API 키 미설정)뿐 아니라 API 오류도 Tesseract 결과로 폴백한다.
            pass
    return result


# --- 4. 테이블 추출 — 3단계 폴백 ---

def extract_tables(page, page_image: np.ndarray | None) -> list[str]:
    """
    3단계 폴백 전략으로 테이블을 추출한다.
    하나라도 결과를 얻으면 이후 단계는 시도하지 않는다.

    Stage 1: pdfplumber     — 선 있는 표 (가장 빠르고 정확)
    Stage 2: 공백 휴리스틱  — 선 없는 텍스트 표
    Stage 3: 컨투어 + OCR  — 스캔된 표 (최후 수단)
    """
    # Stage 1
    try:
        tables = page.extract_tables()
        if tables:
            return [_make_markdown_table(t) for t in tables if t]
    except Exception:
        pass

    # Stage 2
    heuristic = _find_tables_by_whitespace(page.extract_text() or "")
    if heuristic:
        return heuristic

    # Stage 3: page_image가 없으면 (direct 방식 페이지) 스킵
    if page_image is None:
        return []

    results = []
    for region in _find_table_regions(page_image):
        y1, y2, x1, x2 = region["y"], region["y2"], region["x"], region["x2"]
        crop     = page_image[y1:y2, x1:x2]   # 표 영역만 잘라냄
        ocr_text = pytesseract.image_to_string(crop, lang=settings.tesseract_lang)
        results.append(f"<!-- OCR table -->\n{ocr_text}")

    return results


def _make_markdown_table(table: list) -> str:
    """pdfplumber 테이블(2차원 리스트)을 마크다운 표로 변환."""
    if not table or not table[0]:
        return ""

    header    = "| " + " | ".join(str(c or "") for c in table[0]) + " |"
    separator = "| " + " | ".join("---" for _ in table[0]) + " |"
    rows      = [
        "| " + " | ".join(str(c or "") for c in row) + " |"
        for row in table[1:]
    ]
    return "\n".join([header, separator] + rows)


def _find_tables_by_whitespace(text: str) -> list[str]:
    """
    공백 패턴으로 텍스트 표를 감지하는 휴리스틱.
    연속 공백(2개 이상)이 포함된 줄이 3줄 이상 연속되면 표로 간주한다.

    휴리스틱(Heuristic): 완벽한 공식 없이 경험적 규칙으로 추정하는 방법.
    선 없는 텍스트 표는 컬럼 구분을 공백으로 표현하는 경우가 많다.
    """
    lines       = text.splitlines()
    table_lines: list[str] = []
    result:      list[str] = []

    for line in lines:
        if "  " in line:   # 연속 공백 2개 이상 = 컬럼 구분자 가능성
            table_lines.append(line)
        else:
            if len(table_lines) >= 3:
                result.append("\n".join(table_lines))
            table_lines = []

    if len(table_lines) >= 3:
        result.append("\n".join(table_lines))

    return result


def _find_table_regions(image: np.ndarray) -> list[dict]:
    """
    컨투어 검출로 표 영역 후보를 찾는다.
    면적이 전체 이미지의 1% 이상인 직사각형 영역만 반환한다.

    컨투어(Contour): 이미지에서 동일한 밝기 값의 경계를 이어 만든 윤곽선.
    표의 테두리 선이 이진화 이미지에서 경계로 나타나므로 좌표 추출에 활용한다.
    """
    gray      = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    # THRESH_BINARY_INV: 반전 이진화. 컨투어 감지는 "흰 물체"를 찾으므로
    # 어두운 선(표 테두리)을 흰색으로 바꾸기 위해 반전한다.

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # RETR_EXTERNAL   : 가장 바깥쪽 윤곽선만 검출 (내부 중첩 제외)
    # CHAIN_APPROX_SIMPLE: 직선 구간 중간 점 제거로 메모리 절약

    h, w      = image.shape[:2]
    min_area  = h * w * 0.01   # 이미지 전체 면적의 1% 미만은 노이즈로 제외

    regions = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        # boundingRect(): 윤곽선을 감싸는 최소 직사각형의 x, y, 너비, 높이 반환
        if cw * ch >= min_area:
            regions.append({"x": x, "y": y, "x2": x + cw, "y2": y + ch})

    return regions


def extract_image(image: np.ndarray) -> dict:
    """이미지 단건을 OCR 처리해 extract_parallel()과 동일한 형식으로 반환.

    이미지는 단일 "페이지"로 간주해 page_num=0으로 고정한다.
    """
    result = run_ocr_with_fallback(image)
    method = "vlm" if result["engine"] == "vlm" else "ocr"
    page_result = PageResult(
        page_num=0,
        text=result["text"],
        method=method,
        confidence=result["confidence"],
        quality_flag=result["quality_flag"],
        success=True,
    )
    return _make_response([page_result])


# --- 5. 순차 처리 ---

def extract_all_pages(pdf_path: str) -> dict:
    """
    PDF 전체를 순차적으로 처리한다.
    한 페이지의 실패가 전체 작업을 중단시키지 않는다.
    실패는 PageResult.success=False로 기록하고 계속 진행한다.
    """
    results: list[PageResult] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            try:
                results.append(extract_page(page, page_num, pdf_path))
            except Exception as e:
                results.append(
                    PageResult(page_num=page_num, error=str(e), success=False)
                )

    return _make_response(results)


# --- 6. 병렬 처리 — 대용량 PDF용 ---

def extract_parallel(pdf_path: str) -> dict:
    """
    페이지를 ThreadPoolExecutor로 병렬 처리한다.

    주의: pdfplumber 페이지 객체는 파일 스트림을 공유하므로 스레드 간 전달 금지.
    _extract_page_safe()에서 스레드마다 PDF를 독립적으로 열어 경쟁 조건을 방지한다.

    OMP_NUM_THREADS=1이 설정되어 있어야 Tesseract 내부 스레드와 충돌하지 않는다.
    (config.py 임포트 시 자동으로 설정됨)
    """
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)

    results: list[PageResult | None] = [None] * num_pages

    with ThreadPoolExecutor(max_workers=settings.ocr_max_workers) as executor:
        futures = {
            executor.submit(_extract_page_safe, pdf_path, i): i
            for i in range(num_pages)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as e:
                print(f"[ERROR] page {i} 처리 실패:\n{traceback.format_exc()}", flush=True)
                results[i] = PageResult(page_num=i, error=str(e), success=False)

    return _make_response([r for r in results if r is not None])


def _extract_page_safe(pdf_path: str, page_num: int) -> PageResult:
    """스레드마다 PDF를 독립적으로 열어 단일 페이지를 처리한다."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        return extract_page(page, page_num, pdf_path)


# --- 내부 유틸 ---

def _get_page_image(pdf_path: str, page_num: int) -> np.ndarray:
    """PDF 특정 페이지를 numpy 배열(BGR)로 변환."""
    images = convert_from_path(
        pdf_path,
        first_page=page_num + 1,  # pdf2image는 1-based 페이지 번호 사용
        last_page=page_num + 1,
        dpi=settings.pdf_dpi,
        # .env의 PDF_DPI로 조정. 낮추면 빠르지만 OCR 정확도가 떨어진다.
    )
    return cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2BGR)
    # PIL은 RGB, OpenCV는 BGR 순서를 사용하므로 변환 필요.


def _make_response(results: list[PageResult]) -> dict:
    """PageResult 목록을 OCRResponse 호환 dict로 변환."""
    return {
        "pages":         [asdict(r) for r in results],
        "total":         len(results),
        "success_count": sum(1 for r in results if r.success),
        "failed_pages":  [r.page_num for r in results if not r.success],
    }
