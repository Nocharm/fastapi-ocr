# =====================================================================
# [읽기 순서 4/6] app/api/routes/ocr.py
#
# 이 파일의 역할:
#   클라이언트의 HTTP 요청을 받아서 알맞은 서비스로 넘겨주는 역할.
#   비즈니스 로직(OCR 처리)은 services/ 에 위임하고,
#   이 파일은 "요청을 받고 → 분기하고 → 응답을 돌려주는 것"만 담당한다.
#
# ┌─────────────────────────────────────────────────────────┐
# │  비유: 음식점의 "홀 직원"                                │
# │                                                         │
# │  손님(클라이언트)이 주문(요청)을 하면                    │
# │  홀 직원(routes/ocr.py)이 주문을 받아서                 │
# │  주방(services/)에 넘겨주고                             │
# │  완성된 음식(응답)을 손님에게 가져다 준다.               │
# │                                                         │
# │  홀 직원은 요리를 직접 하지 않는다.                     │
# └─────────────────────────────────────────────────────────┘
#
# ---------------------------------------------------------------
# APIRouter란?
#   FastAPI 앱을 여러 파일로 나눠서 관리할 수 있게 해주는 도구.
#
#   비유: 백화점의 "층별 안내"
#     백화점(app) 전체를 한 파일에 다 쓰면 너무 복잡해진다.
#     그래서 1층(ocr), 2층(user), 3층(admin) 처럼 층별로 나누고
#     각 층의 안내 데스크(APIRouter)가 그 층의 요청만 처리한다.
#     main.py의 app.include_router()가 "이 층도 우리 백화점 소속이야"
#     라고 등록해주는 역할을 한다.
#
# ---------------------------------------------------------------
# async / await란?
#   파일 읽기, 네트워크 요청처럼 "기다려야 하는 작업"을 처리할 때 사용.
#
#   비유: 카페 직원의 업무 방식
#     [동기 방식 - await 없음]
#       손님 A 커피 주문 → 커피 나올 때까지 멍하니 기다림 → 손님 B 주문 받음
#
#     [비동기 방식 - await 사용]
#       손님 A 커피 주문 → 커피 기계 작동시켜 두고 → 손님 B 주문 받음
#                       → 커피 완성되면 돌아와서 손님 A에게 전달
#
#     await를 쓰면 "기다리는 시간"에 다른 요청을 처리할 수 있어서
#     서버가 훨씬 효율적으로 동작한다.
# =====================================================================

from fastapi import APIRouter, UploadFile, File, HTTPException
# APIRouter   : 라우터 객체 생성에 사용 (층별 안내 데스크)
# UploadFile  : 업로드된 파일 객체 타입 (파일명, MIME 타입, 내용 등을 담고 있음)
# File        : 이 파라미터가 form-data의 파일 필드임을 FastAPI에게 알려주는 선언자
# HTTPException : HTTP 에러 응답을 발생시킬 때 사용
#               비유: 홀 직원이 "죄송합니다, 저희 메뉴에 없는 음식입니다"라고 말하는 것

from app.schemas.ocr import OCRResponse          # 응답 데이터 구조 (schemas/ocr.py)
from app.services.easyocr_service import extract_image  # 이미지 OCR 처리 함수
from app.services.marker_service import extract_pdf     # PDF OCR 처리 함수


# 이 파일의 라우터(안내 데스크) 인스턴스 생성
# main.py에서 app.include_router()로 등록하면 앱의 일부가 됨
router = APIRouter()


# 허용하는 MIME 타입 목록
# MIME 타입: 파일 종류를 나타내는 표준 문자열
#
# 비유: 음식점의 "취급 메뉴판"
#   이미지 메뉴 : jpeg, png, webp, tiff
#   PDF 메뉴   : pdf
#   그 외       : "저희 메뉴에 없습니다" (415 에러)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
ALLOWED_PDF_TYPES = {"application/pdf"}


# ---------------------------------------------------------------
# @router.post("/upload", response_model=OCRResponse)
#
# @ 로 시작하는 문법을 "데코레이터"라고 한다.
# 함수 바로 위에 붙여서 그 함수에 추가 기능을 부여하는 문법.
#
# 비유: 문 앞의 "안내판"
#   @router.post("/upload") 는
#   "/upload 문으로 POST 방식 손님이 오면 아래 함수를 실행하세요"
#   라는 안내판을 붙이는 것.
#
# HTTP 메서드란?
#   GET  : 데이터를 "조회"할 때 사용 (예: 웹페이지 열기)
#   POST : 데이터를 "전송"할 때 사용 (예: 파일 업로드, 로그인)
#   PUT  : 데이터를 "수정"할 때 사용
#   DELETE : 데이터를 "삭제"할 때 사용
#   → 파일을 서버로 보내는 행위는 POST가 적합하다.
#
# prefix 적용 후 실제 경로:
#   main.py에서 prefix="/ocr"을 붙였으므로
#   "/upload" → 실제 요청 경로는 POST /ocr/upload
#
# response_model=OCRResponse:
#   이 함수가 반환하는 데이터를 OCRResponse 구조로 검증 후 JSON으로 응답
#   비유: 음식이 나올 때 "정해진 그릇(OCRResponse)"에 담아서 내보내는 것
# ---------------------------------------------------------------
@router.post("/upload", response_model=OCRResponse)
async def upload_file(file: UploadFile = File(...)):
    # ---------------------------------------------------------------
    # 파라미터 설명: file: UploadFile = File(...)
    #
    # 비유: 택배 접수창구
    #   File(...)     : "이 창구는 택배(파일)만 받습니다"라는 안내
    #   UploadFile    : 접수된 택배 상자. 안에 아래 정보가 들어있음
    #                   - file.filename    : 파일 이름 (예: "resume.pdf")
    #                   - file.content_type: 파일 종류 (예: "application/pdf")
    #                   - file.read()      : 파일 내용 (실제 바이트 데이터)
    #   File(...)의 ... : 파이썬에서 "필수값"을 나타내는 Ellipsis 문법.
    #                     파일 없이 요청하면 FastAPI가 자동으로 422 에러를 반환함.
    #
    # multipart/form-data란?
    #   파일을 HTTP로 전송하는 표준 방식.
    #   브라우저에서 <input type="file">로 업로드하거나
    #   curl -F "file=@photo.jpg" 로 전송할 때 이 형식이 사용됨.
    # ---------------------------------------------------------------

    content_type = file.content_type  # 업로드된 파일의 MIME 타입 확인
    # 예) JPEG 이미지면 "image/jpeg", PDF면 "application/pdf"

    # 파일 종류에 따라 알맞은 주방(service)으로 주문을 넘김
    if content_type in ALLOWED_IMAGE_TYPES:
        # 이미지 파일 → EasyOCR 서비스로 처리
        # await : extract_image()가 파일을 읽는 동안 다른 요청도 처리 가능
        result = await extract_image(file)

    elif content_type in ALLOWED_PDF_TYPES:
        # PDF 파일 → Marker 서비스로 처리
        result = await extract_pdf(file)

    else:
        # 허용되지 않은 파일 형식
        # raise : 에러를 "던진다". 이 시점에서 함수 실행이 즉시 중단됨.
        # HTTPException : FastAPI가 자동으로 아래 형식의 JSON 에러를 만들어 응답
        #   → HTTP 415 응답: { "detail": "Unsupported file type: text/plain" }
        #
        # 비유: 음식점에서 "저희는 피자만 팝니다. 치킨은 취급 안 합니다."
        raise HTTPException(
            status_code=415,  # 415 = Unsupported Media Type (표준 HTTP 상태 코드)
            detail=f"Unsupported file type: {content_type}"
        )

    # OCRResponse 객체를 반환하면 FastAPI가 JSON으로 변환해서 클라이언트에게 응답
    # response_model=OCRResponse 덕분에 구조가 맞는지 자동 검증도 해줌
    # 최종 응답 예시:
    #   {
    #     "filename": "sample.png",
    #     "markdown": "## 제목\n\n본문 텍스트..."
    #   }
    return OCRResponse(filename=file.filename, markdown=result)
