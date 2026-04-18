# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

이 파일은 Claude Code가 이 프로젝트에서 코드를 수정할 때 반드시 따라야 할 규칙을 정의합니다.

---

## 1. 개발 명령어

### 로컬 실행

```bash
# 가상환경
python -m venv .venv && source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt          # 프로덕션만
pip install -r requirements-dev.txt      # 개발/테스트 포함

# 서버 실행
uvicorn app.main:app --reload
```

서버: http://localhost:8900 / Swagger: http://localhost:8900/docs / 헬스체크: http://localhost:8900/health

### Docker 실행

```bash
docker-compose up --build       # 포그라운드
docker-compose up --build -d    # 백그라운드
docker-compose down             # 중지
```

### 테스트

```bash
pytest tests/ -v                              # 전체 테스트
pytest tests/test_ocr.py::test_health_check -v  # 단일 테스트
```

### 사전 요구사항

- Python 3.11, Tesseract 5.x + 한국어 언어팩, poppler
- macOS: `brew install tesseract tesseract-lang poppler`
- Ubuntu: `apt-get install -y tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng poppler-utils`

---

## 2. 프로젝트 구조 규칙

```
app/
├── main.py              # 앱 진입점, 라우터 등록만 담당. 비즈니스 로직 금지.
├── core/
│   └── config.py        # 설정값과 상수만. 다른 app 모듈을 import하지 않는다.
├── api/
│   └── routes/          # HTTP 레이어. 검증 후 서비스로 위임. 직접 로직 금지.
├── schemas/             # 데이터 구조 정의. Pydantic(응답) + dataclass(내부).
└── services/            # 비즈니스 로직. 라우터/스키마를 알지만 routes는 모른다.
```

- 새 기능은 반드시 위 계층 구조를 따른다.
- 서비스 함수는 항상 `PageResult` 또는 `OCRResponse` 호환 구조를 반환한다.
- 설정값은 코드에 하드코딩하지 않고 `config.py`의 `Settings` 또는 상수로 관리한다.

---

## 3. 코딩 규칙

### 네이밍 규칙

함수·변수·클래스 명명 규칙은 아래 스펙 문서를 따른다.

→ [@docs/superpowers/specs/2026-04-14-naming-conventions-design.md](docs/superpowers/specs/2026-04-14-naming-conventions-design.md)

**핵심 요약:**
- 함수 첫 단어: `extract` / `get` / `run` / `find` / `make` / `preprocess` / `process` 중 하나
- 금지 동사: `convert`, `detect`, `assess`, `build`, `handle`, `classify`
- bool 반환 함수: `is_` / `has_` 접두사 필수
- 예외는 주석으로 이유 명시 후 허용

### 주석 규칙

코드를 수정하거나 추가할 때 **간결하고 의도가 드러나는 주석**을 달아야 한다.

**작성 기준:**
- **왜(Why)** 이 코드가 필요한지 한 줄로 설명한다. 코드만 보면 알 수 있는 "무엇(What)" 주석은 달지 않는다.
- **모듈**: 파일 상단에 한 줄 요약 docstring을 반드시 작성한다 (`"""역할 설명."""`).
- **함수/클래스**: 역할과 주의사항만 한두 줄로 적는다. 명백한 것은 생략한다.
- **비자명한 로직** (라이브러리 옵션, 수식, 경쟁 조건 등): 해당 줄 끝 또는 바로 위에 이유를 한 줄로 적는다.
- **상수/설정값**: 단위·허용 범위·변경 시 영향을 인라인으로 적는다.

**금지 사항:**
- `# 파일을 읽는다`, `# 결과를 반환한다` 처럼 코드를 그대로 번역한 주석.
- 함수 이름과 똑같은 내용의 docstring.
- 장황한 구분선 블록(`# ---...---`) — 섹션 구분 외에는 사용하지 않는다.

**간결한 주석 예시:**

```python
# 내부 OpenMP 스레드와 ThreadPoolExecutor 충돌 방지
os.environ.setdefault("OMP_NUM_THREADS", "1")

def ocr_with_confidence(image: np.ndarray) -> dict:
    """단어별 신뢰도를 필터링해 OCR 결과를 반환. image_to_string() 단독 사용 금지."""
    ...

dpi=300,  # 낮추면 속도 향상, OCR 정확도 하락
```

---

## 4. 설정값 관리 규칙

설정값 관리의 상세 분류 체계와 배치 패턴은 아래 스펙 문서를 따른다.

→ [@docs/superpowers/specs/2026-04-14-env-config-design.md](docs/superpowers/specs/2026-04-14-env-config-design.md)

**핵심 요약:**
새 설정값을 추가할 때 아래 3가지 판단 질문으로 분류한다.
- "다른 서버에 배포할 때 이 값을 바꿔야 하나?" → **환경 설정** (`.env` + `Settings` + Dockerfile `ENV` + docker-compose)
- "코드 수정 없이 성능·동작을 튜닝하고 싶을 수 있나?" → **튜닝 파라미터** (`.env` + `Settings`)
- "이 값이 바뀌면 앱의 분류 로직 자체가 바뀌나?" → **비즈니스 로직 상수** (`Settings` 필드 기본값만)

**환경변수 규칙:**
- `.env`는 git에 커밋하지 않는다 (`.gitignore`에 포함).
- 새 설정값을 `Settings`에 추가할 때 `.env`에도 해당 항목(주석 포함)을 추가한다.
- 민감한 값(API 키, 비밀번호)은 절대 코드에 하드코딩하지 않는다.

**금지 사항:**
- 수치·경로를 `.py` 코드 안에 리터럴로 직접 쓰기
- 튜닝 파라미터를 `Settings` 기본값에만 숨기고 `.env`에 미노출
- `config.py` 모듈 상수(`UPPER_SNAKE_CASE`)와 `Settings` 필드에 같은 값 중복 정의
- Docker 관련 환경 설정을 `Dockerfile`에만 하드코딩하고 `.env` 미연동

---

## 5. Docker 규칙

- `Dockerfile`은 **BuildKit** (`# syntax=docker/dockerfile:1`) 을 사용한다.
- apt 캐시와 pip 캐시는 `--mount=type=cache` 로 처리한다 (`rm -rf /var/lib/apt/lists/*` 불필요).
- `torch` / `torchvision`은 CPU 전용 인덱스(`https://download.pytorch.org/whl/cpu`)에서 먼저 설치한다.
- 컨테이너는 **비루트 사용자(`appuser`)** 로 실행한다.
- `ENV OMP_NUM_THREADS=1` 은 항상 유지한다.

---

## 6. 테스트 규칙

- 새 기능 추가 시 `tests/test_ocr.py`에 대응하는 테스트 케이스를 추가한다.
- 외부 엔진(EasyOCR, Tesseract, pdfplumber)은 Mock으로 대체해 테스트 속도를 유지한다.
- 테스트는 `pytest tests/ -v` 로 실행한다.
- `requirements-dev.txt`에 테스트 의존성이 있어야 한다.

---

## 7. 코드 변경 시 필수 동기화 파일

코드(`.py`)를 수정할 때마다 아래 파일들을 **항상 최신 상태로 유지**해야 한다.
변경이 필요 없는 파일도 **확인 후 확인했음을 명시**해야 한다.

| 파일 | 동기화 대상 변경 예시 |
|------|----------------------|
| `Dockerfile` | 시스템 패키지 추가, 빌드 단계 변경, ENV 추가, 포트 변경 |
| `.dockerignore` | 새 폴더/파일 추가로 빌드 컨텍스트에 불필요한 파일이 생길 때 |
| `requirements.txt` | 프로덕션 의존성 추가/제거/버전 변경 |
| `requirements-dev.txt` | 개발/테스트 전용 의존성 추가/제거/버전 변경 |
| `README.md` | 엔드포인트 변경, 환경변수 추가, 구조 변경, 실행 방법 변경 |
| `.env` | 새 설정값(`Settings` 필드) 추가 시 예시 항목과 주석 추가 |
| `docker-compose.yml` | 포트, 볼륨, 환경변수, 서비스 추가/변경 |
| `tests/test_scenarios.md` | 테스트 케이스 추가/제거/변경, 엔드포인트 동작 변경 시 |

### 동기화 순서

1. `.py` 코드 수정
2. `requirements.txt` / `requirements-dev.txt` 업데이트
3. `Dockerfile` 업데이트
4. `.dockerignore` 확인 및 업데이트
5. `docker-compose.yml` 업데이트
6. `.env` 업데이트 (새 설정값이 생긴 경우)
7. `README.md` 업데이트
8. `tests/test_scenarios.md` 업데이트

---

## 8. requirements 분리 규칙

- `requirements.txt` — **프로덕션 런타임**에 필요한 패키지만 포함
- `requirements-dev.txt` — **개발/테스트 전용** 패키지 포함 (`pytest`, `httpx`, `mypy` 등)
  - 첫 줄에 `-r requirements.txt` 를 포함해 프로덕션 의존성을 상속한다.
- `Dockerfile`은 `requirements.txt`만 설치한다 (개발 도구는 이미지에 포함하지 않음).

---

## 9. 설계 문서 참조

프로젝트의 설계 결정과 구현 플랜은 아래 문서에 기록되어 있다. 관련 작업 시 반드시 참조한다.

### 주석 리팩터링

→ [@docs/superpowers/specs/2026-04-13-comment-refactor-design.md](docs/superpowers/specs/2026-04-13-comment-refactor-design.md) — 과도한 주석 제거 및 기능적 주석 간결화 설계

### 네이밍 규칙

→ [@docs/superpowers/specs/2026-04-14-naming-conventions-design.md](docs/superpowers/specs/2026-04-14-naming-conventions-design.md) — 함수 동사 테이블, 기존 함수 리네임 맵
→ [@docs/superpowers/plans/2026-04-14-naming-conventions-rename.md](docs/superpowers/plans/2026-04-14-naming-conventions-rename.md) — 리네임 구현 플랜

### 설정값 관리 (.env)

→ [@docs/superpowers/specs/2026-04-14-env-config-design.md](docs/superpowers/specs/2026-04-14-env-config-design.md) — 설정값 3분류 체계 및 배치 패턴
→ [@docs/superpowers/plans/2026-04-14-env-config.md](docs/superpowers/plans/2026-04-14-env-config.md) — .env 통합 구현 플랜

### OCR 라우팅

→ [@docs/superpowers/specs/2026-04-15-ocr-routing-design.md](docs/superpowers/specs/2026-04-15-ocr-routing-design.md) — 컨텐츠 기반 엔진 선택 설계 (Tesseract → VLM 폴백)
→ [@docs/superpowers/plans/2026-04-15-ocr-routing.md](docs/superpowers/plans/2026-04-15-ocr-routing.md) — OCR 라우팅 구현 플랜

### VLM 구현

→ [@docs/superpowers/specs/2026-04-15-vlm-design.md](docs/superpowers/specs/2026-04-15-vlm-design.md) — GPT-4V 기반 VLM 폴백 설계
→ [@docs/superpowers/plans/2026-04-15-vlm-implementation.md](docs/superpowers/plans/2026-04-15-vlm-implementation.md) — VLM 구현 플랜
