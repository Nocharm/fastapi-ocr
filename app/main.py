"""
app/main.py — FastAPI 앱 진입점.
라우터 등록과 헬스체크 엔드포인트만 담당. 비즈니스 로직 금지.
"""
from fastapi import FastAPI
from app.api.routes import ocr

app = FastAPI(title="OCR API", version="0.1.0")

# /ocr 접두사로 OCR 라우터 등록. 실제 경로: /ocr/upload
app.include_router(ocr.router, prefix="/ocr", tags=["ocr"])


@app.get("/health")
def health_check():
    """Docker HEALTHCHECK 및 모니터링용 상태 확인 엔드포인트."""
    return {"status": "ok"}
