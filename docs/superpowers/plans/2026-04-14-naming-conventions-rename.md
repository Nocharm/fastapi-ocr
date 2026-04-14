# Naming Conventions Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 문서의 동사 테이블에 맞게 기존 함수명을 리네임하고, 내부 호출·임포트·mock 경로를 모두 일치시킨다.

**Architecture:** 순수 리네임 작업. 로직 변경 없음. 테스트 임포트를 먼저 새 이름으로 바꿔 ImportError를 유발한 뒤, 정의를 리네임해 통과시키는 순서로 진행한다.

**Tech Stack:** Python 3.11, FastAPI, pytest

---

## 파일 맵

| 파일 | 변경 내용 |
|------|-----------|
| `app/services/extractor.py` | 함수 정의 12개 리네임 + 내부 호출 업데이트 |
| `app/api/routes/ocr.py` | `_handle_pdf` → `_process_pdf` (정의 + 호출) |
| `tests/test_ocr.py` | 임포트 2개 + 함수 호출 4개 업데이트 |

---

## Task 1: tests/test_ocr.py — 임포트·호출을 새 이름으로 변경

테스트를 먼저 바꿔 ImportError 상태를 만든다. 이후 Task 2에서 정의를 리네임하면 통과된다.

**Files:**
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: 임포트 줄 수정**

`tests/test_ocr.py` 33번째 줄을 아래로 교체:

```python
from app.services.extractor import _get_quality_flag, _make_markdown_table
```

- [ ] **Step 2: test_quality_classification 호출 수정**

```python
@pytest.mark.parametrize("conf, expected_flag", [
    (85.0, "high"),
    (65.0, "medium"),
    (45.0, "low"),
    (20.0, "very_low"),
])
def test_quality_classification(conf, expected_flag):
    """TC-13: 신뢰도 점수 → quality_flag 분류."""
    assert _get_quality_flag(conf) == expected_flag
```

- [ ] **Step 3: test_table_to_markdown 두 함수 호출 수정**

```python
def test_table_to_markdown():
    """TC-14: pdfplumber 테이블 → 마크다운 표 변환."""
    table = [["이름", "나이"], ["홍길동", "30"], ["김철수", "25"]]
    result = _make_markdown_table(table)
    assert "| 이름 | 나이 |" in result
    assert "| --- | --- |" in result
    assert "| 홍길동 | 30 |" in result
    assert "| 김철수 | 25 |" in result


def test_table_to_markdown_empty():
    """빈 테이블 입력 → 빈 문자열 반환."""
    assert _make_markdown_table([]) == ""
    assert _make_markdown_table([[]]) == ""
```

- [ ] **Step 4: ImportError 확인**

```bash
pytest tests/test_ocr.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name '_get_quality_flag'`

---

## Task 2: app/services/extractor.py — 함수 정의 + 내부 호출 리네임

**Files:**
- Modify: `app/services/extractor.py`

- [ ] **Step 1: 섹션 2 — `get_image_quality`, `preprocess_image`, `_apply_image_filters` 교체**

아래 세 함수 정의를 통째로 교체한다 (로직은 동일, 이름과 내부 호출만 변경):

```python
# --- 2. 이미지 품질 평가 및 전처리 ---

def get_image_quality(image: np.ndarray) -> float:
    """
    Laplacian 분산으로 이미지 선명도를 측정한다.
    값이 높을수록 선명 (OCR 정확도 높음), 낮을수록 흐림.

    Laplacian: 이미지의 경계(엣지)를 감지하는 2차 미분 연산.
    선명한 이미지는 경계가 뚜렷해 분산이 크고, 흐린 이미지는 분산이 작다.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    # image.ndim == 3: 컬러(BGR) → 그레이스케일 변환
    # image.ndim == 2: 이미 흑백 → 그대로 사용
    return cv2.Laplacian(gray, cv2.CV_64F).var()
    # cv2.CV_64F: 64비트 부동소수점으로 계산해 정밀도 확보


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    전처리 전후 품질을 비교해서 더 나은 버전을 반환한다.
    전처리 후 품질이 원본의 90% 미만이면 원본을 그대로 사용한다.

    무조건 전처리를 적용하면 오히려 품질이 떨어질 수 있으므로
    반드시 비교 후 선택한다.
    """
    original_quality = get_image_quality(image)
    processed        = _apply_image_filters(image)

    if get_image_quality(processed) >= original_quality * 0.9:
        return processed
    return image


def _apply_image_filters(image: np.ndarray) -> np.ndarray:
    """그레이스케일 변환 → 노이즈 제거 → Otsu 이진화."""
    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    # h=10: 노이즈 제거 강도. 클수록 매끄러워지지만 디테일도 사라짐.

    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu 이진화: 히스토그램 분석으로 흑/백 분리 최적 임계값을 자동 계산한다.
    # _ : 계산된 임계값 (이후 사용 불필요)
    return binary
```

- [ ] **Step 2: 섹션 3 — `run_ocr`, `_get_quality_flag` 교체**

```python
# --- 3. OCR + 신뢰도 검증 ---

def run_ocr(image: np.ndarray) -> dict:
    """
    단어별 신뢰도를 필터링해 OCR 결과를 반환. image_to_string() 단독 사용 금지.

    image_to_data()로 단어별 신뢰도를 추출하고
    ocr_word_conf_min 미만의 단어는 결과에서 제외한다.

    Returns:
        {"text": str, "confidence": float, "quality_flag": str}
    """
    preprocessed = preprocess_image(image)

    data = pytesseract.image_to_data(
        preprocessed,
        lang=TESSERACT_LANG,
        config=TESSERACT_CONFIG,
        output_type=Output.DICT,
    )

    df    = pd.DataFrame(data)
    valid = df[df["conf"] != -1]
    # conf == -1: Tesseract가 텍스트 외 영역에 반환하는 값. 제외한다.

    avg_conf = float(valid["conf"].mean()) if not valid.empty else 0.0

    filtered_text = " ".join(
        valid[valid["conf"] >= settings.ocr_word_conf_min]["text"].tolist()
    )

    return {
        "text":         filtered_text,
        "confidence":   round(avg_conf, 2),
        "quality_flag": _get_quality_flag(avg_conf),
    }


def _get_quality_flag(avg_conf: float) -> str:
    """신뢰도 점수를 등급 문자열로 변환."""
    if avg_conf >= CONFIDENCE_THRESHOLDS["high"]:   return "high"
    if avg_conf >= CONFIDENCE_THRESHOLDS["medium"]: return "medium"
    if avg_conf >= CONFIDENCE_THRESHOLDS["low"]:    return "low"
    return "very_low"
```

- [ ] **Step 3: 섹션 4 — `extract_tables`, `_make_markdown_table`, `_find_tables_by_whitespace`, `_find_table_regions` 교체**

```python
# --- 4. 테이블 추출 — 3단계 폴백 ---

def extract_tables(page, page_image: np.ndarray | None) -> list[str]:
    """
    3단계 폴백 전략으로 테이블을 추출한다.
    하나라도 결과를 얻으면 이후 단계는 시도하지 않는다.

    Stage 1: pdfplumber     — 선 있는 표 (가장 빠르고 정확)
    Stage 2: 공백 휴리스틱  — 선 없는 텍스트 표
    Stage 3: 컨투어 + OCR  — 스캔된 표 (최후 수단)
    """
    # Stage 1
    try:
        tables = page.extract_tables()
        if tables:
            return [_make_markdown_table(t) for t in tables if t]
    except Exception:
        pass

    # Stage 2
    heuristic = _find_tables_by_whitespace(page.extract_text() or "")
    if heuristic:
        return heuristic

    # Stage 3: page_image가 없으면 (direct 방식 페이지) 스킵
    if page_image is None:
        return []

    results = []
    for region in _find_table_regions(page_image):
        y1, y2, x1, x2 = region["y"], region["y2"], region["x"], region["x2"]
        crop     = page_image[y1:y2, x1:x2]
        ocr_text = pytesseract.image_to_string(crop, lang=TESSERACT_LANG)
        results.append(f"<!-- OCR table -->\n{ocr_text}")

    return results


def _make_markdown_table(table: list) -> str:
    """pdfplumber 테이블(2차원 리스트)을 마크다운 표로 변환."""
    if not table or not table[0]:
        return ""

    header    = "| " + " | ".join(str(c or "") for c in table[0]) + " |"
    separator = "| " + " | ".join("---" for _ in table[0]) + " |"
    rows      = [
        "| " + " | ".join(str(c or "") for c in row) + " |"
        for row in table[1:]
    ]
    return "\n".join([header, separator] + rows)


def _find_tables_by_whitespace(text: str) -> list[str]:
    """
    공백 패턴으로 텍스트 표를 감지하는 휴리스틱.
    연속 공백(2개 이상)이 포함된 줄이 3줄 이상 연속되면 표로 간주한다.
    """
    lines       = text.splitlines()
    table_lines: list[str] = []
    result:      list[str] = []

    for line in lines:
        if "  " in line:
            table_lines.append(line)
        else:
            if len(table_lines) >= 3:
                result.append("\n".join(table_lines))
            table_lines = []

    if len(table_lines) >= 3:
        result.append("\n".join(table_lines))

    return result


def _find_table_regions(image: np.ndarray) -> list[dict]:
    """
    컨투어 검출로 표 영역 후보를 찾는다.
    면적이 전체 이미지의 1% 이상인 직사각형 영역만 반환한다.
    """
    gray      = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    # THRESH_BINARY_INV: 어두운 선(표 테두리)을 흰색으로 반전해 컨투어 감지

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # RETR_EXTERNAL: 가장 바깥쪽 윤곽선만 검출
    # CHAIN_APPROX_SIMPLE: 직선 구간 중간 점 제거로 메모리 절약

    h, w     = image.shape[:2]
    min_area = h * w * 0.01  # 전체 면적의 1% 미만은 노이즈로 제외

    regions = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw * ch >= min_area:
            regions.append({"x": x, "y": y, "x2": x + cw, "y2": y + ch})

    return regions
```

- [ ] **Step 4: 섹션 5 — `extract_all_pages` 내부 호출 수정**

`_build_response` → `_make_response` 호출 1곳:

```python
def extract_all_pages(pdf_path: str) -> dict:
    """
    PDF 전체를 순차적으로 처리한다.
    한 페이지의 실패가 전체 작업을 중단시키지 않는다.
    """
    results: list[PageResult] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            try:
                results.append(extract_page(page, page_num, pdf_path))
            except Exception as e:
                results.append(
                    PageResult(page_num=page_num, error=str(e), success=False)
                )

    return _make_response(results)
```

- [ ] **Step 5: 섹션 6 — `extract_parallel`, `_extract_page_safe` 교체**

```python
# --- 6. 병렬 처리 — 대용량 PDF용 ---

def extract_parallel(pdf_path: str) -> dict:
    """
    페이지를 ThreadPoolExecutor로 병렬 처리한다.

    주의: pdfplumber 페이지 객체는 파일 스트림을 공유하므로 스레드 간 전달 금지.
    _extract_page_safe()에서 스레드마다 PDF를 독립적으로 열어 경쟁 조건을 방지한다.
    """
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)

    results: list[PageResult | None] = [None] * num_pages

    with ThreadPoolExecutor(max_workers=settings.ocr_max_workers) as executor:
        futures = {
            executor.submit(_extract_page_safe, pdf_path, i): i
            for i in range(num_pages)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as e:
                print(f"[ERROR] page {i} 처리 실패:\n{traceback.format_exc()}", flush=True)
                results[i] = PageResult(page_num=i, error=str(e), success=False)

    return _make_response([r for r in results if r is not None])


def _extract_page_safe(pdf_path: str, page_num: int) -> PageResult:
    """스레드마다 PDF를 독립적으로 열어 단일 페이지를 처리한다."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        return extract_page(page, page_num, pdf_path)
```

- [ ] **Step 6: 내부 유틸 — `_get_page_image`, `_make_response` 교체**

```python
# --- 내부 유틸 ---

def _get_page_image(pdf_path: str, page_num: int) -> np.ndarray:
    """PDF 특정 페이지를 numpy 배열(BGR)로 변환."""
    images = convert_from_path(
        pdf_path,
        first_page=page_num + 1,  # pdf2image는 1-based 페이지 번호 사용
        last_page=page_num + 1,
        dpi=300,
        # 낮추면 속도 향상, OCR 정확도 하락
    )
    return cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2BGR)
    # PIL은 RGB, OpenCV는 BGR 순서를 사용하므로 변환 필요.


def _make_response(results: list[PageResult]) -> dict:
    """PageResult 목록을 OCRResponse 호환 dict로 변환."""
    return {
        "pages":         [asdict(r) for r in results],
        "total":         len(results),
        "success_count": sum(1 for r in results if r.success),
        "failed_pages":  [r.page_num for r in results if not r.success],
    }
```

- [ ] **Step 7: extract_page 내부 호출 수정**

`extract_page` 함수 본문에서 호출하는 이름 3개를 업데이트:

```python
def extract_page(page, page_num: int, pdf_path: str) -> PageResult:
    """
    단일 페이지 처리. 직접 추출을 먼저 시도하고 부족하면 OCR 폴백.

    Args:
        page    : pdfplumber 페이지 객체
        page_num: 0-based 페이지 번호
        pdf_path: 원본 PDF 경로 (OCR 폴백 시 이미지 변환에 사용)
    """
    print(f"[DEBUG] extract_page 시작: page_num={page_num}", flush=True)
    text = page.extract_text() or ""
    print(f"[DEBUG] extract_text 완료: len={len(text)}", flush=True)

    if len(text.strip()) >= settings.ocr_text_threshold:
        tables = extract_tables(page, page_image=None)
        return PageResult(
            page_num=page_num,
            text=text,
            tables=tables,
            method="direct",
            success=True,
        )

    # 텍스트 부족 → 스캔 PDF로 판단 → OCR 폴백
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

---

## Task 3: app/api/routes/ocr.py — `_handle_pdf` → `_process_pdf`

**Files:**
- Modify: `app/api/routes/ocr.py`

- [ ] **Step 1: 함수 정의 및 호출 수정**

`upload_file` 내 호출:
```python
elif content_type in ALLOWED_PDF_TYPES:
    result = await _process_pdf(file)
```

함수 정의:
```python
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
```

---

## Task 4: 전체 테스트 실행 및 커밋

**Files:** 없음 (검증 + 커밋만)

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest tests/ -v
```

Expected output (전부 PASSED):
```
tests/test_ocr.py::test_health_check PASSED
tests/test_ocr.py::test_image_upload_not_implemented PASSED
tests/test_ocr.py::test_pdf_direct_extraction PASSED
tests/test_ocr.py::test_pdf_ocr_fallback PASSED
tests/test_ocr.py::test_pdf_mixed_pages PASSED
tests/test_ocr.py::test_pdf_with_tables PASSED
tests/test_ocr.py::test_unsupported_file_type PASSED
tests/test_ocr.py::test_no_file PASSED
tests/test_ocr.py::test_file_too_large PASSED
tests/test_ocr.py::test_pdf_partial_failure PASSED
tests/test_ocr.py::test_quality_classification[85.0-high] PASSED
tests/test_ocr.py::test_quality_classification[65.0-medium] PASSED
tests/test_ocr.py::test_quality_classification[45.0-low] PASSED
tests/test_ocr.py::test_quality_classification[20.0-very_low] PASSED
tests/test_ocr.py::test_table_to_markdown PASSED
tests/test_ocr.py::test_table_to_markdown_empty PASSED
```

실패 시: 오류 메시지에서 여전히 구 이름(예: `_classify_quality`)이 남아있는 곳을 찾아 수정한다.

- [ ] **Step 2: 커밋**

```bash
git add app/services/extractor.py app/api/routes/ocr.py tests/test_ocr.py
git commit -m "refactor: apply naming conventions — rename 13 functions to match verb table"
```
