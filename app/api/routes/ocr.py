"""
app/api/routes/ocr.py — OCR 업로드 라우터.
HTTP 레이어: 파일 유효성 검사 후 서비스 계층으로 위임. 직접 OCR 로직 금지.

[변경 이력] EasyOCR 제거 → 이미지 요청 시 HTTP 501 반환, VLM으로 대체 예정.
"""
from fastapi import APIRouter, File, HTTPException, UploadFile
from app.schemas.ocr import OCRResponse
from app.services.extractor import extract_parallel

router = APIRouter()

# 이미지 타입은 현재 미지원 (EasyOCR 제거됨, VLM 연동 예정).
# 에러 메시지에 포함해 클라이언트에게 안내하기 위해 선언만 유지.
ALLOWED_IMAGE_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
ALLOWED_PDF_TYPES:   set[str] = {"application/pdf"}
MAX_FILE_SIZE:       int      = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", response_model=OCRResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    파일 업로드 → OCR 결과를 페이지별 JSON으로 반환.

    지원: PDF (pdfplumber + Tesseract 하이브리드)
    미지원: 이미지 → HTTP 501 (VLM 연동 예정)
    """
    # Content-Length 헤더 기반 사전 검증. 헤더 없으면 file.size == None → 스킵.
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max allowed size is {MAX_FILE_SIZE // 1024 // 1024} MB.",
        )

    content_type = file.content_type

    if content_type in ALLOWED_IMAGE_TYPES:
        # 501 Not Implemented: 기능 존재하나 미구현 상태임을 명시.
        # 415(미지원 타입)와 달리 향후 구현 예정임을 나타낸다.
        raise HTTPException(
            status_code=501,
            detail=(
                f"Image OCR ({content_type}) is not yet implemented. "
                "EasyOCR has been removed. VLM-based image OCR is coming soon."
            ),
        )

    elif content_type in ALLOWED_PDF_TYPES:
        result = await _process_pdf(file)

    else:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type: {content_type}. "
                f"Allowed: {ALLOWED_PDF_TYPES}. "
                f"Image types {ALLOWED_IMAGE_TYPES} are planned (VLM, coming soon)."
            ),
        )

    return OCRResponse(filename=file.filename, **result)


async def _process_pdf(file: UploadFile) -> dict:
    """
    PDF를 임시 파일로 저장 후 extract_parallel()에 경로 전달.

    extract_parallel()은 파일 경로(str)를 입력으로 받으므로
    UploadFile(메모리 스트림)을 디스크에 한 번 써야 한다.
    finally로 성공/실패 여부와 무관하게 임시 파일을 반드시 삭제한다.
    """
    import os
    import tempfile

    contents = await file.read()

    with tempfile.NamedTemporaryFile(dir="temp", suffix=".pdf", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        return extract_parallel(tmp_path)
    finally:
        os.remove(tmp_path)
