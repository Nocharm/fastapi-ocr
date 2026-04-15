# OCR 라우팅 설계 — 컨텐츠 기반 엔진 선택
**Date:** 2026-04-15
**Scope:** `app/services/`, `app/api/routes/ocr.py`, `app/core/config.py`, `app/schemas/ocr.py`

---

## 1. 배경 및 목표

### 현재 상태
- 이미지 업로드 → HTTP 501 반환 (EasyOCR 제거됨, VLM 연동 예정)
- PDF → pdfplumber 직접 추출 우선, 스캔 페이지는 Tesseract OCR 폴백

### 문제
이미지와 스캔 PDF 페이지는 처리 과정이 동일한데 다른 경로로 분기되어 있고,
Tesseract 신뢰도가 낮아도 VLM으로 재시도할 수단이 없다.

### 목표
- 이미지와 스캔 PDF 페이지를 같은 함수로 처리
- Tesseract 신뢰도 기반으로 VLM 폴백 자동 적용
- VLM 엔진을 나중에 교체할 수 있도록 인터페이스 분리

---

## 2. 전체 데이터 흐름

```
이미지 업로드  ──┐
                  ├── numpy 배열 ──► run_ocr_with_fallback()
스캔 PDF 페이지 ─┘                       │
                                          ├── run_ocr() [Tesseract]
                                          │    └── quality_flag ∈ vlm_fallback_flags?
                                          │         ├── Yes → run_vlm()
                                          │         │         └── NotImplementedError → Tesseract 결과 반환
                                          │         └── No  → Tesseract 결과 반환
                                          └── 결과 반환

PDF 텍스트 페이지
  └── pdfplumber 직접 추출 (변경 없음)
```

**핵심 원칙:** 이미지와 스캔 PDF 페이지는 numpy 배열로 수렴한 이후 동일한 함수로 처리한다.
차이는 numpy 배열이 만들어지는 방식뿐이다.

---

## 3. 모듈별 변경 사항

### 3-1. `app/services/vlm.py` (신규)

VLM 엔진 인터페이스. 현재 stub — 로컬 모델(LLaVA, Qwen-VL 등) 연동 예정.

```python
def run_vlm(image: np.ndarray) -> dict:
    """VLM으로 이미지에서 텍스트 추출.
    반환 형식: {"text": str, "confidence": float, "quality_flag": str}
    로컬 모델 연동 전까지 NotImplementedError를 발생시켜 호출부에서 폴백 처리.
    """
    raise NotImplementedError
```

로컬 모델 연결 시 이 함수 내부만 교체한다. 호출부(`run_ocr_with_fallback`) 수정 불필요.

### 3-2. `app/services/extractor.py` (수정)

#### 추가: `run_ocr_with_fallback()`

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

`engine` 키를 포함해 반환하는 이유: `extract_page()`와 `_process_image()`가
`PageResult.method`를 `"ocr"` / `"vlm"` 중 어느 값으로 설정할지 판단하기 위해 필요하다.

#### 수정: `extract_page()`

스캔 페이지 폴백 경로에서 `run_ocr(image)` → `run_ocr_with_fallback(image)` 교체.
`method`는 `ocr_result["engine"]` 값을 그대로 사용한다 (`"tesseract"` → `"ocr"`, `"vlm"` → `"vlm"`).

### 3-3. `app/api/routes/ocr.py` (수정)

이미지 분기에서 501 제거. `_process_image()` 추가.

```python
async def _process_image(file: UploadFile) -> dict:
    """bytes → numpy 변환 후 run_ocr_with_fallback() 위임."""
    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    result = run_ocr_with_fallback(image)
    return _make_single_page_response(result)
```

`_make_single_page_response()`는 이미지 단건 결과를 `extract_parallel()` 반환 형식과 동일하게 맞춰주는 내부 함수. `PageResult(page_num=0, method=engine, ...)`를 생성한 뒤 기존 `_make_response([page_result])`를 호출해 `OCRResponse` 호환 구조(`pages`, `total`, `success_count`, `failed_pages`)를 반환한다. 이미지는 단일 "페이지"로 간주하므로 `page_num=0` 고정.

### 3-4. `app/core/config.py` (수정)

```python
vlm_fallback_flags: list[str] = ["very_low"]
# Tesseract quality_flag가 이 목록에 해당하면 VLM 재시도.
# .env: VLM_FALLBACK_FLAGS=very_low,low
```

분류: 튜닝 파라미터 → `.env` + `Settings` 2단계 연동.

### 3-5. `app/schemas/ocr.py` (수정)

`PageResult.method` 주석에 `"vlm"` 추가:

```python
method: str = ""
# "direct": pdfplumber 직접 추출
# "ocr"   : Tesseract OCR
# "vlm"   : VLM 엔진 (Tesseract 폴백 후 재시도)
```

---

## 4. 설정값 분류

| 항목 | 분류 | 위치 |
|------|------|------|
| `vlm_fallback_flags` | 튜닝 파라미터 | `.env` + `Settings` |

`.env` 추가 항목:
```
# VLM 폴백 트리거 등급 (very_low / low / medium / high)
VLM_FALLBACK_FLAGS=very_low
```

---

## 5. 동기화 파일 체크리스트

| 파일 | 변경 내용 |
|------|-----------|
| `app/services/vlm.py` | 신규 생성 |
| `app/services/extractor.py` | `run_ocr_with_fallback()` 추가, `extract_page()` 수정 |
| `app/api/routes/ocr.py` | 이미지 501 제거, `_process_image()` 추가 |
| `app/core/config.py` | `vlm_fallback_flags` 필드 추가 |
| `app/schemas/ocr.py` | `method` 주석에 `"vlm"` 추가 |
| `.env` | `VLM_FALLBACK_FLAGS` 항목 추가 |
| `README.md` | 이미지 업로드 지원 상태 업데이트 |
| `tests/test_ocr.py` | `run_ocr_with_fallback()` 테스트 추가 |
| `tests/test_scenarios.md` | 이미지 업로드 시나리오 추가 |

`Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.dockerignore`는 이번 변경으로 수정 불필요.

---

## 6. 테스트 전략

- `run_ocr_with_fallback()`: Tesseract mock으로 `quality_flag="very_low"` 반환 시 `run_vlm()` 호출 여부 확인
- `run_vlm()` stub: `NotImplementedError` 발생 시 Tesseract 결과가 최종 반환되는지 확인
- `_process_image()`: 이미지 bytes → numpy 변환 정상 동작 확인
- 기존 PDF 테스트: 변경 없이 통과해야 함
