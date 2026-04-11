# =====================================================================
# [읽기 순서 4/7] app/api/routes/ocr.py
#
# 이 파일의 역할:
#   클라이언트의 HTTP 요청을 받아서 파일 타입에 맞는 서비스로 넘긴 뒤
#   OCRResponse 형태로 응답을 돌려준다.
#   비즈니스 로직(실제 OCR 처리)은 services/ 폴더에 위임한다.
#
# ┌─────────────────────────────────────────────────────────┐
# │  비유: 음식점의 "홀 직원"                                │
# │                                                         │
# │  손님(클라이언트)이 주문(요청)을 하면                    │
# │  홀 직원(routes/ocr.py)이 주문을 받아서:                │
# │   1. 메뉴판에 있는 음식인지 확인 (파일 타입 검증)        │
# │   2. 양이 너무 많지 않은지 확인 (파일 크기 검증)         │
# │   3. 주방(services/)에 넘겨주고                         │
# │   4. 완성된 음식(응답)을 손님에게 가져다 준다.           │
# │                                                         │
# │  홀 직원은 요리를 직접 하지 않는다.                     │
# └─────────────────────────────────────────────────────────┘
# =====================================================================

from fastapi import APIRouter, File, HTTPException, UploadFile
# APIRouter   : 라우터 객체 생성. 앱을 여러 파일로 분리할 수 있게 해줌.
# File        : 이 파라미터가 form-data의 파일 필드임을 FastAPI에게 알려주는 선언자.
# HTTPException : HTTP 에러 응답을 발생시킬 때 사용.
# UploadFile  : 업로드된 파일 객체 타입.
#               - file.filename    : 파일 이름
#               - file.content_type: MIME 타입 (예: "image/png")
#               - file.size        : 파일 크기 (바이트 단위, 없을 수도 있음)
#               - await file.read(): 파일 내용을 bytes로 읽음

from app.schemas.ocr import OCRResponse
# 응답 데이터 구조 (schemas/ocr.py 참고)

from app.services.easyocr_service import extract_image
# 이미지 파일용 OCR 서비스

from app.services.extractor import extract_parallel
# PDF 파일용 추출 서비스 (병렬 처리)


# 이 파일의 라우터 인스턴스 생성
# main.py에서 app.include_router()로 등록하면 앱의 일부가 됨
router = APIRouter()

# ---------------------------------------------------------------
# 허용하는 파일 형식 (MIME 타입 기준)
# MIME 타입 : 파일 종류를 나타내는 표준 문자열
#   예) "image/png", "application/pdf"
#   {} (중괄호) = 파이썬 집합(set). 중복 없이 빠른 포함 여부 확인 가능.
# ---------------------------------------------------------------
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
ALLOWED_PDF_TYPES   = {"application/pdf"}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (바이트 단위로 계산: 50 × 1024 × 1024)
# 허용하는 최대 파일 크기.
# 1 KB = 1024 바이트, 1 MB = 1024 KB → 50 MB = 50 × 1024 × 1024 바이트


@router.post("/upload", response_model=OCRResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    파일을 업로드하면 OCR 결과를 페이지별 구조화된 JSON으로 반환한다.

    - 이미지 → EasyOCR (단일 페이지 결과)
    - PDF    → pdfplumber + Tesseract 하이브리드 추출 (페이지별 결과)

    응답 형식:
        {
            "filename": "document.pdf",
            "pages": [ { page_num, text, tables, method, confidence, ... } ],
            "total": 5,
            "success_count": 4,
            "failed_pages": [3]
        }
    """
    # ---------------------------------------------------------------
    # 파일 크기 사전 검증
    #
    # file.size : HTTP 요청의 Content-Length 헤더에서 읽은 파일 크기.
    #   실제 파일을 읽지 않고(read() 호출 없이) 빠르게 크기를 확인할 수 있다.
    #   단, 클라이언트가 헤더를 보내지 않은 경우 None이 될 수 있으므로
    #   "if file.size and ..." 로 None 체크를 먼저 한다.
    #
    # 비유: 택배 접수 시 무게를 달아보고 50kg 초과면 바로 거절하는 것.
    #       짐을 풀어보기(read()) 전에 겉에서 확인하는 것.
    # ---------------------------------------------------------------
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            # 413 = Request Entity Too Large (파일이 너무 큼)
            detail=f"File too large. Max allowed size is {MAX_FILE_SIZE // 1024 // 1024} MB.",
            # // : 정수 나눗셈. 50*1024*1024 // 1024 // 1024 = 50 (MB로 다시 변환)
        )

    content_type = file.content_type
    # 업로드된 파일의 MIME 타입을 확인
    # 예) JPEG 이미지 → "image/jpeg", PDF → "application/pdf"

    # 파일 종류에 따라 알맞은 서비스로 처리를 위임
    if content_type in ALLOWED_IMAGE_TYPES:
        # 이미지 → EasyOCR 서비스
        result = await extract_image(file)

    elif content_type in ALLOWED_PDF_TYPES:
        # PDF → 임시 파일 저장 후 병렬 추출
        result = await _handle_pdf(file)

    else:
        # 허용되지 않는 파일 형식
        # | 연산자로 두 집합을 합쳐서 허용 목록 전체를 에러 메시지에 포함
        raise HTTPException(
            status_code=415,
            # 415 = Unsupported Media Type (지원하지 않는 파일 형식)
            detail=f"Unsupported file type: {content_type}. "
                   f"Allowed: {ALLOWED_IMAGE_TYPES | ALLOWED_PDF_TYPES}",
        )

    # OCRResponse 객체를 반환하면 FastAPI가 JSON으로 변환해서 응답
    # **result : 딕셔너리를 키워드 인자로 풀어서 전달하는 언패킹 문법
    #   result = {"pages": [...], "total": 1, "success_count": 1, "failed_pages": []}
    #   OCRResponse(filename=file.filename, **result)
    #   = OCRResponse(filename=..., pages=..., total=..., success_count=..., failed_pages=...)
    return OCRResponse(filename=file.filename, **result)


async def _handle_pdf(file: UploadFile) -> dict:
    """
    PDF를 임시 파일로 저장한 뒤 extractor.extract_parallel()에 경로를 전달한다.
    처리 완료 후 임시 파일은 반드시 삭제한다.
    """
    # ---------------------------------------------------------------
    # import를 함수 안에 쓰는 이유:
    #   os, tempfile은 PDF 처리에만 필요한 모듈이다.
    #   함수 안에 import 하면 PDF 요청이 있을 때만 모듈이 로드되고,
    #   이미지 요청에서는 불필요한 모듈을 로드하지 않아도 된다.
    #   (성능보다는 의도를 명확히 하는 스타일 선택)
    # ---------------------------------------------------------------
    import os
    import tempfile
    # tempfile : 임시 파일을 안전하게 생성하는 파이썬 표준 라이브러리
    # os       : 파일 삭제(os.remove) 등 OS 작업에 사용

    contents = await file.read()
    # PDF 파일의 내용을 bytes로 읽음

    # ---------------------------------------------------------------
    # 임시 파일 생성
    # Marker(구버전)에서 Tesseract 기반 extractor로 교체됐지만
    # extract_parallel()도 파일 경로를 필요로 하므로 임시 파일은 여전히 필요하다.
    #
    # with 블록:
    #   파일을 열고, with 블록이 끝나면 자동으로 파일을 닫아준다.
    #   비유: 냉장고 문을 열고 물건을 넣은 뒤 자동으로 닫히는 것.
    #
    # delete=False : with 블록 종료 시 자동 삭제 안 함.
    #   아래 try 블록에서 파일 경로(tmp_path)를 다시 써야 하므로
    #   자동 삭제를 막고 finally에서 직접 삭제한다.
    # ---------------------------------------------------------------
    with tempfile.NamedTemporaryFile(
        dir="temp", suffix=".pdf", delete=False
    ) as tmp:
        tmp.write(contents)   # 메모리의 bytes를 임시 파일에 저장
        tmp_path = tmp.name   # 임시 파일의 전체 경로를 기억
                              # 예) "temp/tmpXk39ab.pdf"

    # ---------------------------------------------------------------
    # try / finally 패턴
    #
    # try    : 실제 PDF 변환 시도
    # finally: 성공하든 실패(에러)하든 임시 파일은 반드시 삭제
    #
    # finally가 없으면 convert 중 에러가 발생할 때
    # os.remove()가 실행되지 않아 임시 파일이 계속 쌓인다 → 디스크 부족 위험
    # ---------------------------------------------------------------
    try:
        return extract_parallel(tmp_path)
        # extract_parallel() : extractor.py에 있는 PDF 병렬 처리 함수
        # dict를 반환 → 위 upload_file에서 **result 로 언패킹됨
    finally:
        os.remove(tmp_path)
        # 성공이든 실패든 임시 파일을 무조건 삭제
