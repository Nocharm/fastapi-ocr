# OCR 라우팅 구현 플랜 — 컨텐츠 기반 엔진 선택

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미지와 스캔 PDF 페이지를 동일한 `run_ocr_with_fallback()` 파이프라인으로 처리하고, Tesseract 신뢰도 낮을 때 VLM으로 자동 폴백하는 구조를 구축한다.

**Architecture:** `run_ocr_with_fallback(image)`이 Tesseract를 먼저 실행하고 `quality_flag`가 `vlm_fallback_flags`에 해당하면 `run_vlm()`을 재시도한다. VLM은 `app/services/vlm.py` 단일 함수로 격리되어, 로컬 모델 연결 시 이 파일만 수정하면 된다. 이미지 업로드는 `extract_image(numpy_array) -> dict`로 수렴해 `extract_parallel()`과 동일한 응답 형식을 반환한다.

**Tech Stack:** FastAPI, pydantic-settings, pytesseract, OpenCV (cv2), numpy, pdfplumber

---

## 파일 맵

| 파일 | 작업 |
|------|------|
| `app/core/config.py` | `vlm_fallback_flags: list[str]` 필드 추가 |
| `.env` | `VLM_FALLBACK_FLAGS=["very_low"]` 추가 |
| `app/services/vlm.py` | 신규 생성 — VLM 인터페이스 stub |
| `app/services/extractor.py` | `run_ocr_with_fallback()`, `extract_image()` 추가; `extract_page()` 수정 |
| `app/api/routes/ocr.py` | 이미지 501 제거, `_process_image()` 추가 |
| `app/schemas/ocr.py` | `method` 주석에 `"vlm"` 추가 |
| `tests/test_ocr.py` | 신규 테스트 추가, TC-02N → TC-02 교체 |
| `README.md` | OCR 전략 다이어그램 업데이트 |
| `tests/test_scenarios.md` | TC-02N → TC-02 교체, TC-15~17 추가 |

---

## Task 1: Settings — `vlm_fallback_flags` 필드 추가

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_ocr.py` 하단 "Settings 필드 검증" 블록에 추가:

```python
def test_settings_has_vlm_fallback_flags():
    """vlm_fallback_flags가 Settings에 존재하고 list[str]인지 확인."""
    from app.core.config import settings
    assert isinstance(settings.vlm_fallback_flags, list)
    assert all(isinstance(f, str) for f in settings.vlm_fallback_flags)
    assert len(settings.vlm_fallback_flags) >= 1
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_settings_has_vlm_fallback_flags -v
```

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'vlm_fallback_flags'`

- [ ] **Step 3: `config.py`에 필드 추가**

`app/core/config.py`의 `confidence_thresholds` 필드 바로 위에 추가:

```python
    vlm_fallback_flags: list[str] = ["very_low"]
    # Tesseract quality_flag가 이 목록에 해당하면 VLM 재시도.
    # .env: VLM_FALLBACK_FLAGS=["very_low"]  (JSON 배열 형식 필수)
```

- [ ] **Step 4: `.env`에 항목 추가**

`OCR_WORD_CONF_MIN=30` 바로 아래에 추가:

```
# VLM 폴백 트리거 등급 (JSON 배열 형식 필수)
# very_low / low / medium / high 중 선택
VLM_FALLBACK_FLAGS=["very_low"]
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_settings_has_vlm_fallback_flags -v
```

Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/core/config.py .env tests/test_ocr.py
git commit -m "feat: add vlm_fallback_flags setting"
```

---

## Task 2: VLM stub 모듈 생성

**Files:**
- Create: `app/services/vlm.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_ocr.py` 상단 import 블록 수정 (기존 import 유지):

```python
import numpy as np
import cv2
```

`tests/test_ocr.py` 하단에 새 섹션 추가:

```python
# --- VLM stub ---

def test_run_vlm_raises_not_implemented():
    """run_vlm()은 로컬 모델 연동 전까지 NotImplementedError를 발생시켜야 한다."""
    from app.services.vlm import run_vlm
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(NotImplementedError):
        run_vlm(image)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_run_vlm_raises_not_implemented -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.vlm'`

- [ ] **Step 3: `app/services/vlm.py` 생성**

```python
"""app/services/vlm.py — VLM 엔진 인터페이스.

로컬 모델(LLaVA, Qwen-VL 등) 연동 예정.
모델 연결 시 run_vlm() 내부만 교체한다. 호출부 수정 불필요.
"""
import numpy as np


def run_vlm(image: np.ndarray) -> dict:
    """VLM으로 이미지에서 텍스트 추출.

    Returns:
        {"text": str, "confidence": float, "quality_flag": str}
        — run_ocr()과 동일한 키 구조.

    로컬 모델 연동 전까지 NotImplementedError 발생.
    호출부(run_ocr_with_fallback)가 이를 잡아 Tesseract 결과로 폴백한다.
    """
    raise NotImplementedError
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_run_vlm_raises_not_implemented -v
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/services/vlm.py tests/test_ocr.py
git commit -m "feat: add vlm stub module with NotImplementedError interface"
```

---

## Task 3: `run_ocr_with_fallback()` 추가

**Files:**
- Modify: `app/services/extractor.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패 테스트 3개 작성**

`tests/test_ocr.py`에 추가:

```python
# --- run_ocr_with_fallback 단위 테스트 ---

def test_run_ocr_with_fallback_high_confidence():
    """신뢰도 높으면 Tesseract 결과 반환, VLM 호출 없음."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "hello", "confidence": 85.0, "quality_flag": "high"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result) as mock_ocr, \
         patch("app.services.extractor.run_vlm") as mock_vlm:
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "tesseract"
    assert result["text"] == "hello"
    mock_vlm.assert_not_called()


def test_run_ocr_with_fallback_vlm_escalation():
    """quality_flag가 vlm_fallback_flags에 해당하면 VLM 결과 반환."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "bad", "confidence": 10.0, "quality_flag": "very_low"}
    vlm_result = {"text": "good", "confidence": 90.0, "quality_flag": "high"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm", return_value=vlm_result):
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "vlm"
    assert result["text"] == "good"


def test_run_ocr_with_fallback_vlm_not_implemented():
    """VLM NotImplementedError 시 Tesseract 결과를 그대로 반환."""
    from app.services.extractor import run_ocr_with_fallback
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    tesseract_result = {"text": "fallback", "confidence": 10.0, "quality_flag": "very_low"}
    with patch("app.services.extractor.run_ocr", return_value=tesseract_result), \
         patch("app.services.extractor.run_vlm", side_effect=NotImplementedError):
        result = run_ocr_with_fallback(image)
    assert result["engine"] == "tesseract"
    assert result["text"] == "fallback"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_run_ocr_with_fallback_high_confidence \
       tests/test_ocr.py::test_run_ocr_with_fallback_vlm_escalation \
       tests/test_ocr.py::test_run_ocr_with_fallback_vlm_not_implemented -v
```

Expected: FAIL — `ImportError: cannot import name 'run_ocr_with_fallback'`

- [ ] **Step 3: `extractor.py` 상단 import에 vlm 추가**

`extractor.py`의 `from app.core.config import settings` 줄 아래에 추가:

```python
from app.services.vlm import run_vlm
```

- [ ] **Step 4: `extractor.py`에 `run_ocr_with_fallback()` 추가**

`run_ocr()` 함수 바로 아래 (3번 섹션 내)에 추가:

```python
def run_ocr_with_fallback(image: np.ndarray) -> dict:
    """Tesseract 먼저 시도. quality_flag가 vlm_fallback_flags에 해당하면 VLM 재시도.

    VLM 미구현(NotImplementedError) 시 Tesseract 결과를 그대로 반환.

    Returns:
        run_ocr() / run_vlm() 반환값에 "engine" 키 추가:
        {"text": str, "confidence": float, "quality_flag": str, "engine": "tesseract"|"vlm"}
    """
    result = run_ocr(image)
    result["engine"] = "tesseract"
    if result["quality_flag"] in settings.vlm_fallback_flags:
        try:
            vlm_result = run_vlm(image)
            vlm_result["engine"] = "vlm"
            return vlm_result
        except NotImplementedError:
            pass
    return result
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_run_ocr_with_fallback_high_confidence \
       tests/test_ocr.py::test_run_ocr_with_fallback_vlm_escalation \
       tests/test_ocr.py::test_run_ocr_with_fallback_vlm_not_implemented -v
```

Expected: PASS (3개 모두)

- [ ] **Step 6: 커밋**

```bash
git add app/services/extractor.py tests/test_ocr.py
git commit -m "feat: add run_ocr_with_fallback with VLM escalation"
```

---

## Task 4: `extract_image()` 추가 + `extract_page()` 수정

**Files:**
- Modify: `app/services/extractor.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_ocr.py`에 추가:

```python
# --- extract_image 단위 테스트 ---

def test_extract_image_returns_ocr_response_format():
    """extract_image()가 extract_parallel()과 동일한 dict 구조를 반환한다."""
    from app.services.extractor import extract_image
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    fallback_result = {"text": "test", "confidence": 72.0, "quality_flag": "medium", "engine": "tesseract"}
    with patch("app.services.extractor.run_ocr_with_fallback", return_value=fallback_result):
        result = extract_image(image)
    assert "pages" in result
    assert "total" in result
    assert "success_count" in result
    assert "failed_pages" in result
    assert result["total"] == 1
    assert result["pages"][0]["page_num"] == 0
    assert result["pages"][0]["method"] == "ocr"
    assert result["pages"][0]["success"] is True


def test_extract_image_vlm_engine_sets_method_vlm():
    """VLM 엔진 사용 시 method가 'vlm'으로 기록된다."""
    from app.services.extractor import extract_image
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    vlm_result = {"text": "vlm text", "confidence": 90.0, "quality_flag": "high", "engine": "vlm"}
    with patch("app.services.extractor.run_ocr_with_fallback", return_value=vlm_result):
        result = extract_image(image)
    assert result["pages"][0]["method"] == "vlm"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_extract_image_returns_ocr_response_format \
       tests/test_ocr.py::test_extract_image_vlm_engine_sets_method_vlm -v
```

Expected: FAIL — `ImportError: cannot import name 'extract_image'`

- [ ] **Step 3: `extractor.py`에 `extract_image()` 추가**

`# --- 5. 순차 처리 ---` 섹션 바로 위에 추가:

```python
def extract_image(image: np.ndarray) -> dict:
    """이미지 단건을 OCR 처리해 extract_parallel()과 동일한 형식으로 반환.

    이미지는 단일 "페이지"로 간주해 page_num=0으로 고정한다.
    """
    result = run_ocr_with_fallback(image)
    method = "vlm" if result["engine"] == "vlm" else "ocr"
    page_result = PageResult(
        page_num=0,
        text=result["text"],
        method=method,
        confidence=result["confidence"],
        quality_flag=result["quality_flag"],
        success=True,
    )
    return _make_response([page_result])
```

- [ ] **Step 4: `extract_page()`에서 `run_ocr` → `run_ocr_with_fallback` 교체**

`extract_page()` 함수에서 아래 3줄을 찾아:

```python
    image      = _get_page_image(pdf_path, page_num)
    ocr_result = run_ocr(image)
    tables     = extract_tables(page, page_image=image)

    return PageResult(
        page_num=page_num,
        text=ocr_result["text"],
        tables=tables,
        method="ocr",
        confidence=ocr_result["confidence"],
        quality_flag=ocr_result["quality_flag"],
        success=True,
    )
```

아래와 같이 교체:

```python
    image      = _get_page_image(pdf_path, page_num)
    ocr_result = run_ocr_with_fallback(image)
    tables     = extract_tables(page, page_image=image)
    method     = "vlm" if ocr_result["engine"] == "vlm" else "ocr"

    return PageResult(
        page_num=page_num,
        text=ocr_result["text"],
        tables=tables,
        method=method,
        confidence=ocr_result["confidence"],
        quality_flag=ocr_result["quality_flag"],
        success=True,
    )
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_extract_image_returns_ocr_response_format \
       tests/test_ocr.py::test_extract_image_vlm_engine_sets_method_vlm \
       tests/test_ocr.py::test_pdf_ocr_fallback -v
```

Expected: PASS (3개 모두 — TC-06이 통과하면 `extract_page()` 수정이 기존 동작을 깨지 않음)

- [ ] **Step 6: 커밋**

```bash
git add app/services/extractor.py tests/test_ocr.py
git commit -m "feat: add extract_image(), update extract_page() to use run_ocr_with_fallback"
```

---

## Task 5: 이미지 라우팅 업데이트

**Files:**
- Modify: `app/api/routes/ocr.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: TC-02N을 TC-02로 교체 (실패 테스트 먼저)**

`tests/test_ocr.py`에서 `test_image_upload_not_implemented` 함수를 아래로 교체:

```python
@pytest.fixture
def image_bytes():
    """유효한 10x10 PNG 바이트 (cv2.imdecode 테스트용)."""
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def test_image_upload_ocr(image_bytes):
    """TC-02: 이미지 업로드 → HTTP 200, method='ocr' 또는 'vlm'."""
    from dataclasses import asdict
    mock_result = {
        "pages": [asdict(PageResult(page_num=0, text="추출된 텍스트", method="ocr",
                                    confidence=72.0, quality_flag="medium", success=True))],
        "total": 1, "success_count": 1, "failed_pages": [],
    }
    with patch("app.api.routes.ocr.extract_image", return_value=mock_result):
        response = client.post(
            "/ocr/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["method"] in ("ocr", "vlm")
    assert page["success"] is True


def test_image_upload_invalid_bytes():
    """TC-02E: 이미지로 디코딩 불가한 bytes → HTTP 422."""
    response = client.post(
        "/ocr/upload",
        files={"file": ("broken.png", b"not_an_image", "image/png")},
    )
    assert response.status_code == 422
    assert "Invalid image" in response.json()["detail"]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_ocr.py::test_image_upload_ocr \
       tests/test_ocr.py::test_image_upload_invalid_bytes -v
```

Expected: FAIL — `assert 501 == 200`

- [ ] **Step 3: `ocr.py` 이미지 분기 수정**

`ocr.py` 상단 import에 추가:

```python
import cv2
import numpy as np
from app.services.extractor import extract_image, extract_parallel
```

기존 `from app.services.extractor import extract_parallel` 줄을 위 코드로 교체.

- [ ] **Step 4: `upload_file()` 이미지 분기 수정**

`if content_type in ALLOWED_IMAGE_TYPES:` 블록을 아래로 교체:

```python
    if content_type in ALLOWED_IMAGE_TYPES:
        result = await _process_image(file)
```

- [ ] **Step 5: `_process_image()` 함수 추가**

`_process_pdf()` 함수 바로 아래에 추가:

```python
async def _process_image(file: UploadFile) -> dict:
    """bytes → numpy 변환 후 extract_image() 위임.

    cv2.imdecode가 None을 반환하면 디코딩 실패 → 422.
    """
    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="Invalid image file: unable to decode.")
    return extract_image(image)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/test_ocr.py::test_image_upload_ocr \
       tests/test_ocr.py::test_image_upload_invalid_bytes -v
```

Expected: PASS

- [ ] **Step 7: 전체 테스트 통과 확인**

```bash
pytest tests/ -v
```

Expected: 모든 테스트 PASS (TC-02N 제거, TC-02 + TC-02E 추가)

- [ ] **Step 8: 커밋**

```bash
git add app/api/routes/ocr.py tests/test_ocr.py
git commit -m "feat: enable image OCR via run_ocr_with_fallback, replace 501 with actual processing"
```

---

## Task 6: Schema 주석 + 문서 동기화

**Files:**
- Modify: `app/schemas/ocr.py`
- Modify: `README.md`
- Modify: `tests/test_scenarios.md`

- [ ] **Step 1: `ocr.py` schema 주석 수정**

`app/schemas/ocr.py`에서:

```python
    method:       str             = ""
    # "direct": pdfplumber 직접 추출 / "ocr": Tesseract OCR
```

아래로 교체:

```python
    method:       str             = ""
    # "direct": pdfplumber 직접 추출 / "ocr": Tesseract OCR / "vlm": VLM 엔진
```

- [ ] **Step 2: `README.md` OCR 전략 다이어그램 수정**

`README.md`에서 아래 블록을 찾아:

```
업로드된 파일
├── 이미지 (JPEG / PNG / WebP / TIFF)
│   └── HTTP 501 반환 (VLM 연동 예정)
│
└── PDF
    └── 페이지별 독립 판단
        ├── 텍스트 레이어 ≥ 50자  →  pdfplumber 직접 추출 (method: "direct")
        └── 텍스트 레이어 < 50자  →  pdf2image + Tesseract OCR 폴백 (method: "ocr")
```

아래로 교체:

```
업로드된 파일
├── 이미지 (JPEG / PNG / WebP / TIFF)
│   └── run_ocr_with_fallback()
│       ├── Tesseract 신뢰도 충분  →  method: "ocr"
│       └── 신뢰도 very_low       →  VLM 재시도 → method: "vlm"
│                                      (VLM 미구현 시 Tesseract 결과 유지)
│
└── PDF
    └── 페이지별 독립 판단
        ├── 텍스트 레이어 ≥ 50자  →  pdfplumber 직접 추출 (method: "direct")
        └── 텍스트 레이어 < 50자  →  run_ocr_with_fallback()
                                      ├── Tesseract 신뢰도 충분  →  method: "ocr"
                                      └── 신뢰도 very_low       →  VLM 재시도 → method: "vlm"
```

`README.md` 상단의 이미지 OCR 예정 주석 블록(3줄)도 제거:

```
> **이미지 OCR (VLM 연동 예정)**
> EasyOCR이 제거되었습니다. 이미지 파일(JPEG/PNG/WebP/TIFF) 업로드 시 `HTTP 501`을 반환하며,
> VLM(Vision Language Model) 기반 이미지 OCR로 교체 예정입니다.
```

기술 스택 표에서 `이미지 OCR` 행도 교체:

```
| 이미지 OCR | VLM 연동 예정 (EasyOCR 제거됨) |
```
→
```
| 이미지 OCR | Tesseract + VLM 폴백 (로컬 모델 연동 예정) |
```

- [ ] **Step 3: `tests/test_scenarios.md` 업데이트**

`test_scenarios.md`의 `## 2. 이미지 OCR` 섹션에서 TC-02N 내용을 아래로 교체:

```markdown
### TC-02 이미지 업로드 — OCR 처리

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_image_upload_ocr` |
| 목적 | 이미지 업로드 시 Tesseract → VLM 폴백 파이프라인이 동작하는지 확인 |
| 비고 | VLM 미구현 시 Tesseract 결과 반환. method = "ocr" 또는 "vlm" |

**요청**
```
POST /ocr/upload
Content-Type: multipart/form-data
file: test.png (image/png)
```

**기대 결과**
```json
HTTP 200
{
  "pages": [{ "page_num": 0, "method": "ocr", "confidence": 72.0 }],
  "total": 1,
  "success_count": 1
}
```

**확인 포인트**
- 상태 코드 = `200`
- `method` = `"ocr"` 또는 `"vlm"`
- `page_num` = `0` (이미지는 단일 페이지)

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-02E 이미지 업로드 — 손상된 파일

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_image_upload_invalid_bytes` |
| 목적 | 디코딩 불가한 bytes 전송 시 422 반환 확인 |

**기대 결과**
```json
HTTP 422
{ "detail": "Invalid image file: unable to decode." }
```

**실행 결과** `[ ]` 통과 / `[ ]` 실패
```

변경 이력 블록도 업데이트:

```markdown
> **[변경 이력]**
> - EasyOCR 제거에 따라 TC-02(고품질 이미지), TC-03(저품질 이미지),
>   TC-04(이미지 포맷) 삭제.
> - TC-02N 추가 후 삭제: 이미지 업로드 시 HTTP 501 반환 검증.
> - TC-02 재추가: Tesseract+VLM 폴백 파이프라인으로 이미지 처리 구현.
> - TC-02E 추가: 손상된 이미지 파일 → 422 검증.
```

- [ ] **Step 4: 최종 전체 테스트**

```bash
pytest tests/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/schemas/ocr.py README.md tests/test_scenarios.md
git commit -m "docs: update schema comment, README, test_scenarios for image OCR routing"
```
