# OCR API 테스트 시나리오

> 각 시나리오는 `tests/test_ocr.py`의 대응 테스트 함수와 매핑된다.
> 코드 변경 시 이 파일도 함께 업데이트해야 한다.
>
> **[변경 이력]**
> - EasyOCR 제거에 따라 TC-02(고품질 이미지), TC-03(저품질 이미지),
>   TC-04(이미지 포맷) 삭제.
> - TC-02N 추가 후 삭제: 이미지 업로드 시 HTTP 501 반환 검증.
> - TC-02 재추가: Tesseract+VLM 폴백 파이프라인으로 이미지 처리 구현.
> - TC-02E 추가: 손상된 이미지 파일 → 422 검증.

---

## 목차

1. [기본 동작](#1-기본-동작)
2. [이미지 OCR](#2-이미지-ocr)
3. [PDF OCR](#3-pdf-ocr)
4. [입력 유효성 검사](#4-입력-유효성-검사)
5. [에러 복구](#5-에러-복구)
6. [OCR 품질 등급](#6-ocr-품질-등급)

---

## 1. 기본 동작

### TC-01 서버 상태 확인

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_health_check` |
| 목적 | 서버가 정상적으로 실행 중인지 확인 |
| 비고 | Docker HEALTHCHECK, 모니터링 도구가 주기적으로 호출 |

**요청**
```
GET /health
```

**기대 결과**
```json
HTTP 200
{ "status": "ok" }
```

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

## 2. 이미지 OCR

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

**요청**
```
POST /ocr/upload
Content-Type: multipart/form-data
file: broken.png (image/png, 내용: b"not_an_image")
```

**기대 결과**
```json
HTTP 422
{ "detail": "Invalid image file: unable to decode." }
```

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

## 3. PDF OCR

### TC-05 직접 추출 PDF (텍스트 레이어 있음)

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_pdf_direct_extraction` |
| 목적 | pdfplumber가 텍스트를 충분히 추출하면 OCR 없이 직접 반환되는지 확인 |
| 전제 조건 | 페이지 텍스트 길이 ≥ OCR_TEXT_THRESHOLD(50) |

**기대 결과**
```json
HTTP 200
{
  "pages": [{ "method": "direct", "confidence": null, "quality_flag": "" }]
}
```

**확인 포인트**
- `method` = `"direct"`
- `confidence` = `null` (OCR을 거치지 않아 신뢰도 없음)
- `quality_flag` = `""` (직접 추출은 등급 없음)

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-06 OCR 폴백 PDF (스캔 문서)

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_pdf_ocr_fallback` |
| 목적 | 직접 추출 텍스트가 부족하면 Tesseract OCR로 폴백하는지 확인 |
| 전제 조건 | 페이지 텍스트 길이 < OCR_TEXT_THRESHOLD(50) |

**기대 결과**
```json
HTTP 200
{
  "pages": [{ "method": "ocr", "confidence": 72.4, "quality_flag": "medium" }]
}
```

**확인 포인트**
- `method` = `"ocr"`
- `confidence` 값이 존재함 (null이 아님)

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-07 혼합 PDF (일부 페이지는 직접 추출, 일부는 OCR)

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_pdf_mixed_pages` |
| 목적 | 페이지마다 독립적으로 추출 방식이 결정되는지 확인 |
| 전제 조건 | 3페이지 PDF: 0번 직접 추출 가능 / 1번 OCR 필요 / 2번 직접 추출 가능 |

**기대 결과**
```json
HTTP 200
{
  "pages": [
    { "page_num": 0, "method": "direct" },
    { "page_num": 1, "method": "ocr" },
    { "page_num": 2, "method": "direct" }
  ],
  "total": 3,
  "success_count": 3
}
```

**확인 포인트**
- 각 페이지가 독립적으로 판단됨 (문서 전체를 단일 단위로 처리하지 않음)

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-08 테이블 포함 PDF

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_pdf_with_tables` |
| 목적 | 테이블이 마크다운 표 형식으로 변환되는지 확인 |

**기대 결과**
- `pages[n].tables` 배열에 마크다운 표 문자열 포함
- 마크다운 형식: `| col1 | col2 |\n| --- | --- |\n| val | val |`

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

## 4. 입력 유효성 검사

### TC-09 지원하지 않는 파일 형식

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_unsupported_file_type` |

**요청**
```
POST /ocr/upload
file: test.txt (text/plain)
```

**기대 결과**
```json
HTTP 415
{ "detail": "Unsupported file type: text/plain. Allowed: ..." }
```

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-10 파일 미첨부

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_no_file` |

**요청**
```
POST /ocr/upload
(파일 없음)
```

**기대 결과**
```json
HTTP 422
{ "detail": [...] }   ← FastAPI 자동 유효성 검사 에러
```

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-11 파일 크기 초과 (> 50 MB)

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_file_too_large` |

**기대 결과**
```json
HTTP 413
{ "detail": "File too large. Max allowed size is 50 MB." }
```

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

## 5. 에러 복구

### TC-12 특정 페이지 처리 실패 시 나머지 페이지 정상 처리

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_pdf_partial_failure` |
| 목적 | 1개 페이지 실패가 전체 작업을 중단시키지 않는지 확인 |
| 전제 조건 | 3페이지 PDF에서 1번 페이지 처리 시 예외 발생하도록 mock |

**기대 결과**
```json
HTTP 200
{
  "total": 3,
  "success_count": 2,
  "failed_pages": [1],
  "pages": [
    { "page_num": 0, "success": true },
    { "page_num": 1, "success": false, "error": "..." },
    { "page_num": 2, "success": true }
  ]
}
```

**확인 포인트**
- `success_count` = 2 (실패한 1페이지 제외)
- `failed_pages` = `[1]`
- 0번, 2번 페이지는 정상 결과 포함

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

## 6. OCR 품질 등급

### TC-13 품질 등급 분류 단위 테스트

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_quality_classification` |
| 목적 | 신뢰도 점수에 따라 올바른 quality_flag가 반환되는지 확인 |

**기대 결과**

| 신뢰도 (avg_conf) | 기대 quality_flag |
|---|---|
| 85.0 | `"high"` |
| 65.0 | `"medium"` |
| 45.0 | `"low"` |
| 20.0 | `"very_low"` |

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

### TC-14 테이블 마크다운 변환 단위 테스트

| 항목 | 내용 |
|---|---|
| 대응 함수 | `test_table_to_markdown`, `test_table_to_markdown_empty` |
| 목적 | pdfplumber 테이블 데이터가 올바른 마크다운 표로 변환되는지 확인 |

**입력**
```python
[["이름", "나이"], ["홍길동", "30"], ["김철수", "25"]]
```

**기대 결과**
```
| 이름 | 나이 |
| --- | --- |
| 홍길동 | 30 |
| 김철수 | 25 |
```

**빈 입력 케이스**
- `[]` → `""`
- `[[]]` → `""`

**실행 결과** `[ ]` 통과 / `[ ]` 실패

---

## 실행 방법

```bash
# 전체 테스트
pytest tests/ -v

# 특정 테스트만
pytest tests/test_ocr.py::test_health_check -v

# 짧은 트레이스백으로 실행
pytest tests/ -v --tb=short
```
