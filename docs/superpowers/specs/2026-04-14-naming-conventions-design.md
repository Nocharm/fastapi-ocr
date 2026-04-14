# Naming Conventions Design
**Date:** 2026-04-14
**Scope:** `app/` 전체 Python 코드 (신규 코드 + 기존 함수 리네임 포함)

---

## 1. 프로젝트 전용 동사 테이블

함수 이름의 첫 단어는 아래 동사 중 하나를 사용한다. 예외는 "예외 허용 목록"에 명시된 경우만 허용.

| 동사 | 의미 | 사용 예 |
|------|------|---------|
| `extract` | 외부 소스(PDF·이미지)에서 데이터를 꺼냄 | `extract_page`, `extract_tables`, `extract_parallel` |
| `get` | 계산 결과나 파생값을 반환 (DB·IO 없음) | `get_image_quality`, `get_quality_flag` |
| `run` | 외부 엔진·프로세스 실행 | `run_ocr` |
| `find` | 탐색·검색이 필요한 조회 | `find_tables_by_whitespace`, `find_table_regions` |
| `make` | 새 구조(dict·문자열·객체)를 조립 | `make_markdown_table`, `make_response` |
| `preprocess` | 이미지 전처리 (도메인 용어) | `preprocess_image` |
| `is_` | bool을 반환하는 함수의 접두사 | `is_text_sufficient` |
| `process` | 파이프라인 진입점·중간 조율 역할 | `_process_pdf` |

### 사용 금지 동사 (위 동사로 대체)

`convert`, `detect`, `assess`, `build`, `handle`, `classify`

---

## 2. 기존 함수 리네임 맵

### `app/services/extractor.py`

| 현재 | 변경 후 | 이유 |
|------|---------|------|
| `assess_image_quality` | `get_image_quality` | `assess` 금지 동사 → `get` |
| `adaptive_preprocess` | `preprocess_image` | 형용사+동사 혼합 → 동사+명사 |
| `_apply_preprocessing` | `_apply_image_filters` | `preprocess`와 역할 구분 명확화 |
| `ocr_with_confidence` | `run_ocr` | 동사 없음 → `run` |
| `_classify_quality` | `_get_quality_flag` | `classify` 금지 동사 → `get` |
| `extract_tables_with_fallback` | `extract_tables` | `_with_fallback`은 구현 세부사항 |
| `_table_to_markdown` | `_make_markdown_table` | `convert` 금지 동사 → `make` |
| `_detect_table_by_whitespace` | `_find_tables_by_whitespace` | `detect` 금지 동사 → `find` |
| `_detect_table_regions_by_contour` | `_find_table_regions` | `detect` 금지 동사 → `find` |
| `_process_page_safe` | `_extract_page_safe` | `process` 모호 → `extract` |
| `_convert_page_to_image` | `_get_page_image` | `convert` 금지 동사 → `get` |
| `_build_response` | `_make_response` | `build` 금지 동사 → `make` |

**유지 (이미 규칙에 맞음):** `extract_page`, `extract_all_pages`, `extract_parallel`

### `app/api/routes/ocr.py`

| 현재 | 변경 후 | 이유 |
|------|---------|------|
| `_handle_pdf` | `_process_pdf` | `handle` 모호 → `process` (파이프라인 진입점) |

---

## 3. 변수 · 상수 · 클래스 규칙

### 변수 (snake_case)

| 규칙 | 예시 |
|------|------|
| bool 변수는 `is_` / `has_` 접두사 | `is_fallback_needed`, `has_tables` |
| 복수 컬렉션은 복수형 | `results`, `pages`, `regions` |
| 임시 루프 변수는 단일 단어 | `page`, `row`, `cnt` |
| 줄임말은 도메인 용어만 허용 | `conf` (confidence), `df` (DataFrame), `tmp` (임시파일) |

### 상수 (UPPER_SNAKE_CASE) — 변경 없음

`CONFIDENCE_THRESHOLDS`, `TESSERACT_CONFIG`, `TESSERACT_LANG`, `MAX_FILE_SIZE` 유지.

### 클래스 (PascalCase) — 변경 없음

`PageResult`, `OCRResponse`, `Settings` 유지.

---

## 4. 예외 허용 목록

- FastAPI 라우트 핸들러 (`upload_file`) — HTTP 레이어 관례 우선
- pandas/numpy/OpenCV 외부 라이브러리 반환 속성 (`valid.empty`, `image.ndim`) — 라이브러리 관례 유지
- 3자 이하 루프 변수 (`i`, `r`, `x`) — 허용
- 어쩔 수 없는 상황에서 동사 테이블 외 동사 사용 — 주석으로 이유 명시 후 허용
