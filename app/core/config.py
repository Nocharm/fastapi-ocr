import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 파일에서 읽어오는 앱 설정. 없으면 기본값 사용."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    upload_dir: str = "uploads"         # 업로드 파일 저장 경로
    temp_dir:   str = "temp"            # PDF 임시 파일 저장 경로

    # --- Tesseract / 하이브리드 OCR 튜닝값 ---
    # [변경 이력] easyocr_languages 필드 제거 (EasyOCR 제거됨)
    ocr_text_threshold: int = 50
    # pdfplumber 추출 텍스트가 이 글자 수 미만이면 Tesseract OCR 폴백으로 전환.

    ocr_max_workers: int = 4
    # PDF 페이지 병렬 처리 스레드 수. CPU 코어 수를 초과하면 역효과.

    ocr_word_conf_min: int = 30
    # Tesseract 단어 신뢰도(0~100) 최솟값. 미만 단어는 결과에서 제외.

    tesseract_cmd: str = ""
    # Tesseract 실행 파일 경로. 빈 문자열이면 시스템 PATH 자동 탐색.

    # --- 서버 환경 설정 ---
    omp_num_threads: int = 1
    # OpenMP 스레드 수. ThreadPoolExecutor와 충돌 방지용. Dockerfile ENV 폴백과 맞춰야 한다.

    # --- PDF / OCR 튜닝 ---
    pdf_dpi: int = 300
    # PDF→이미지 변환 해상도. 낮추면 빠르지만 OCR 정확도 하락.

    tesseract_config: str = "--psm 6 --oem 3 -c preserve_interword_spaces=1"
    # --psm 6: 단일 균일 텍스트 블록 분석. --oem 3: LSTM 자동 선택.

    tesseract_lang: str = "kor+eng"
    # 인식 언어. 추가 언어는 tesseract-ocr-<lang> 패키지 설치 필요.

    # --- 비즈니스 로직 상수 ---
    confidence_thresholds: dict[str, int] = Field(
        default={"high": 80, "medium": 60, "low": 40, "very_low": 0},
        frozen=True,
    )
    # 신뢰도 등급 경계. .env 오버라이드 금지 — JSON 파싱 실패로 앱 시작 불가.
    # 변경하려면 이 기본값을 직접 수정한다.


settings = Settings()

if settings.tesseract_cmd:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

# OMP_NUM_THREADS=1: ThreadPoolExecutor(외부)와 Tesseract 내부 OpenMP 스레드가
# 동시에 돌면 경쟁으로 성능 저하 또는 충돌이 발생한다.
# setdefault: 이미 설정된 값은 덮어쓰지 않음.
os.environ.setdefault("OMP_NUM_THREADS", str(settings.omp_num_threads))


# --- 런타임에 변경되지 않는 상수 ---

CONFIDENCE_THRESHOLDS: dict[str, int] = {
    "high":     80,   # 신뢰할 수 있음
    "medium":   60,   # 수용 가능
    "low":      40,   # 재처리 권장
    "very_low":  0,   # 반드시 검토 필요
}

TESSERACT_CONFIG = "--psm 6 --oem 3 -c preserve_interword_spaces=1"
# --psm 6: 단일 균일 텍스트 블록으로 분석 (다중 줄 문서에 적합)
# --oem 3: LSTM OCR 엔진 자동 선택
# preserve_interword_spaces=1: 단어 사이 공백 보존 (표·컬럼 정렬 유지)

TESSERACT_LANG = "kor+eng"  # 한국어 + 영어 동시 인식
