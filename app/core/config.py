# =====================================================================
# [읽기 순서 2/7] app/core/config.py
#
# 이 파일의 역할:
#   앱 전체에서 사용하는 설정값과 상수를 한 곳에서 관리한다.
#   설정값은 .env 파일에서 읽어오며, 없으면 기본값을 사용한다.
#
# ┌─────────────────────────────────────────────────────────┐
# │  비유: 음식점의 "운영 매뉴얼 + 조리 기준표"              │
# │                                                         │
# │  Settings = 변경 가능한 운영 정책                        │
# │    (영업시간, 테이블 수처럼 필요시 바꿀 수 있는 것)      │
# │                                                         │
# │  CONFIDENCE_THRESHOLDS, TESSERACT_CONFIG = 조리 기준표  │
# │    (레시피처럼 런타임에 절대 바뀌지 않는 고정 값)        │
# │                                                         │
# │  직원들은 매번 사장한테 묻는 대신 이 문서를 보면 된다.  │
# └─────────────────────────────────────────────────────────┘
#
# .env 파일이란?
#   환경변수를 저장하는 텍스트 파일.
#   코드를 수정하지 않고 외부 파일만 바꿔서 동작을 바꿀 수 있다.
#   비밀번호, API 키 같은 민감한 값도 코드 밖으로 분리할 수 있어 보안에 유리하다.
#   .gitignore에 .env를 추가하면 깃허브에 올라가지 않는다.
# =====================================================================

import os
# os : 운영체제(Operating System) 기능을 파이썬에서 사용하는 표준 라이브러리.
# 여기서는 환경변수 설정(os.environ.setdefault)에 사용.

from pydantic_settings import BaseSettings, SettingsConfigDict
# pydantic_settings : .env 파일의 값을 파이썬 클래스 필드에 자동으로 연결해주는 라이브러리.
# SettingsConfigDict : 설정 방식(어떤 파일을 읽을지 등)을 명시하는 딕셔너리 타입.


class Settings(BaseSettings):
    # BaseSettings를 상속하면 .env 파일을 자동으로 읽어서
    # 아래 필드들을 채워준다.

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # model_config : Pydantic v2 방식의 설정 선언.
    #   env_file=".env"    : 프로젝트 루트의 .env 파일을 읽음
    #   extra="ignore"     : .env에 이 클래스에 없는 항목이 있어도 에러 없이 무시
    #                        비유: 매뉴얼에 없는 질문이 들어와도 그냥 넘어가는 것

    upload_dir: str = "uploads"
    # 업로드된 파일을 저장할 폴더 경로 (기본: "uploads")
    # .env에 UPLOAD_DIR=my_folder 라고 쓰면 "my_folder"로 바뀜

    temp_dir:   str = "temp"
    # PDF 처리 중 임시 파일을 저장할 폴더 경로 (기본: "temp")
    # Tesseract/pdfplumber는 파일 경로를 입력으로 받아서 임시 파일이 필요함

    # ---------------------------------------------------------------
    # EasyOCR 설정
    # ---------------------------------------------------------------
    easyocr_languages: list[str] = ["en", "ko"]
    # EasyOCR이 인식할 언어 목록.
    # "en" = 영어, "ko" = 한국어
    # 언어를 추가할수록 모델이 커지고 로딩 시간이 늘어남

    # ---------------------------------------------------------------
    # Tesseract / 하이브리드 OCR 튜닝값
    # 이 값들은 .env 파일로만 변경해야 한다. 코드에 하드코딩 금지.
    # ---------------------------------------------------------------
    ocr_text_threshold: int = 50
    # 직접 추출(pdfplumber)로 얻은 텍스트가 이 글자 수 미만이면
    # OCR 폴백(Tesseract)으로 재처리한다.
    # 예) 50 → 50자 미만이면 "이 페이지는 스캔된 이미지겠구나"로 판단

    ocr_max_workers:    int = 4
    # PDF 페이지를 병렬 처리할 때 사용하는 스레드 수.
    # 숫자가 클수록 빠르지만 메모리 사용량도 커짐.
    # CPU 코어 수를 초과하면 오히려 느려질 수 있음.

    ocr_word_conf_min:  int = 30
    # Tesseract가 인식한 단어 중 신뢰도가 이 값 미만이면 결과에서 제외.
    # 0~100 기준. 30 = "30% 미만의 확신으로 인식한 단어는 버린다"
    # 비유: 들릴 듯 말 듯 한 말은 받아 적지 않는 것

    tesseract_cmd:      str = ""
    # Tesseract 실행 파일의 절대 경로.
    # 빈 문자열("")이면 시스템 PATH에서 자동으로 찾음.
    # Windows에서 설치 경로가 다를 경우 직접 지정:
    # 예) TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe


# ---------------------------------------------------------------
# 싱글턴 인스턴스 생성
# 모든 파일에서 이 객체를 import해서 사용한다.
#   from app.core.config import settings
#   print(settings.temp_dir)  # "temp"
# ---------------------------------------------------------------
settings = Settings()

# Tesseract 실행 파일 경로 오버라이드
# tesseract_cmd 가 설정된 경우에만 실행 (빈 문자열이면 if 조건 False → 스킵)
if settings.tesseract_cmd:
    import pytesseract
    # pytesseract : Tesseract OCR 엔진을 파이썬에서 호출하는 라이브러리
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    # pytesseract 라이브러리에게 "이 경로에 있는 tesseract를 써라" 고 알려줌

# Tesseract 내부 스레드 수 제한
# ---------------------------------------------------------------
# 왜 필요한가?
#   extractor.py에서 ThreadPoolExecutor로 여러 페이지를 병렬 처리한다.
#   Tesseract도 내부적으로 멀티스레드(OpenMP)를 사용하는데,
#   두 스레드 풀이 동시에 돌면 서로 경쟁해서 성능이 오히려 나빠지거나 충돌할 수 있다.
#   OMP_THREAD_LIMIT=1 로 Tesseract 내부 스레드를 1개로 제한하면
#   외부 ThreadPoolExecutor가 전체 병렬성을 제어하게 된다.
#
# os.environ.setdefault(key, value):
#   환경변수 key가 없을 때만 value로 설정한다.
#   이미 다른 값이 설정되어 있으면 덮어쓰지 않는다.
#   비유: "이미 메모가 있으면 그냥 두고, 없으면 이 내용을 적어두는 것"
# ---------------------------------------------------------------
os.environ.setdefault("OMP_THREAD_LIMIT", "1")


# ================================================================
# 상수 (Constants)
# Settings와 달리 런타임에 절대 변경되지 않는 고정 값
# ================================================================

CONFIDENCE_THRESHOLDS: dict[str, int] = {
    "high":     80,   # 신뢰할 수 있음 → 그대로 사용
    "medium":   60,   # 수용 가능      → 검토 권장
    "low":      40,   # 품질 낮음      → 재처리 권장
    "very_low":  0,   # 매우 낮음      → 반드시 경고 처리
}
# 신뢰도 점수(0~100)를 등급 이름으로 매핑하는 딕셔너리.
# extractor.py의 _classify_quality() 함수에서 이 값을 참조한다.
#
# 비유: 성적 등급표
#   80점 이상 = A (high), 60점 이상 = B (medium), ...
#
# 타입 힌트 dict[str, int]:
#   키(str) 와 값(int)으로 이뤄진 딕셔너리라는 선언.
#   예) {"high": 80} → 키 "high"는 str, 값 80은 int

TESSERACT_CONFIG = "--psm 6 --oem 3 -c preserve_interword_spaces=1"
# Tesseract OCR 실행 시 전달하는 CLI 옵션 문자열.
#
# --psm 6 : Page Segmentation Mode 6 = "단일 균일 텍스트 블록으로 가정"
#           문서처럼 여러 줄로 된 텍스트를 분석할 때 적합.
#           (PSM 종류: 0~13, 기본은 3)
#
# --oem 3 : OCR Engine Mode 3 = LSTM 엔진만 사용 (최신 딥러닝 방식)
#           OEM 0 = 구형 방식, OEM 1 = LSTM, OEM 3 = 자동 선택
#
# preserve_interword_spaces=1 : 단어 사이 공백을 최대한 보존.
#           표나 컬럼 구분이 있는 문서에서 정렬을 유지하기 위해 필요.

TESSERACT_LANG = "kor+eng"
# Tesseract OCR 인식 언어.
# "kor+eng" : 한국어와 영어를 동시에 인식.
# "+" 로 연결하면 복수 언어를 함께 사용할 수 있다.
# 언어 데이터 파일(.traineddata)이 Tesseract 설치 폴더에 있어야 한다.
