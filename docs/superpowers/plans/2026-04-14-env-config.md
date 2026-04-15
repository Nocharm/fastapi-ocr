# .env 설정 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 하드코딩된 설정값(`TESSERACT_CONFIG`, `TESSERACT_LANG`, `CONFIDENCE_THRESHOLDS`, `dpi=300`, `OMP_NUM_THREADS`)을 모두 `Settings` 또는 `.env`로 이동해 단일 진실 공급원을 확립한다.

**Architecture:** `Settings` 필드에 기본값을 정의하고 `.env`에서 오버라이드한다. 환경 설정(`PORT`, `OMP_NUM_THREADS`)은 Dockerfile `ENV`도 함께 유지한다(폴백용). `extractor.py`는 모듈 상수 대신 `settings.*`를 직접 참조한다.

**Tech Stack:** Pydantic Settings v2, python-dotenv, Docker Compose variable substitution

---

## File Map

| 파일 | 변경 내용 |
|---|---|
| `CLAUDE.md` | 9번 섹션 추가 — `.env` 활용 규칙 |
| `app/core/config.py` | `Settings`에 5개 필드 추가; 모듈 상수 3개 제거 |
| `.env` | `OMP_NUM_THREADS`, `PDF_DPI`, `TESSERACT_CONFIG`, `TESSERACT_LANG` 추가 |
| `Dockerfile` | `OMP_NUM_THREADS` 폴백 유지, 주석 보강 |
| `app/services/extractor.py` | 모듈 상수 import 제거, `settings.*` 참조로 교체 |
| `tests/test_ocr.py` | Settings 필드 검증 테스트 추가 |

---

## Task 1: CLAUDE.md에 `.env` 활용 규칙 추가

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: CLAUDE.md 섹션 9 추가**

`## 8. 환경변수 규칙` 뒤에 아래 섹션을 추가한다.

```markdown
---

## 9. 설정값 관리 규칙 — `.env` 단일 진실 공급원

새 설정값을 추가할 때 아래 3가지 중 하나로 분류하고 지정된 위치에만 배치한다.

| 분류 | 판단 기준 | 배치 |
|---|---|---|
| **환경 설정** | 서버·배포 환경마다 다를 수 있는 값 | `.env` + `Settings` + Dockerfile `ENV`(폴백) + docker-compose `${VAR}` |
| **튜닝 파라미터** | 기본값은 있지만 코드 수정 없이 조정 가능한 값 | `.env` + `Settings` |
| **비즈니스 로직 상수** | 앱의 분류 경계를 정의하는 값. 배포 환경과 무관 | `Settings` 필드 기본값만 (`.env` 항목 없음) |

**판단 질문:**
- "다른 서버에 배포할 때 이 값을 바꿔야 하나?" → 환경 설정
- "코드 수정 없이 성능·동작을 튜닝하고 싶을 수 있나?" → 튜닝 파라미터
- "이 값이 바뀌면 앱의 분류 로직 자체가 바뀌나?" → 비즈니스 로직 상수

### 분류별 배치 패턴

**환경 설정 — 4단계 연동**
```plaintext
# 1. .env — 단일 진실 공급원
PORT=8900

# 2. config.py Settings 필드
port: int = 8900

# 3. Dockerfile — .env 없을 때 폴백
ENV PORT=8900

# 4. docker-compose.yml — .env 값 참조
"${PORT:-8900}:${PORT:-8900}"
```

**튜닝 파라미터 — 2단계**
```plaintext
# 1. .env — 값 노출 (Settings 기본값에만 숨기지 않는다)
PDF_DPI=300

# 2. config.py Settings 필드
pdf_dpi: int = 300
```

**비즈니스 로직 상수 — Settings 필드만**
```python
# config.py — .env 항목 없음
confidence_thresholds: dict[str, int] = {
    "high": 80, "medium": 60, "low": 40, "very_low": 0
}
```

### 금지 사항

- 수치·경로를 `.py` 코드 안에 리터럴로 직접 쓰기
- 튜닝 파라미터를 `Settings` 기본값에만 숨기고 `.env`에 미노출
- `config.py` 모듈 상수(`UPPER_SNAKE_CASE`)와 `Settings` 필드에 같은 값 중복 정의
- Docker 관련 환경 설정을 `Dockerfile`에만 하드코딩하고 `.env` 미연동
```

- [ ] **Step 2: 커밋**

```bash
git add CLAUDE.md
git commit -m "docs: add .env single source of truth rule to CLAUDE.md"
```

---

## Task 2: Settings에 신규 필드 5개 추가 (TDD)

**Files:**
- Modify: `app/core/config.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ocr.py` 하단에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_settings_has_pdf_dpi -v
```
Expected: `FAILED` — `Settings object has no attribute 'pdf_dpi'`

- [ ] **Step 3: config.py에 5개 필드 추가**

`app/core/config.py`의 `Settings` 클래스 안 `tesseract_cmd` 필드 다음에 추가:

```python
    pdf_dpi: int = 300
    # PDF→이미지 변환 해상도. 낮추면 빠르지만 OCR 정확도 하락.

    omp_num_threads: int = 1
    # OpenMP 스레드 수. ThreadPoolExecutor와 충돌 방지용. Dockerfile ENV 폴백과 맞춰야 한다.

    tesseract_config: str = "--psm 6 --oem 3 -c preserve_interword_spaces=1"
    # --psm 6: 단일 균일 텍스트 블록 분석. --oem 3: LSTM 자동 선택.

    tesseract_lang: str = "kor+eng"
    # 인식 언어. 추가 언어는 tesseract-ocr-<lang> 패키지 설치 필요.

    confidence_thresholds: dict[str, int] = {
        "high": 80, "medium": 60, "low": 40, "very_low": 0
    }
    # 신뢰도 등급 경계. 분류 로직 자체이므로 .env에서 오버라이드하지 않는다.
```

그리고 `os.environ.setdefault` 라인을 아래처럼 교체해 settings 값을 사용하도록 한다:

```python
os.environ.setdefault("OMP_NUM_THREADS", str(settings.omp_num_threads))
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py -v
```
Expected: 모든 테스트 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add app/core/config.py tests/test_ocr.py
git commit -m "feat: add pdf_dpi, omp_num_threads, tesseract_config, tesseract_lang, confidence_thresholds to Settings"
```

---

## Task 3: extractor.py 모듈 상수 참조를 settings로 교체

**Files:**
- Modify: `app/services/extractor.py`

- [ ] **Step 1: import 블록 수정**

`extractor.py` 상단 import를 아래처럼 교체한다:

```python
# 변경 전
from app.core.config import (
    CONFIDENCE_THRESHOLDS,
    TESSERACT_CONFIG,
    TESSERACT_LANG,
    settings,
)

# 변경 후
from app.core.config import settings
```

- [ ] **Step 2: run_ocr() 내 상수 참조 교체**

`run_ocr()` 함수 안 `pytesseract.image_to_data()` 호출 부분:

```python
# 변경 전
data = pytesseract.image_to_data(
    preprocessed,
    lang=TESSERACT_LANG,
    config=TESSERACT_CONFIG,
    output_type=Output.DICT,
)

# 변경 후
data = pytesseract.image_to_data(
    preprocessed,
    lang=settings.tesseract_lang,
    config=settings.tesseract_config,
    output_type=Output.DICT,
)
```

- [ ] **Step 3: _get_quality_flag() 내 상수 참조 교체**

```python
# 변경 전
def _get_quality_flag(avg_conf: float) -> str:
    """신뢰도 점수를 등급 문자열로 변환."""
    if avg_conf >= CONFIDENCE_THRESHOLDS["high"]:   return "high"
    if avg_conf >= CONFIDENCE_THRESHOLDS["medium"]: return "medium"
    if avg_conf >= CONFIDENCE_THRESHOLDS["low"]:    return "low"
    return "very_low"

# 변경 후
def _get_quality_flag(avg_conf: float) -> str:
    """신뢰도 점수를 등급 문자열로 변환."""
    ct = settings.confidence_thresholds
    if avg_conf >= ct["high"]:   return "high"
    if avg_conf >= ct["medium"]: return "medium"
    if avg_conf >= ct["low"]:    return "low"
    return "very_low"
```

- [ ] **Step 4: extract_tables() 내 TESSERACT_LANG 참조 교체**

`extract_tables()` 함수 안 Stage 3 OCR 부분:

```python
# 변경 전
ocr_text = pytesseract.image_to_string(crop, lang=TESSERACT_LANG)

# 변경 후
ocr_text = pytesseract.image_to_string(crop, lang=settings.tesseract_lang)
```

- [ ] **Step 5: _get_page_image() 내 dpi 하드코딩 교체**

```python
# 변경 전
images = convert_from_path(
    pdf_path,
    first_page=page_num + 1,
    last_page=page_num + 1,
    dpi=300,
    # dpi 300: 고해상도 스캔 수준. 낮추면 빠르지만 OCR 정확도가 떨어진다.
)

# 변경 후
images = convert_from_path(
    pdf_path,
    first_page=page_num + 1,
    last_page=page_num + 1,
    dpi=settings.pdf_dpi,
    # .env의 PDF_DPI로 조정. 낮추면 빠르지만 OCR 정확도가 떨어진다.
)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py -v
```
Expected: 모든 테스트 `PASSED`

- [ ] **Step 7: 커밋**

```bash
git add app/services/extractor.py
git commit -m "refactor: replace module constants with settings.* in extractor.py"
```

---

## Task 4: config.py 모듈 상수 3개 제거

**Files:**
- Modify: `app/core/config.py`

이 태스크는 더 이상 참조되지 않는 모듈 상수를 삭제한다.
Task 3 완료 후 실행해야 한다.

- [ ] **Step 1: 참조 없음 확인**

```bash
grep -rn "CONFIDENCE_THRESHOLDS\|TESSERACT_CONFIG\|TESSERACT_LANG" app/
```
Expected: 아무것도 출력되지 않아야 한다.

- [ ] **Step 2: config.py에서 모듈 상수 3개 삭제**

`app/core/config.py`에서 아래 블록 전체를 삭제한다:

```python
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
```

- [ ] **Step 3: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py -v
```
Expected: 모든 테스트 `PASSED`

- [ ] **Step 4: 커밋**

```bash
git add app/core/config.py
git commit -m "refactor: remove obsolete module constants (TESSERACT_CONFIG, TESSERACT_LANG, CONFIDENCE_THRESHOLDS)"
```

---

## Task 5: .env + Dockerfile 동기화

**Files:**
- Modify: `.env`
- Modify: `Dockerfile`

- [ ] **Step 1: .env에 4개 항목 추가**

`.env`의 `# OCR 튜닝값` 섹션 앞에 아래 블록 추가:

```dotenv
# 서버 실행 환경
OMP_NUM_THREADS=1     # ThreadPoolExecutor와 OpenMP 스레드 충돌 방지. 변경 시 성능 영향.

# PDF 처리 튜닝
PDF_DPI=300           # 낮추면 속도 향상, OCR 정확도 하락

# Tesseract 설정
TESSERACT_CONFIG="--psm 6 --oem 3 -c preserve_interword_spaces=1"
TESSERACT_LANG=kor+eng
```

- [ ] **Step 2: Dockerfile OMP_NUM_THREADS 주석 보강**

Dockerfile의 `ENV OMP_NUM_THREADS=1` 줄 위 주석을 아래로 교체:

```dockerfile
# OMP_NUM_THREADS: .env 없이 실행할 때의 폴백 기본값.
# docker-compose 실행 시 .env의 OMP_NUM_THREADS 값이 이 값을 덮어쓴다.
ENV OMP_NUM_THREADS=1
```

- [ ] **Step 3: 전체 테스트 통과 확인**

```bash
pytest tests/test_ocr.py -v
```
Expected: 모든 테스트 `PASSED`

- [ ] **Step 4: 커밋**

```bash
git add .env Dockerfile
git commit -m "chore: sync OMP_NUM_THREADS, PDF_DPI, TESSERACT_CONFIG, TESSERACT_LANG to .env"
```
