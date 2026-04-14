"""
app/schemas/ocr.py — 데이터 구조 정의.
PageResult(내부 처리용 dataclass) + OCRResponse(API 응답용 Pydantic 모델).
"""
from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel


@dataclass
class PageResult:
    """페이지 단위 추출 결과. 모든 추출 함수는 반드시 이 타입을 반환해야 한다."""

    page_num: int                       # 0-based 페이지 번호

    text:         str             = ""
    # default_factory=list 사용 이유: dataclass에서 = [] 로 선언하면
    # 모든 인스턴스가 동일한 리스트 객체를 공유해 서로 영향을 준다.
    tables:       list[str]       = field(default_factory=list)

    method:       str             = ""
    # "direct": pdfplumber 직접 추출 / "ocr": Tesseract OCR

    confidence:   Optional[float] = None
    # OCR 평균 신뢰도 (0~100). method="direct"이면 None.

    quality_flag: str             = ""
    # confidence 구간별 등급: "high"(≥80) / "medium"(≥60) / "low"(≥40) / "very_low"(<40)
    # method="direct"이면 빈 문자열.

    error:        Optional[str]   = None  # 처리 실패 시 에러 메시지
    success:      bool            = True  # False이면 error 필드에 원인 기록


class OCRResponse(BaseModel):
    """POST /ocr/upload 의 최종 응답 구조."""

    filename:      str        # 업로드된 파일 이름
    pages:         list[dict] # 각 페이지의 PageResult를 dict로 변환한 목록
    total:         int        # 전체 페이지 수
    success_count: int        # 성공 처리 페이지 수
    failed_pages:  list[int]  # 실패 페이지 번호 목록 (0-based). 모두 성공이면 []
