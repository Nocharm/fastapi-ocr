# =====================================================================
# [읽기 순서 1/7] app/schemas/ocr.py
#
# 이 파일의 역할:
#   API 전체에서 데이터를 주고받는 "구조(모양)"를 정의한다.
#   모든 서비스 함수와 API 응답은 이 파일에 정의된 타입을 사용해야 한다.
#
# ┌─────────────────────────────────────────────────────────┐
# │  비유: 택배 회사의 "표준 박스 규격"                       │
# │                                                         │
# │  택배 회사가 "소형 박스는 이 크기, 이 정보를 담아라"     │
# │  라고 규격을 정해두면                                    │
# │  포장 직원(서비스), 배송 직원(라우터) 모두               │
# │  같은 박스를 쓰게 되어 혼선이 없다.                      │
# │                                                         │
# │  PageResult  = 페이지 1장의 OCR 결과 박스                │
# │  OCRResponse = 파일 전체의 최종 응답 박스                │
# └─────────────────────────────────────────────────────────┘
# =====================================================================

from dataclasses import dataclass, field
# dataclass : 데이터를 담는 클래스를 간결하게 만들어주는 파이썬 데코레이터.
#
# 비유: 빈 양식지에 "이름, 나이, 주소" 칸을 자동으로 만들어주는 도장.
# @dataclass를 붙이면 __init__, __repr__ 등 반복적인 메서드를
# 파이썬이 자동으로 생성해줘서 코드가 훨씬 짧아진다.
#
# field : dataclass 필드에 추가 옵션(기본값, 팩토리 등)을 설정할 때 사용.

from typing import Optional
# Optional[X] : "X 타입 또는 None" 을 의미하는 타입 힌트.
# 예) Optional[float] → float 값일 수도 있고, 아직 모를 때는 None.
# 비유: 설문지에서 "해당 없으면 비워두세요" 항목

from pydantic import BaseModel
# BaseModel : Pydantic의 기본 클래스.
# 이를 상속하면 JSON 직렬화(파이썬 객체 → JSON 문자열) 및
# 자동 타입 검증 기능이 활성화된다.
# routes/ocr.py의 response_model= 에서 사용된다.


@dataclass
class PageResult:
    """페이지 단위 추출 결과. 모든 추출 함수는 반드시 이 타입을 반환해야 한다."""
    # @dataclass : 이 클래스를 "데이터 컨테이너"로 선언하는 데코레이터.
    #   __init__을 자동 생성하므로 PageResult(page_num=0, text="안녕") 처럼 바로 생성 가능.
    #
    # 비유: OCR 결과를 담는 "페이지 성적표"
    #   page_num   = 몇 페이지인지
    #   text       = 인식된 텍스트
    #   tables     = 표 목록
    #   method     = 어떻게 추출했는지 ("direct" 또는 "ocr")
    #   confidence = 얼마나 정확한지 (0~100)
    #   quality_flag = 품질 등급 ("high", "medium", "low", "very_low")
    #   error      = 실패했다면 에러 메시지
    #   success    = 성공 여부

    page_num:     int
    # 0부터 시작하는 페이지 번호 (0-based index)
    # 예) 첫 번째 페이지 = 0, 두 번째 페이지 = 1

    text:         str             = ""
    # OCR로 추출된 텍스트 (기본값: 빈 문자열)

    tables:       list[str]       = field(default_factory=list)
    # 추출된 테이블 목록. 각 항목은 마크다운 표 형식의 문자열.
    # 예) ["| 이름 | 나이 |\n| --- | --- |\n| 홍길동 | 30 |"]
    #
    # field(default_factory=list) 를 쓰는 이유:
    #   dataclass에서 가변 객체(list, dict 등)를 기본값으로 쓸 때는
    #   = [] 대신 반드시 field(default_factory=list)를 써야 한다.
    #
    #   왜? = [] 를 쓰면 모든 인스턴스가 같은 리스트 객체를 공유하게 돼서
    #   한 인스턴스에서 리스트를 수정하면 다른 인스턴스에도 영향을 준다.
    #   default_factory=list 는 인스턴스마다 새 리스트를 생성하게 해준다.
    #   비유: "공용 메모장" 대신 "1인 1메모장"을 나눠주는 것.

    method:       str             = ""
    # 추출 방식
    # "direct" = pdfplumber로 텍스트 레이어에서 직접 추출 (빠름, 신뢰도 없음)
    # "ocr"    = Tesseract OCR로 이미지를 분석해 텍스트 추출 (느림, 신뢰도 있음)

    confidence:   Optional[float] = None
    # OCR 신뢰도 (0.0~100.0)
    # method="direct" 이면 OCR을 쓰지 않으므로 None
    # method="ocr" 이면 Tesseract가 각 단어별 신뢰도의 평균값을 반환

    quality_flag: str             = ""
    # 신뢰도를 사람이 읽기 쉬운 등급으로 변환한 문자열
    # "high"     = confidence >= 80  (신뢰할 수 있음)
    # "medium"   = confidence >= 60  (수용 가능)
    # "low"      = confidence >= 40  (재처리 권장)
    # "very_low" = confidence <  40  (반드시 검토 필요)
    # ""         = direct 방식이라 해당 없음

    error:        Optional[str]   = None
    # 처리 중 에러가 발생했다면 에러 메시지. 정상이면 None.

    success:      bool            = True
    # 페이지 처리 성공 여부
    # False 이면 error 필드에 원인이 기록됨


class OCRResponse(BaseModel):
    """API 응답 구조. 이미지/PDF 모두 이 형식으로 반환된다."""
    # BaseModel을 상속하는 이유:
    #   routes/ocr.py에서 response_model=OCRResponse 로 지정하면
    #   FastAPI가 이 구조에 맞게 JSON 응답을 자동으로 검증하고 직렬화해준다.
    #
    # 최종 JSON 응답 예시:
    # {
    #   "filename": "invoice.pdf",
    #   "pages": [
    #     {
    #       "page_num": 0,
    #       "text": "청구서\n합계 100,000원",
    #       "tables": ["| 항목 | 금액 |\n|---|---|\n| 서비스 | 100,000 |"],
    #       "method": "direct",
    #       "confidence": null,
    #       "quality_flag": "",
    #       "error": null,
    #       "success": true
    #     }
    #   ],
    #   "total": 1,
    #   "success_count": 1,
    #   "failed_pages": []
    # }

    filename:      str
    # 업로드된 파일의 이름. 예) "document.pdf"

    pages:         list[dict]
    # 각 페이지의 PageResult를 딕셔너리로 변환한 목록.
    # PageResult → dict 변환은 dataclasses.asdict()로 수행됨 (extractor.py 참고).

    total:         int
    # 전체 페이지 수. 이미지는 항상 1.

    success_count: int
    # 성공적으로 처리된 페이지 수.
    # success_count < total 이면 일부 페이지 처리 실패.

    failed_pages:  list[int]
    # 처리에 실패한 페이지 번호 목록 (0-based).
    # 예) [1, 3] → 2번째, 4번째 페이지 실패
    # 빈 리스트([])면 모두 성공.
