# VLM 구현 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run_vlm()`을 GPT-4V(gpt-4o)로 구현해 Tesseract 신뢰도가 very_low일 때 VLM 폴백이 실제로 동작하게 한다.

**Architecture:** `app/services/vlm.py` 내부만 채운다. 호출부(`run_ocr_with_fallback`)는 변경 없음. API 키 미설정 시 `NotImplementedError` → Tesseract 결과 유지. API 오류도 Tesseract로 폴백하도록 `extractor.py`의 except 범위를 넓힌다.

**Tech Stack:** `openai` Python SDK, GPT-4o (vision), OpenCV base64 인코딩, Pydantic Settings

---

## 파일 변경 목록

| 파일 | 역할 |
|---|---|
| `app/core/config.py` | `openai_api_key`, `vlm_model`, `vlm_max_tokens` 필드 추가 |
| `.env` | 위 3개 설정값 항목 추가 |
| `requirements.txt` | `openai` 패키지 추가 |
| `app/services/vlm.py` | `run_vlm()` 실제 구현 |
| `app/services/extractor.py` | `except NotImplementedError` → `except Exception` |
| `docker-compose.yml` | `OPENAI_API_KEY` 환경변수 참조 추가 |
| `tests/test_ocr.py` | VLM 관련 테스트 추가/갱신 |
| `tests/test_scenarios.md` | TC-15~TC-17 추가 |
| `README.md` | 환경변수 표, 이미지 지원 상태, 요청 흐름 다이어그램 갱신 |

---

### Task 1: Settings에 VLM 설정 필드 추가

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env`
- Test: `tests/test_ocr.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ocr.py` 맨 아래에 추가:

```python
# --- Settings VLM 필드 검증 ---

def test_settings_has_openai_api_key():
    """openai_api_key가 Settings에 존재하고 str 타입인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.openai_api_key, str)


def test_settings_has_vlm_model():
    """vlm_model이 Settings에 존재하고 비어있지 않은지 확인."""
    from app.core.config import settings
    assert isinstance(settings.vlm_model, str)
    assert len(settings.vlm_model) > 0


def test_settings_has_vlm_max_tokens():
    """vlm_max_tokens가 Settings에 존재하고 양수인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.vlm_max_tokens, int)
    assert settings.vlm_max_tokens > 0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_settings_has_openai_api_key tests/test_ocr.py::test_settings_has_vlm_model tests/test_ocr.py::test_settings_has_vlm_max_tokens -v
```

Expected: `FAILED` — `AttributeError: 'Settings' object has no attribute 'openai_api_key'`

- [ ] **Step 3: config.py에 필드 추가**

`app/core/config.py`의 `vlm_fallback_flags` 필드 아래에 추가:

```python
    # --- VLM 설정 ---
    openai_api_key: str = ""
    # OpenAI API 키. 비어있으면 VLM 폴백을 건너뛰고 Tesseract 결과를 유지한다.

    vlm_model: str = "gpt-4o"
    # VLM 호출에 사용할 OpenAI 모델. gpt-4o-mini로 낮추면 비용 절감, 정확도 하락.

    vlm_max_tokens: int = 1024
    # VLM 응답 최대 토큰 수. OCR 결과가 잘리면 늘린다.
```

- [ ] **Step 4: .env에 항목 추가**

`.env`의 `VLM_FALLBACK_FLAGS` 아래에 추가:

```env
# VLM (GPT-4V) 설정
OPENAI_API_KEY=           # OpenAI API 키. 비어있으면 VLM 폴백 비활성화.
VLM_MODEL=gpt-4o          # 사용할 모델. gpt-4o-mini로 낮추면 비용 절감.
VLM_MAX_TOKENS=1024       # 응답 최대 토큰. 텍스트가 잘리면 늘린다.
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_settings_has_openai_api_key tests/test_ocr.py::test_settings_has_vlm_model tests/test_ocr.py::test_settings_has_vlm_max_tokens -v
```

Expected: `PASSED`

- [ ] **Step 6: 전체 테스트 회귀 확인**

```bash
pytest tests/ -v
```

Expected: 기존 테스트 모두 `PASSED`

- [ ] **Step 7: 커밋**

```bash
git add app/core/config.py .env tests/test_ocr.py
git commit -m "feat: add VLM settings fields (openai_api_key, vlm_model, vlm_max_tokens)"
```

---

### Task 2: requirements.txt에 openai 추가

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: requirements.txt에 추가**

`pytesseract==0.3.13` 줄 아래에 추가:

```
# --- VLM (GPT-4V) ---
openai>=1.30.0              # OpenAI Python SDK. GPT-4V API 호출에 사용.
```

- [ ] **Step 2: 패키지 설치**

```bash
pip install openai
```

Expected: `Successfully installed openai-...`

- [ ] **Step 3: 커밋**

```bash
git add requirements.txt
git commit -m "feat: add openai package for GPT-4V VLM integration"
```

---

### Task 3: run_vlm() 구현

**Files:**
- Modify: `app/services/vlm.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ocr.py`의 `test_run_vlm_raises_not_implemented` 함수를 아래로 교체하고, 신규 테스트를 추가한다:

```python
# --- run_vlm() 단위 테스트 ---

def test_run_vlm_raises_not_implemented_without_api_key(monkeypatch):
    """API 키 미설정 시 NotImplementedError → 호출부에서 Tesseract 결과 유지."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "openai_api_key", "")
    from app.services.vlm import run_vlm
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(NotImplementedError):
        run_vlm(image)


def test_get_vlm_confidence_zero():
    """빈 텍스트 → confidence=0.0."""
    from app.services.vlm import _get_vlm_confidence
    assert _get_vlm_confidence("") == 0.0


def test_get_vlm_confidence_half():
    """250자 텍스트 → confidence=50.0 (상한 500자 기준)."""
    from app.services.vlm import _get_vlm_confidence
    assert _get_vlm_confidence("x" * 250) == 50.0


def test_get_vlm_confidence_max():
    """500자 이상 텍스트 → confidence=100.0 (상한 초과 시 고정)."""
    from app.services.vlm import _get_vlm_confidence
    assert _get_vlm_confidence("x" * 600) == 100.0


def test_run_vlm_returns_correct_structure(monkeypatch):
    """API 키 설정 + mock 응답 → {"text", "confidence", "quality_flag"} 구조 반환."""
    from unittest.mock import MagicMock, patch
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.settings, "vlm_model", "gpt-4o")
    monkeypatch.setattr(cfg.settings, "vlm_max_tokens", 1024)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "x" * 400  # 400자 → confidence=80.0, flag="high"

    from app.services.vlm import run_vlm
    image = np.zeros((10, 10, 3), dtype=np.uint8)

    with patch("openai.OpenAI") as mock_openai_cls:
        # openai.OpenAI를 패치해야 함수 내부 lazy import에서도 mock이 적용된다.
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        result = run_vlm(image)

    assert "text" in result
    assert "confidence" in result
    assert "quality_flag" in result
    assert result["text"] == "x" * 400
    assert result["confidence"] == 80.0
    assert result["quality_flag"] == "high"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_run_vlm_raises_not_implemented_without_api_key tests/test_ocr.py::test_get_vlm_confidence_zero tests/test_ocr.py::test_get_vlm_confidence_half tests/test_ocr.py::test_get_vlm_confidence_max tests/test_ocr.py::test_run_vlm_returns_correct_structure -v
```

Expected: `FAILED` — `ImportError: cannot import name '_get_vlm_confidence'`

- [ ] **Step 3: vlm.py 구현**

`app/services/vlm.py` 전체를 교체:

```python
"""app/services/vlm.py — VLM 엔진 인터페이스.

현재 구현: OpenAI GPT-4V (gpt-4o).
로컬 Qwen 모델로 전환 시 run_vlm() 내부만 교체한다. 호출부 수정 불필요.
"""
import base64

import cv2
import numpy as np

from app.core.config import settings

# 신뢰도 100에 대응하는 텍스트 길이 상한 (문자 수)
# 실제 문서는 수백~수천 자이므로 500자를 넘으면 충분히 추출된 것으로 간주한다.
VLM_CONF_TEXT_LIMIT = 500

_OCR_SYSTEM_PROMPT = (
    "You are an OCR engine. Extract all text from the image exactly as it appears.\n"
    "- Preserve the original layout, line breaks, and spacing.\n"
    "- Support Korean and English text.\n"
    "- Accurately transcribe numbers, symbols, and table content.\n"
    "- Output only the extracted text. No explanations, no markdown formatting."
)


def run_vlm(image: np.ndarray) -> dict:
    """GPT-4V로 이미지에서 텍스트 추출.

    Returns:
        {"text": str, "confidence": float, "quality_flag": str}
        — run_ocr()과 동일한 키 구조.

    API 키 미설정 시 NotImplementedError → 호출부에서 Tesseract 결과 유지.
    API 오류는 예외를 그대로 전파 → 호출부(except Exception)에서 Tesseract 폴백.
    """
    if not settings.openai_api_key:
        raise NotImplementedError("OPENAI_API_KEY가 설정되지 않아 VLM을 사용할 수 없습니다.")

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)

    # BGR numpy 배열 → PNG bytes → base64 (OpenCV는 BGR, OpenAI는 RGB 무관하게 PNG로 전송)
    _, buf = cv2.imencode(".png", image)
    b64_image = base64.b64encode(buf.tobytes()).decode("utf-8")

    response = client.chat.completions.create(
        model=settings.vlm_model,
        messages=[
            {"role": "system", "content": _OCR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                    }
                ],
            },
        ],
        max_tokens=settings.vlm_max_tokens,
    )

    text = response.choices[0].message.content or ""
    confidence = _get_vlm_confidence(text)

    return {
        "text": text,
        "confidence": round(confidence, 2),
        "quality_flag": _get_quality_flag(confidence),
    }


def _get_vlm_confidence(text: str) -> float:
    """텍스트 길이를 0~100 신뢰도로 선형 매핑.

    VLM_CONF_TEXT_LIMIT 이상이면 100.0으로 고정.
    GPT-4V는 단어별 신뢰도를 반환하지 않으므로 텍스트 길이로 근사한다.
    """
    return min(len(text) / VLM_CONF_TEXT_LIMIT * 100, 100.0)


def _get_quality_flag(confidence: float) -> str:
    """신뢰도 점수를 quality_flag 문자열로 변환. extractor._get_quality_flag()와 동일한 임계값."""
    ct = settings.confidence_thresholds
    if confidence >= ct["high"]:   return "high"
    if confidence >= ct["medium"]: return "medium"
    if confidence >= ct["low"]:    return "low"
    return "very_low"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_run_vlm_raises_not_implemented_without_api_key tests/test_ocr.py::test_get_vlm_confidence_zero tests/test_ocr.py::test_get_vlm_confidence_half tests/test_ocr.py::test_get_vlm_confidence_max tests/test_ocr.py::test_run_vlm_returns_correct_structure -v
```

Expected: 5개 모두 `PASSED`

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
pytest tests/ -v
```

Expected: 기존 테스트 모두 `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add app/services/vlm.py tests/test_ocr.py
git commit -m "feat: implement run_vlm() with GPT-4V, length-based confidence heuristic"
```

---

### Task 4: extractor.py 폴백 범위 수정

**Files:**
- Modify: `app/services/extractor.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ocr.py`에 추가:

```python
def test_run_ocr_with_fallback_api_error_falls_back_to_tesseract():
    """run_vlm()이 API 오류(NotImplementedError 아닌 예외)를 던져도 Tesseract 결과 반환."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "fallback", "confidence": 10.0, "quality_flag": "very_low"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm", side_effect=RuntimeError("API error")):
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "tesseract"
    assert result["text"] == "fallback"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_run_ocr_with_fallback_api_error_falls_back_to_tesseract -v
```

Expected: `FAILED` — RuntimeError가 잡히지 않고 전파됨

- [ ] **Step 3: extractor.py except 수정**

`app/services/extractor.py`의 `run_ocr_with_fallback()` 함수에서:

```python
        except NotImplementedError:
            pass
```

를 아래로 교체:

```python
        except Exception:
            # NotImplementedError(API 키 미설정)뿐 아니라 API 오류도 Tesseract 결과로 폴백한다.
            pass
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_run_ocr_with_fallback_api_error_falls_back_to_tesseract -v
```

Expected: `PASSED`

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
pytest tests/ -v
```

Expected: 모두 `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add app/services/extractor.py tests/test_ocr.py
git commit -m "fix: broaden VLM fallback to catch all exceptions, not just NotImplementedError"
```

---

### Task 5: docker-compose.yml 동기화

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: docker-compose.yml에 environment 섹션 추가**

`docker-compose.yml`의 `env_file` 아래에 추가:

```yaml
services:
  api:
    build: .
    ports:
      - "${PORT:-8900}:${PORT:-8900}"
    volumes:
      - ./uploads:/app/uploads
      - ./temp:/app/temp
    env_file:
      - .env
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      # .env에서 자동으로 읽히지만 명시해 컨테이너에 전달됨을 문서화한다.
    restart: unless-stopped
```

- [ ] **Step 2: 커밋**

```bash
git add docker-compose.yml
git commit -m "feat: pass OPENAI_API_KEY to docker-compose container"
```

---

### Task 6: README + test_scenarios.md 동기화

**Files:**
- Modify: `README.md`
- Modify: `tests/test_scenarios.md`

- [ ] **Step 1: README 이미지 지원 상태 업데이트**

`README.md`의 지원 파일 형식 표에서 이미지 행의 `상태` 열을 수정:

```markdown
| JPEG | `image/jpeg` | 50 MB | Tesseract + VLM 폴백 |
| PNG  | `image/png`  | 50 MB | Tesseract + VLM 폴백 |
| WebP | `image/webp` | 50 MB | Tesseract + VLM 폴백 |
| TIFF | `image/tiff` | 50 MB | Tesseract + VLM 폴백 |
```

- [ ] **Step 2: README 환경변수 표 업데이트**

기존 환경변수 표 아래에 추가:

```markdown
| `OPENAI_API_KEY` | `` | OpenAI API 키. 비어있으면 VLM 폴백 비활성화, Tesseract 결과 유지 |
| `VLM_MODEL` | `gpt-4o` | VLM 호출 모델. `gpt-4o-mini`로 낮추면 비용 절감 |
| `VLM_MAX_TOKENS` | `1024` | VLM 응답 최대 토큰 수 |
| `VLM_FALLBACK_FLAGS` | `["very_low"]` | 이 등급일 때 VLM 재시도. JSON 배열 형식 필수 |
```

- [ ] **Step 3: README 기술 스택 표 업데이트**

이미지 OCR 행 수정:

```markdown
| 이미지 OCR | Tesseract + GPT-4V 폴백 (OpenAI API) |
```

- [ ] **Step 4: README 에러 응답 표에서 501 제거**

아래 행 삭제:
```markdown
| `501` | 이미지 업로드 (VLM 미구현) |
```

- [ ] **Step 5: README 요청 흐름 다이어그램 업데이트**

"이미지 → HTTP 501 (VLM 예정)" 부분을 수정:

```
POST /ocr/upload
    │
    ├─ 이미지 → run_ocr_with_fallback()
    │         ├─ Tesseract 신뢰도 충분  →  method: "ocr"
    │         └─ 신뢰도 very_low       →  GPT-4V 재시도 → method: "vlm"
    │                                      (API 키 없거나 오류 시 Tesseract 유지)
    │
    └─ PDF
         │  routes/ocr.py: 임시 파일 저장 → extract_parallel() 호출
         │
         └─ extractor.py (페이지별 독립 처리)
                │
                ├─ pdfplumber 텍스트 ≥ 50자
                │       └─ method: "direct"  confidence: null
                │
                └─ 텍스트 < 50자
                        └─ pdf2image → 전처리 → Tesseract
                               ├─ 신뢰도 충분  →  method: "ocr"
                               └─ very_low   →  GPT-4V → method: "vlm"
```

- [ ] **Step 6: test_scenarios.md에 신규 시나리오 추가**

`tests/test_scenarios.md`의 6번 섹션 뒤에 추가:

```markdown
---

## 7. VLM 폴백

### TC-15 VLM 폴백 — API 키 미설정

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_run_vlm_raises_not_implemented_without_api_key` |
| 목적 | OPENAI_API_KEY 미설정 시 NotImplementedError → Tesseract 결과 유지 |

**기대 결과**
- `run_vlm()` 호출 시 `NotImplementedError` 발생

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-16 VLM 폴백 — API 오류

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_run_ocr_with_fallback_api_error_falls_back_to_tesseract` |
| 목적 | API 오류(RuntimeError 등) 발생 시 Tesseract 결과로 폴백 |

**기대 결과**
- `result["engine"]` = `"tesseract"`
- `result["text"]` = Tesseract 결과

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-17 VLM 신뢰도 휴리스틱

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_get_vlm_confidence_zero`, `test_get_vlm_confidence_half`, `test_get_vlm_confidence_max` |
| 목적 | 텍스트 길이 → confidence 선형 매핑 검증 |

**기대 결과**

| 텍스트 길이 | confidence |
|---|---|
| 0자 | 0.0 |
| 250자 | 50.0 |
| 500자+ | 100.0 |

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-18 VLM 결과 구조 검증

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_run_vlm_returns_correct_structure` |
| 목적 | run_vlm()이 run_ocr()과 동일한 키 구조를 반환하는지 확인 |

**기대 결과**
- `{"text": str, "confidence": float, "quality_flag": str}` 키 존재
- 400자 텍스트 → confidence=80.0, quality_flag="high"

**실행 결과** `[ ]` 통과 / `[ ]` 실패
```

- [ ] **Step 7: 전체 테스트 최종 확인**

```bash
pytest tests/ -v
```

Expected: 전체 `PASSED`

- [ ] **Step 8: 커밋**

```bash
git add README.md tests/test_scenarios.md
git commit -m "docs: update README and test_scenarios for VLM (GPT-4V) implementation"
```
