# .env 설정 관리 설계
**Date:** 2026-04-14
**Scope:** `app/` 전체 설정값 및 `Dockerfile`, `docker-compose.yml`

---

## 1. 목적

설정값이 여러 파일에 분산 하드코딩되는 것을 방지한다.
`.env` 또는 `config.py`를 단일 진실 공급원(Single Source of Truth)으로 삼아,
값을 바꿀 때 한 곳만 수정하면 되도록 한다.

---

## 2. 값 분류 기준

새 설정값을 추가할 때 아래 3가지 중 하나로 분류한다.

| 분류 | 판단 기준 | 배치 |
|---|---|---|
| **환경 설정** | 서버·배포 환경마다 다를 수 있는 값 | `.env` + `Settings` + Docker 연동 |
| **튜닝 파라미터** | 기본값은 있지만 운영 중 코드 수정 없이 조정 가능한 값 | `.env` + `Settings` |
| **비즈니스 로직 상수** | 앱의 동작 분류 경계를 정의하는 값. 배포 환경과 무관 | `Settings` 필드 (`.env` 항목 없음) |

**판단 질문:**
- "다른 서버에 배포할 때 이 값을 바꿔야 하나?" → 환경 설정
- "코드 수정 없이 성능·동작을 튜닝하고 싶을 수 있나?" → 튜닝 파라미터
- "이 값이 바뀌면 앱의 분류 로직 자체가 바뀌나?" → 비즈니스 로직 상수

---

## 3. 분류별 배치 패턴

### 환경 설정 — 4단계 연동

```
# 1. .env — 단일 진실 공급원
PORT=8900

# 2. config.py Settings 필드 — 앱에서 참조
port: int = 8900

# 3. Dockerfile — .env 없을 때 폴백용 기본값
ENV PORT=8900

# 4. docker-compose.yml — .env 값 참조, 없으면 폴백
"${PORT:-8900}:${PORT:-8900}"
```

### 튜닝 파라미터 — 2단계 (Docker 연동 불필요)

```
# 1. .env — 값 노출 (Settings 기본값에만 숨기지 않는다)
PDF_DPI=300

# 2. config.py Settings 필드
pdf_dpi: int = 300

# 3. 코드에서 사용
dpi=settings.pdf_dpi
```

### 비즈니스 로직 상수 — Settings 필드만

```python
# config.py Settings 안에서 기본값으로 정의
# .env 항목 없음 — 환경마다 달라질 값이 아니므로
confidence_thresholds: dict[str, int] = {
    "high": 80, "medium": 60, "low": 40, "very_low": 0
}
```

비즈니스 로직 상수를 변경하려면 `config.py` 코드를 직접 수정한다.
코드 리뷰 없이 배포 환경에서 변경할 수 없도록 의도적으로 `.env`에서 제외한다.

---

## 4. 금지 사항

- 수치·경로를 `.py` 코드 안에 리터럴로 직접 쓰기
- 튜닝 파라미터를 `Settings` 기본값에만 숨기고 `.env`에 미노출
- `config.py` 모듈 상수(`UPPER_SNAKE_CASE`)와 `Settings` 필드에 같은 값 중복 정의
- Docker 관련 환경 설정을 `Dockerfile`에만 하드코딩하고 `.env` 미연동

---

## 5. 현재 프로젝트 적용 현황

| 값 | 분류 | 현재 상태 | 조치 |
|---|---|---|---|
| `PORT` | 환경 설정 | `.env` + Dockerfile `ENV` + docker-compose `${PORT}` | 완료 |
| `UPLOAD_DIR`, `TEMP_DIR` | 환경 설정 | `.env` + `Settings` | 완료 |
| `OMP_NUM_THREADS` | 환경 설정 | Dockerfile에만 하드코딩 | `.env` + `Settings` 이동 필요 |
| `OCR_MAX_WORKERS` | 튜닝 파라미터 | `.env` + `Settings` | 완료 |
| `OCR_TEXT_THRESHOLD` | 튜닝 파라미터 | `.env` + `Settings` | 완료 |
| `OCR_WORD_CONF_MIN` | 튜닝 파라미터 | `.env` + `Settings` | 완료 |
| `dpi=300` | 튜닝 파라미터 | `extractor.py` 하드코딩 | `.env` + `Settings` 이동 필요 |
| `TESSERACT_CONFIG` | 튜닝 파라미터 | `config.py` 모듈 상수 | `Settings` 필드로 이동 필요 |
| `TESSERACT_LANG` | 튜닝 파라미터 | `config.py` 모듈 상수 | `Settings` 필드로 이동 필요 |
| `CONFIDENCE_THRESHOLDS` | 비즈니스 로직 상수 | `config.py` 모듈 상수 | `Settings` 필드로 이동 필요 |
