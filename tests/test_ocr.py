"""
tests/test_ocr.py

API 동작을 자동으로 검증하는 테스트 코드.

현재 테스트 시나리오 (상세 내용은 test_scenarios.md 참고):
  TC-01 : GET /health → 200
  TC-02 : 이미지 업로드 → 200
  TC-02E: 이미지 디코딩 실패 → 422
  TC-05 : PDF 직접 추출 → method=direct
  TC-06 : PDF OCR 폴백  → method=ocr
  TC-07 : 혼합 PDF      → 페이지별 독립 method
  TC-08 : 테이블 포함 PDF
  TC-09 : 미지원 파일 형식 → 415
  TC-10 : 파일 미첨부 → 422
  TC-11 : 파일 크기 초과 → 413
  TC-12 : 일부 페이지 실패 복구
  TC-13 : 신뢰도 분류 단위 테스트
  TC-14 : 마크다운 표 변환 단위 테스트

실행 방법:
  pytest tests/ -v
"""

import io
from dataclasses import asdict
from unittest.mock import patch

import numpy as np
import cv2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.ocr import PageResult
from app.services.extractor import _get_quality_flag, _make_markdown_table

client = TestClient(app)


# --- 픽스처 ---

@pytest.fixture
def pdf_bytes():
    """최소한의 유효한 PDF 바이트 (extract_parallel이 mock으로 교체되므로 내용 무관)."""
    return b"%PDF-1.4 fake pdf content"


# --- TC-01 헬스체크 ---

def test_health_check():
    """TC-01: GET /health → HTTP 200, { status: ok }"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-02 이미지 업로드 ---

@pytest.fixture
def image_bytes():
    """유효한 10x10 PNG 바이트 (cv2.imdecode 테스트용)."""
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def test_image_upload_ocr(image_bytes):
    """TC-02: 이미지 업로드 → HTTP 200, method='ocr' 또는 'vlm'."""
    from dataclasses import asdict
    mock_result = {
        "pages": [asdict(PageResult(page_num=0, text="추출된 텍스트", method="ocr",
                                    confidence=72.0, quality_flag="medium", success=True))],
        "total": 1, "success_count": 1, "failed_pages": [],
    }
    with patch("app.api.routes.ocr.extract_image", return_value=mock_result):
        response = client.post(
            "/ocr/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["method"] in ("ocr", "vlm")
    assert page["success"] is True


def test_image_upload_invalid_bytes():
    """TC-02E: 디코딩 불가한 bytes → HTTP 422."""
    response = client.post(
        "/ocr/upload",
        files={"file": ("broken.png", b"not_an_image", "image/png")},
    )
    assert response.status_code == 422
    assert "Invalid image" in response.json()["detail"]


# --- TC-05~08 PDF OCR ---

def test_pdf_direct_extraction(pdf_bytes):
    """TC-05: 텍스트 레이어 있는 PDF → method=direct, confidence=null."""
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [asdict(PageResult(page_num=0, text="A" * 100, method="direct", success=True))],
            "total": 1, "success_count": 1, "failed_pages": [],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["method"] == "direct"
    assert page["confidence"] is None
    assert page["quality_flag"] == ""


def test_pdf_ocr_fallback(pdf_bytes):
    """TC-06: 스캔 PDF → method=ocr, confidence 값 존재."""
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [asdict(PageResult(page_num=0, text="스캔된 텍스트", method="ocr",
                                        confidence=72.4, quality_flag="medium", success=True))],
            "total": 1, "success_count": 1, "failed_pages": [],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("scan.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["method"] == "ocr"
    assert page["confidence"] == 72.4
    assert page["quality_flag"] == "medium"


def test_pdf_mixed_pages(pdf_bytes):
    """TC-07: 혼합 PDF → 페이지마다 독립적으로 method 결정."""
    pages = [
        asdict(PageResult(page_num=0, text="충분한 텍스트", method="direct", success=True)),
        asdict(PageResult(page_num=1, text="OCR텍스트", method="ocr",
                          confidence=65.0, quality_flag="medium", success=True)),
        asdict(PageResult(page_num=2, text="충분한 텍스트", method="direct", success=True)),
    ]
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {"pages": pages, "total": 3, "success_count": 3, "failed_pages": []}
        response = client.post(
            "/ocr/upload",
            files={"file": ("mixed.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["pages"][0]["method"] == "direct"
    assert data["pages"][1]["method"] == "ocr"
    assert data["pages"][2]["method"] == "direct"


def test_pdf_with_tables(pdf_bytes):
    """TC-08: 테이블 포함 PDF → tables 배열에 마크다운 표 포함."""
    table_md = "| 이름 | 나이 |\n| --- | --- |\n| 홍길동 | 30 |"
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [asdict(PageResult(page_num=0, text="표 포함 문서",
                                        tables=[table_md], method="direct", success=True))],
            "total": 1, "success_count": 1, "failed_pages": [],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("table.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert len(page["tables"]) == 1
    assert "| 이름 | 나이 |" in page["tables"][0]


# --- TC-09~11 입력 유효성 검사 ---

def test_unsupported_file_type():
    """TC-09: text/plain → HTTP 415."""
    response = client.post(
        "/ocr/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_no_file():
    """TC-10: 파일 미첨부 → HTTP 422 (FastAPI 자동 검증)."""
    response = client.post("/ocr/upload")
    assert response.status_code == 422


def test_file_too_large():
    """TC-11: MAX_FILE_SIZE를 5바이트로 낮추고 10바이트 파일 전송 → HTTP 413."""
    with patch("app.api.routes.ocr.MAX_FILE_SIZE", 5):
        response = client.post(
            "/ocr/upload",
            files={"file": ("large.pdf", b"x" * 10, "application/pdf")},
        )
    assert response.status_code == 413
    assert "File too large" in response.json()["detail"]


# --- TC-12 에러 복구 ---

def test_pdf_partial_failure(pdf_bytes):
    """TC-12: 일부 페이지 실패 → HTTP 200 + failed_pages 기록."""
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [
                asdict(PageResult(page_num=0, text="정상", method="direct", success=True)),
                asdict(PageResult(page_num=1, error="처리 중 예외 발생", success=False)),
                asdict(PageResult(page_num=2, text="정상", method="direct", success=True)),
            ],
            "total": 3, "success_count": 2, "failed_pages": [1],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("partial.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["success_count"] == 2
    assert data["failed_pages"] == [1]
    assert data["pages"][1]["success"] is False
    assert data["pages"][1]["error"] is not None


# --- TC-13~14 단위 테스트 ---

@pytest.mark.parametrize("conf, expected_flag", [
    (85.0, "high"),
    (65.0, "medium"),
    (45.0, "low"),
    (20.0, "very_low"),
])
def test_quality_classification(conf, expected_flag):
    """TC-13: 신뢰도 점수 → quality_flag 분류."""
    assert _get_quality_flag(conf) == expected_flag


def test_table_to_markdown():
    """TC-14: pdfplumber 테이블 → 마크다운 표 변환."""
    table = [["이름", "나이"], ["홍길동", "30"], ["김철수", "25"]]
    result = _make_markdown_table(table)
    assert "| 이름 | 나이 |" in result
    assert "| --- | --- |" in result
    assert "| 홍길동 | 30 |" in result
    assert "| 김철수 | 25 |" in result


def test_table_to_markdown_empty():
    """빈 테이블 입력 → 빈 문자열 반환."""
    assert _make_markdown_table([]) == ""
    assert _make_markdown_table([[]]) == ""


# --- Settings 필드 검증 ---

def test_settings_has_pdf_dpi():
    """pdf_dpi가 Settings에 존재하고 양수인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.pdf_dpi, int)
    assert settings.pdf_dpi > 0


def test_settings_has_omp_num_threads():
    """omp_num_threads가 Settings에 존재하고 1 이상인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.omp_num_threads, int)
    assert settings.omp_num_threads >= 1


def test_settings_has_tesseract_config():
    """tesseract_config가 Settings에 존재하고 --psm 옵션을 포함하는지 확인."""
    from app.core.config import settings
    assert isinstance(settings.tesseract_config, str)
    assert "--psm" in settings.tesseract_config


def test_settings_has_tesseract_lang():
    """tesseract_lang이 Settings에 존재하고 kor을 포함하는지 확인."""
    from app.core.config import settings
    assert isinstance(settings.tesseract_lang, str)
    assert "kor" in settings.tesseract_lang


def test_settings_has_confidence_thresholds():
    """confidence_thresholds가 Settings에 존재하고 4개 키를 포함하는지 확인."""
    from app.core.config import settings
    ct = settings.confidence_thresholds
    assert ct["high"] == 80
    assert ct["medium"] == 60
    assert ct["low"] == 40
    assert ct["very_low"] == 0


def test_settings_has_vlm_fallback_flags():
    """vlm_fallback_flags가 Settings에 존재하고 list[str]인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.vlm_fallback_flags, list)
    assert all(isinstance(f, str) for f in settings.vlm_fallback_flags)
    assert len(settings.vlm_fallback_flags) >= 1


# --- run_vlm() 단위 테스트 ---

def test_run_vlm_raises_not_implemented_without_api_key(monkeypatch):
    """API 키 미설정 시 NotImplementedError → 호출부에서 Tesseract 결과 유지."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "openai_api_key", "")
    from app.services.vlm import run_vlm
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(NotImplementedError):
        run_vlm(image)


def test_get_vlm_confidence_zero():
    """빈 텍스트 → confidence=0.0."""
    from app.services.vlm import _get_vlm_confidence
    assert _get_vlm_confidence("") == 0.0


def test_get_vlm_confidence_half():
    """250자 텍스트 → confidence=50.0 (상한 500자 기준)."""
    from app.services.vlm import _get_vlm_confidence
    assert _get_vlm_confidence("x" * 250) == 50.0


def test_get_vlm_confidence_max():
    """500자 이상 텍스트 → confidence=100.0 (상한 초과 시 고정)."""
    from app.services.vlm import _get_vlm_confidence
    assert _get_vlm_confidence("x" * 600) == 100.0


def test_run_vlm_returns_correct_structure(monkeypatch):
    """API 키 설정 + mock 응답 → {"text", "confidence", "quality_flag"} 구조 반환."""
    from unittest.mock import MagicMock, patch
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.settings, "vlm_model", "gpt-4o")
    monkeypatch.setattr(cfg.settings, "vlm_max_tokens", 1024)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "x" * 400  # 400자 → confidence=80.0, flag="high"

    from app.services.vlm import run_vlm
    image = np.zeros((10, 10, 3), dtype=np.uint8)

    with patch("openai.OpenAI") as mock_openai_cls:
        # openai.OpenAI를 패치해야 함수 내부 lazy import에서도 mock이 적용된다.
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        result = run_vlm(image)

    assert "text" in result
    assert "confidence" in result
    assert "quality_flag" in result
    assert result["text"] == "x" * 400
    assert result["confidence"] == 80.0
    assert result["quality_flag"] == "high"


# --- run_ocr_with_fallback 단위 테스트 ---

def test_run_ocr_with_fallback_high_confidence():
    """신뢰도 높으면 Tesseract 결과 반환, VLM 호출 없음."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "hello", "confidence": 85.0, "quality_flag": "high"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm") as mock_vlm:
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "tesseract"
    assert result["text"] == "hello"
    mock_vlm.assert_not_called()


def test_run_ocr_with_fallback_vlm_escalation():
    """quality_flag가 vlm_fallback_flags에 해당하면 VLM 결과 반환."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "bad", "confidence": 10.0, "quality_flag": "very_low"}
    vlm_result = {"text": "good", "confidence": 90.0, "quality_flag": "high"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm", return_value=vlm_result):
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "vlm"
    assert result["text"] == "good"


def test_run_ocr_with_fallback_vlm_not_implemented():
    """VLM NotImplementedError 시 Tesseract 결과를 그대로 반환."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "fallback", "confidence": 10.0, "quality_flag": "very_low"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm", side_effect=NotImplementedError):
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "tesseract"
    assert result["text"] == "fallback"


def test_run_ocr_with_fallback_api_error_falls_back_to_tesseract():
    """run_vlm()이 API 오류(NotImplementedError 아닌 예외)를 던져도 Tesseract 결과 반환."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "fallback", "confidence": 10.0, "quality_flag": "very_low"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm", side_effect=RuntimeError("API error")):
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "tesseract"
    assert result["text"] == "fallback"


# --- extract_image 단위 테스트 ---

def test_extract_image_returns_ocr_response_format():
    """extract_image()가 extract_parallel()과 동일한 dict 구조를 반환한다."""
    from app.services.extractor import extract_image
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    fallback_result = {"text": "test", "confidence": 72.0, "quality_flag": "medium", "engine": "tesseract"}
    with patch("app.services.extractor.run_ocr_with_fallback", return_value=fallback_result):
        result = extract_image(image)
    assert "pages" in result
    assert "total" in result
    assert "success_count" in result
    assert "failed_pages" in result
    assert result["total"] == 1
    assert result["pages"][0]["page_num"] == 0
    assert result["pages"][0]["method"] == "ocr"
    assert result["pages"][0]["success"] is True


def test_extract_image_vlm_engine_sets_method_vlm():
    """VLM 엔진 사용 시 method가 'vlm'으로 기록된다."""
    from app.services.extractor import extract_image
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    vlm_result = {"text": "vlm text", "confidence": 90.0, "quality_flag": "high", "engine": "vlm"}
    with patch("app.services.extractor.run_ocr_with_fallback", return_value=vlm_result):
        result = extract_image(image)
    assert result["pages"][0]["method"] == "vlm"


# --- Settings VLM 필드 검증 ---

def test_settings_has_openai_api_key():
    """openai_api_key가 Settings에 존재하고 str 타입인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.openai_api_key, str)


def test_settings_has_vlm_model():
    """vlm_model이 Settings에 존재하고 비어있지 않은지 확인."""
    from app.core.config import settings
    assert isinstance(settings.vlm_model, str)
    assert len(settings.vlm_model) > 0


def test_settings_has_vlm_max_tokens():
    """vlm_max_tokens가 Settings에 존재하고 양수인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.vlm_max_tokens, int)
    assert settings.vlm_max_tokens > 0
