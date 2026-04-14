# CLAUDE.md — 프로젝트 작업 규칙

이 파일은 Claude Code가 이 프로젝트에서 코드를 수정할 때 반드시 따라야 할 규칙을 정의합니다.

---

## 1. 네이밍 규칙

함수·변수·클래스 명명 규칙은 아래 스펙 문서를 따른다.

→ [@docs/superpowers/specs/2026-04-14-naming-conventions-design.md](docs/superpowers/specs/2026-04-14-naming-conventions-design.md)

**핵심 요약:**
- 함수 첫 단어: `extract` / `get` / `run` / `find` / `make` / `preprocess` / `process` 중 하나
- 금지 동사: `convert`, `detect`, `assess`, `build`, `handle`, `classify`
- bool 반환 함수: `is_` / `has_` 접두사 필수
- 예외는 주석으로 이유 명시 후 허용

---

## 2. 주석 규칙

코드를 수정하거나 추가할 때 **간결하고 의도가 드러나는 주석**을 달아야 한다.

### 주석 작성 기준

- **왜(Why)** 이 코드가 필요한지 한 줄로 설명한다. 코드만 보면 알 수 있는 "무엇(What)" 주석은 달지 않는다.
- **모듈**: 파일 상단에 한 줄 요약 docstring을 반드시 작성한다 (`"""역할 설명."""`).
- **함수/클래스**: 역할과 주의사항만 한두 줄로 적는다. 명백한 것은 생략한다.
- **비자명한 로직** (라이브러리 옵션, 수식, 경쟁 조건 등): 해당 줄 끝 또는 바로 위에 이유를 한 줄로 적는다.
- **상수/설정값**: 단위·허용 범위·변경 시 영향을 인라인으로 적는다.

### 금지 사항

- `# 파일을 읽는다`, `# 결과를 반환한다` 처럼 코드를 그대로 번역한 주석.
- 함수 이름과 똑같은 내용의 docstring.
- 장황한 구분선 블록(`# ---...---`) — 섹션 구분 외에는 사용하지 않는다.

### 간결한 주석 예시

```python
# 내부 OpenMP 스레드와 ThreadPoolExecutor 충돌 방지
os.environ.setdefault("OMP_NUM_THREADS", "1")

def ocr_with_confidence(image: np.ndarray) -> dict:
    """단어별 신뢰도를 필터링해 OCR 결과를 반환. image_to_string() 단독 사용 금지."""
    ...

dpi=300,  # 낮추면 속도 향상, OCR 정확도 하락
```

---

## 3. 코드 변경 시 필수 동기화 파일

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

## 4. requirements 분리 규칙

- `requirements.txt` — **프로덕션 런타임**에 필요한 패키지만 포함
- `requirements-dev.txt` — **개발/테스트 전용** 패키지 포함 (`pytest`, `httpx`, `mypy` 등)
  - 첫 줄에 `-r requirements.txt` 를 포함해 프로덕션 의존성을 상속한다.
- `Dockerfile`은 `requirements.txt`만 설치한다 (개발 도구는 이미지에 포함하지 않음).

---

## 5. 프로젝트 구조 규칙

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

## 6. Docker 규칙

- `Dockerfile`은 **BuildKit** (`# syntax=docker/dockerfile:1`) 을 사용한다.
- apt 캐시와 pip 캐시는 `--mount=type=cache` 로 처리한다 (`rm -rf /var/lib/apt/lists/*` 불필요).
- `torch` / `torchvision`은 CPU 전용 인덱스(`https://download.pytorch.org/whl/cpu`)에서 먼저 설치한다.
- 컨테이너는 **비루트 사용자(`appuser`)** 로 실행한다.
- `ENV OMP_NUM_THREADS=1` 은 항상 유지한다.

---

## 7. 테스트 규칙

- 새 기능 추가 시 `tests/test_ocr.py`에 대응하는 테스트 케이스를 추가한다.
- 외부 엔진(EasyOCR, Tesseract, pdfplumber)은 Mock으로 대체해 테스트 속도를 유지한다.
- 테스트는 `pytest tests/ -v` 로 실행한다.
- `requirements-dev.txt`에 테스트 의존성이 있어야 한다.

---

## 8. 환경변수 규칙

- `.env`는 git에 커밋하지 않는다 (`.gitignore`에 포함).
- 새 설정값을 `Settings`에 추가할 때 `.env`에도 해당 항목(주석 포함)을 추가한다.
- 민감한 값(API 키, 비밀번호)은 절대 코드에 하드코딩하지 않는다.

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

1. `.env` — 단일 진실 공급원: `PORT=8900`
2. `config.py Settings` 필드: `port: int = 8900`
3. `Dockerfile` — `.env` 없을 때 폴백: `ENV PORT=8900`
4. `docker-compose.yml` — `.env` 값 참조: `"${PORT:-8900}:${PORT:-8900}"`

**튜닝 파라미터 — 2단계**

1. `.env` — 값 노출 (Settings 기본값에만 숨기지 않는다): `PDF_DPI=300`
2. `config.py Settings` 필드: `pdf_dpi: int = 300`
3. 코드에서 사용: `dpi=settings.pdf_dpi`

**비즈니스 로직 상수 — Settings 필드만**

`config.py`의 `Settings` 안에 기본값으로 정의한다. `.env` 항목 없음.
변경하려면 `config.py`를 직접 수정한다 (코드 리뷰 없이 배포 환경에서 변경 불가).

### 금지 사항

- 수치·경로를 `.py` 코드 안에 리터럴로 직접 쓰기
- 튜닝 파라미터를 `Settings` 기본값에만 숨기고 `.env`에 미노출
- `config.py` 모듈 상수(`UPPER_SNAKE_CASE`)와 `Settings` 필드에 같은 값 중복 정의
- Docker 관련 환경 설정을 `Dockerfile`에만 하드코딩하고 `.env` 미연동
