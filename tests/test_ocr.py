"""
[읽기 순서 7/7] tests/test_ocr.py

이 파일의 역할:
  API가 올바르게 동작하는지 자동으로 검증하는 테스트 코드.
  pytest 명령어 한 번으로 TC-01 ~ TC-14 시나리오를 모두 실행한다.

  시나리오 상세: tests/test_scenarios.md 참고

┌─────────────────────────────────────────────────────────┐
│  비유: 공장의 "자동화 품질 검사 라인"                    │
│                                                         │
│  사람이 매번 curl이나 Postman으로 확인하는 대신          │
│  자동 기계(테스트)가 1초 만에 수십 가지 시나리오를       │
│  동시에 검사한다.                                       │
│                                                         │
│  핵심 기술: Mock(가짜 객체)                             │
│    EasyOCR 모델, Tesseract, pdfplumber는 실제 실행 시   │
│    수십 초가 걸리므로 테스트마다 실행하면 너무 느림.     │
│    Mock으로 "가짜 결과를 즉시 반환"하게 만들어서         │
│    API 로직과 응답 구조만 빠르게 검증한다.              │
└─────────────────────────────────────────────────────────┘

실행 방법:
  pytest tests/ -v           # 전체 테스트 + 상세 출력
  pytest tests/test_ocr.py::test_health_check -v   # 특정 테스트만
"""

import io
# io.BytesIO : bytes를 파일처럼 다루기 위한 메모리 스트림

from dataclasses import asdict
# asdict : PageResult → dict 변환 (mock 반환값 생성 시 사용)

from unittest.mock import MagicMock, patch
# unittest.mock : 파이썬 표준 Mock 라이브러리
#
# MagicMock : "마법의 가짜 객체". 어떤 속성/메서드를 호출해도 에러 없이 동작.
#   비유: "뭐든 OK라고 대답하는 더미 직원"
#   mock = MagicMock()
#   mock.anything()         → MagicMock() 반환 (에러 없음)
#   mock.return_value = 42  → mock() 호출 시 42 반환
#
# patch : 특정 함수나 클래스를 테스트 동안만 Mock으로 교체.
#   with patch("app.services.easyocr_service.get_reader") as mock:
#   → 이 with 블록 안에서만 get_reader를 mock으로 대체
#   → with 블록 밖에서는 원래 함수로 복원됨
#   비유: 공연에서 실제 배우 대신 대역을 쓰는 것 (공연 후엔 원래대로)

import numpy as np
import pytest
# pytest : 파이썬 테스트 프레임워크
# test_로 시작하는 함수를 자동으로 찾아서 실행
# assert가 실패하면 테스트 실패(빨간색), 모두 통과하면 성공(초록색)

from fastapi.testclient import TestClient
# TestClient : 실제 서버 실행 없이 HTTP 요청을 시뮬레이션하는 클라이언트

from PIL import Image
# Pillow : 테스트용 이미지를 코드로 생성할 때 사용

from app.main import app                          # 테스트 대상 FastAPI 앱
from app.schemas.ocr import PageResult            # Mock 반환값 생성 시 사용
from app.services.extractor import _classify_quality, _table_to_markdown
# 내부 유틸 함수를 직접 단위 테스트할 때 import

client = TestClient(app)
# 모든 테스트에서 공유하는 가상 HTTP 클라이언트
# 모듈 수준에 선언하면 각 테스트 함수에서 재사용 가능


# ================================================================
# 픽스처 — 반복 사용하는 테스트용 파일 생성
# ================================================================
# pytest 픽스처(Fixture):
#   테스트에서 반복적으로 필요한 "사전 준비 작업"을 재사용 가능한 함수로 만든 것.
#   @pytest.fixture 를 붙이면 테스트 함수의 파라미터로 이름을 쓸 수 있다.
#
# 비유: 요리 실습 전에 미리 준비해둔 "재료 세트"
#   각 테스트(요리사)가 매번 재료를 준비하는 대신
#   픽스처(보조 직원)가 미리 준비해서 전달해줌.

@pytest.fixture
def png_file(tmp_path):
    """흰 배경에 검은 텍스트가 있는 PNG 파일."""
    # tmp_path : pytest가 자동으로 제공하는 임시 폴더 경로 (테스트 후 자동 삭제)
    img = Image.new("RGB", (300, 80), color="white")
    path = tmp_path / "test.png"
    img.save(path)
    return path
    # 반환된 path를 테스트 함수의 파라미터로 받아서 사용


@pytest.fixture
def pdf_bytes():
    """최소한의 유효한 PDF 바이트 (실제 파싱 없이 mock에서 사용)."""
    return b"%PDF-1.4 fake pdf content"
    # 실제 PDF가 아니지만 extract_parallel이 mock으로 교체되므로
    # 실제 내용이 파싱될 일이 없다.


@pytest.fixture
def mock_easyocr():
    """EasyOCR Reader를 mock으로 대체. 고정된 결과를 반환한다."""
    with patch("app.services.easyocr_service.get_reader") as mock:
        # "app.services.easyocr_service.get_reader" :
        #   패치할 함수의 경로 (모듈.함수명 형식)
        #   반드시 "실제로 사용하는 위치"를 패치해야 한다.

        reader = MagicMock()
        reader.readtext.return_value = [
            # (바운딩박스, 텍스트, 신뢰도) 형식의 EasyOCR 가짜 반환값
            ([[0, 0], [100, 0], [100, 20], [0, 20]], "Hello OCR", 0.95),
            ([[0, 25], [80, 25], [80, 45], [0, 45]], "FastAPI", 0.88),
        ]
        mock.return_value = reader
        yield reader
        # yield : 픽스처가 반환값을 "넘겨주고" 테스트가 끝날 때까지 대기.
        # 테스트 완료 후 with patch 블록이 종료되어 원래 함수로 복원.


@pytest.fixture
def mock_pdf_direct():
    """직접 추출 가능한 PDF 페이지 mock (텍스트 충분)."""
    page = MagicMock()
    page.extract_text.return_value = "A" * 100
    # "A" * 100 = "AAA...A" (100자) → ocr_text_threshold(50)를 초과 → direct 방식
    page.extract_tables.return_value = []
    return page


@pytest.fixture
def mock_pdf_ocr():
    """OCR 폴백이 필요한 PDF 페이지 mock (텍스트 부족)."""
    page = MagicMock()
    page.extract_text.return_value = "짧"
    # 1자 → ocr_text_threshold(50) 미만 → OCR 폴백
    page.extract_tables.return_value = []
    return page


# ================================================================
# TC-01 기본 동작 — 서버 상태 확인
# ================================================================

def test_health_check():
    """TC-01: GET /health → HTTP 200, { status: ok }"""
    response = client.get("/health")

    assert response.status_code == 200
    # assert : 조건이 False이면 테스트 실패. 비유: "이 조건이 반드시 참이어야 한다"

    assert response.json() == {"status": "ok"}
    # .json() : 응답 본문을 파이썬 딕셔너리로 파싱


# ================================================================
# TC-02, TC-03 이미지 OCR
# ================================================================

def test_image_high_quality(png_file, mock_easyocr):
    """TC-02: 고품질 이미지 업로드 → 응답 구조 및 quality_flag 확인."""
    # png_file, mock_easyocr : pytest가 픽스처를 자동으로 주입
    with open(png_file, "rb") as f:
        # "rb" : 이진(binary) 읽기 모드. 이미지는 텍스트가 아닌 이진 파일.
        response = client.post(
            "/ocr/upload",
            files={"file": ("test_high.png", f, "image/png")},
            # files 딕셔너리 형식: {"form필드명": (파일명, 파일객체, MIME타입)}
        )

    assert response.status_code == 200
    data = response.json()

    # 응답 최상위 구조 검증
    assert data["filename"] == "test_high.png"
    assert data["total"] == 1           # 이미지는 항상 1페이지
    assert data["success_count"] == 1
    assert data["failed_pages"] == []

    # 페이지 구조 검증
    page = data["pages"][0]
    assert page["page_num"] == 0
    assert page["method"] == "ocr"      # 이미지는 항상 ocr 방식
    assert page["success"] is True
    assert "Hello OCR" in page["text"]  # mock에서 반환한 텍스트 포함 여부
    assert page["quality_flag"] == "high"
    # mock 신뢰도 0.95 → 0~100 변환 시 95 → 80 이상 → "high"

    assert page["confidence"] is not None


def test_image_low_quality(tmp_path, mock_easyocr):
    """TC-03: 저신뢰도 결과를 반환하는 이미지 → quality_flag 확인."""
    mock_easyocr.readtext.return_value = [
        ([[0, 0], [100, 0], [100, 20], [0, 20]], "흐릿한텍스트", 0.35),
        # 신뢰도 0.35 → 0~100 변환 시 35 → "low" 등급
    ]
    img = Image.new("RGB", (100, 30), color="gray")
    path = tmp_path / "low.png"
    img.save(path)

    with open(path, "rb") as f:
        response = client.post(
            "/ocr/upload",
            files={"file": ("low.png", f, "image/png")},
        )

    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["quality_flag"] in ("low", "very_low", "medium")
    # 신뢰도 35이므로 "low" 또는 경계에 따라 "medium"도 가능
    assert page["success"] is True
    # 품질이 낮아도 에러가 아님 → success는 여전히 True


def test_image_formats(tmp_path, mock_easyocr):
    """TC-04: 지원하는 이미지 형식 4가지 모두 200 반환 확인."""
    formats = [
        ("image/jpeg", "test.jpg"),
        ("image/png",  "test.png"),
        ("image/webp", "test.webp"),
        ("image/tiff", "test.tiff"),
    ]
    img = Image.new("RGB", (100, 30), color="white")

    for mime, filename in formats:
        # for A, B in 리스트 : 튜플 언패킹으로 각 항목을 A, B로 분리
        path = tmp_path / filename
        fmt = filename.split(".")[-1].upper()
        # "test.jpg" → split(".") → ["test", "jpg"] → [-1] → "jpg" → upper() → "JPG"
        fmt = "JPEG" if fmt == "JPG" else fmt
        # PIL은 "JPG" 대신 "JPEG"로 저장 형식을 지정해야 함
        img.save(path, format=fmt)

        with open(path, "rb") as f:
            response = client.post(
                "/ocr/upload",
                files={"file": (filename, f, mime)},
            )
        assert response.status_code == 200, f"{mime} 형식이 실패함"
        # assert 뒤의 문자열 : 실패 시 출력할 메시지 (디버깅 편의를 위한 것)


# ================================================================
# TC-05, TC-06, TC-07 PDF OCR
# ================================================================

def test_pdf_direct_extraction(pdf_bytes, mock_pdf_direct):
    """TC-05: 텍스트 레이어가 있는 PDF → method = direct, confidence = null."""
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        # extract_parallel을 mock으로 교체
        # "app.api.routes.ocr.extract_parallel" : routes/ocr.py에서 import된 함수를 패치
        # (easyocr_service처럼 서비스 파일이 아닌 "사용 위치"를 패치해야 함)

        mock_extract.return_value = {
            # extract_parallel()이 반환할 가짜 값 설정
            "pages": [asdict(PageResult(
                page_num=0,
                text="A" * 100,
                method="direct",   # 직접 추출
                success=True,
                # confidence=None (기본값) : 직접 추출은 신뢰도 없음
            ))],
            "total": 1,
            "success_count": 1,
            "failed_pages": [],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            # io.BytesIO(pdf_bytes) : bytes를 파일 객체로 포장
        )

    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["method"] == "direct"
    assert page["confidence"] is None    # 직접 추출 → 신뢰도 없음 → null
    assert page["quality_flag"] == ""    # 직접 추출 → 품질 등급 없음 → 빈 문자열


def test_pdf_ocr_fallback(pdf_bytes):
    """TC-06: 스캔 PDF → method = ocr, confidence 값 존재."""
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [asdict(PageResult(
                page_num=0,
                text="스캔된 텍스트",
                method="ocr",          # OCR 방식
                confidence=72.4,       # 신뢰도 있음
                quality_flag="medium", # 60~80 → medium
                success=True,
            ))],
            "total": 1,
            "success_count": 1,
            "failed_pages": [],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("scan.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["method"] == "ocr"
    assert page["confidence"] == 72.4   # 신뢰도 값이 그대로 반환되는지 확인
    assert page["quality_flag"] == "medium"


def test_pdf_mixed_pages(pdf_bytes):
    """TC-07: 혼합 PDF → 페이지마다 독립적으로 method가 결정됨."""
    pages = [
        asdict(PageResult(page_num=0, text="충분한 텍스트", method="direct", success=True)),
        asdict(PageResult(page_num=1, text="OCR텍스트", method="ocr", confidence=65.0, quality_flag="medium", success=True)),
        asdict(PageResult(page_num=2, text="충분한 텍스트", method="direct", success=True)),
    ]
    # 3개 페이지: 0번과 2번은 direct, 1번은 ocr
    # 핵심 검증: 첫 페이지가 direct라고 나머지도 direct가 되면 안 됨
    #           각 페이지가 독립적으로 판단되어야 함

    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": pages,
            "total": 3,
            "success_count": 3,
            "failed_pages": [],
        }
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
    # 마크다운 표 형식의 문자열

    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [asdict(PageResult(
                page_num=0,
                text="표 포함 문서",
                tables=[table_md],  # 표가 포함된 페이지
                method="direct",
                success=True,
            ))],
            "total": 1,
            "success_count": 1,
            "failed_pages": [],
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("table.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert len(page["tables"]) == 1              # 표가 1개
    assert "| 이름 | 나이 |" in page["tables"][0]  # 마크다운 표 형식 확인


# ================================================================
# TC-09, TC-10, TC-11 입력 유효성 검사
# ================================================================

def test_unsupported_file_type():
    """TC-09: 지원하지 않는 파일 형식 → HTTP 415."""
    response = client.post(
        "/ocr/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
        # "text/plain" : MIME 타입 — ALLOWED_IMAGE_TYPES, ALLOWED_PDF_TYPES 모두에 없음
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]
    # 에러 메시지에 "Unsupported file type"이 포함되어 있는지 확인


def test_no_file():
    """TC-10: 파일 미첨부 → HTTP 422 (FastAPI 자동 유효성 검사)."""
    response = client.post("/ocr/upload")
    # 파일을 첨부하지 않으면 FastAPI가 자동으로 422 에러를 반환
    # 422 = Unprocessable Entity (필수 파라미터 누락)
    assert response.status_code == 422


def test_file_too_large():
    """TC-11: 파일 크기 초과 → HTTP 413.

    MAX_FILE_SIZE를 5바이트로 낮추고 10바이트 파일을 전송해서 검증한다.
    실제 50MB 파일 생성 없이 동일한 분기를 테스트할 수 있다.
    """
    with patch("app.api.routes.ocr.MAX_FILE_SIZE", 5):
        # MAX_FILE_SIZE를 테스트 동안만 5바이트로 낮춤
        # 실제 50MB 파일을 만들 필요 없이 작은 파일로 초과 상황을 재현
        response = client.post(
            "/ocr/upload",
            files={"file": ("large.pdf", b"x" * 10, "application/pdf")},
            # b"x" * 10 = 10바이트 → MAX_FILE_SIZE(5바이트) 초과
        )
    assert response.status_code == 413
    # 413 = Request Entity Too Large
    assert "File too large" in response.json()["detail"]


# ================================================================
# TC-12 에러 복구
# ================================================================

def test_pdf_partial_failure(pdf_bytes):
    """TC-12: 특정 페이지 실패 → 나머지 페이지는 정상 처리."""
    # 핵심 검증: 1개 페이지가 실패해도 HTTP 200을 반환하고
    #           실패 정보가 응답 내에 기록되어야 함
    with patch("app.api.routes.ocr.extract_parallel") as mock_extract:
        mock_extract.return_value = {
            "pages": [
                asdict(PageResult(page_num=0, text="정상", method="direct", success=True)),
                asdict(PageResult(page_num=1, error="처리 중 예외 발생", success=False)),
                # success=False : 2번 페이지 실패 시뮬레이션
                asdict(PageResult(page_num=2, text="정상", method="direct", success=True)),
            ],
            "total": 3,
            "success_count": 2,   # 3중 2개만 성공
            "failed_pages": [1],  # 1번 페이지 실패
        }
        response = client.post(
            "/ocr/upload",
            files={"file": ("partial.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert response.status_code == 200
    # 일부 페이지 실패여도 전체 요청은 200 OK
    data = response.json()
    assert data["total"] == 3
    assert data["success_count"] == 2
    assert data["failed_pages"] == [1]
    assert data["pages"][0]["success"] is True
    assert data["pages"][1]["success"] is False
    assert data["pages"][1]["error"] is not None   # 에러 메시지가 있어야 함
    assert data["pages"][2]["success"] is True


# ================================================================
# TC-13, TC-14 단위 테스트 — 서비스 내부 로직
# ================================================================
# 단위 테스트(Unit Test):
#   API 전체가 아닌 특정 함수 하나만 독립적으로 테스트.
#   함수의 입력/출력이 예상대로인지 확인.
#
# @pytest.mark.parametrize : 여러 입력 케이스를 한 함수로 반복 테스트
#   비유: 같은 테스트를 다른 재료로 여러 번 실행하는 것

@pytest.mark.parametrize("conf, expected_flag", [
    (85.0, "high"),     # 85 ≥ 80 → "high"
    (65.0, "medium"),   # 65 ≥ 60 → "medium"
    (45.0, "low"),      # 45 ≥ 40 → "low"
    (20.0, "very_low"), # 20 < 40 → "very_low"
])
def test_quality_classification(conf, expected_flag):
    """TC-13: 신뢰도 점수 → quality_flag 분류 검증."""
    from app.services.extractor import _classify_quality
    assert _classify_quality(conf) == expected_flag
    # 각 conf 값에 대해 4번 실행됨 (parametrize로 자동 반복)


def test_table_to_markdown():
    """TC-14: pdfplumber 테이블 데이터 → 마크다운 표 변환 검증."""
    table = [
        ["이름", "나이"],       # 헤더 행
        ["홍길동", "30"],       # 데이터 행
        ["김철수", "25"],
    ]
    result = _table_to_markdown(table)

    # 마크다운 표의 각 구성 요소가 포함되어 있는지 확인
    assert "| 이름 | 나이 |" in result      # 헤더
    assert "| --- | --- |" in result      # 구분선
    assert "| 홍길동 | 30 |" in result     # 데이터 행 1
    assert "| 김철수 | 25 |" in result     # 데이터 행 2


def test_table_to_markdown_empty():
    """빈 테이블 입력 시 빈 문자열 반환."""
    assert _table_to_markdown([]) == ""
    # 빈 리스트 → 빈 문자열 (에러 없음)

    assert _table_to_markdown([[]]) == ""
    # 헤더 행이 비어있는 경우도 빈 문자열 반환
