# OCR API

이미지와 PDF 파일에서 텍스트를 추출해 마크다운 형식으로 반환하는 FastAPI 기반 OCR 서버입니다.

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| 웹 프레임워크 | [FastAPI](https://fastapi.tiangolo.com/) |
| 웹 서버 | [Uvicorn](https://www.uvicorn.org/) |
| 이미지 OCR | [EasyOCR](https://github.com/JaidedAI/EasyOCR) |
| PDF → 마크다운 | [Marker](https://github.com/VikParuchuri/marker) |
| 데이터 검증 | [Pydantic](https://docs.pydantic.dev/) |
| 패키지 관리 | [uv](https://github.com/astral-sh/uv) |
| 컨테이너 | [Docker](https://www.docker.com/) |

---

## OCR 엔진 역할 분담

```
업로드된 파일
├── 이미지 (jpg, png, webp, tiff) → EasyOCR  → 마크다운 텍스트 반환
└── PDF                           → Marker   → 마크다운 텍스트 반환
```

- **EasyOCR** : 이미지에서 한/영 텍스트를 인식
- **Marker** : PDF 문서의 구조(제목, 본문, 표 등)를 분석해 마크다운으로 변환

---

## 폴더 구조

```
FastAPI_Project/
├── app/
│   ├── main.py                   # FastAPI 앱 진입점, 라우터 등록
│   ├── api/
│   │   └── routes/
│   │       └── ocr.py            # 업로드 엔드포인트, 파일 타입 분기
│   ├── core/
│   │   └── config.py             # 환경변수 및 앱 설정
│   ├── services/
│   │   ├── easyocr_service.py    # 이미지 OCR 처리 로직
│   │   └── marker_service.py     # PDF OCR 처리 로직
│   └── schemas/
│       └── ocr.py                # 요청/응답 Pydantic 모델
├── tests/
│   └── test_ocr.py               # API 테스트
├── uploads/                      # 업로드 파일 저장 (git 추적 제외)
├── temp/                         # PDF 임시 파일 저장 (git 추적 제외)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env                          # 환경변수 설정 (git 추적 제외)
```

---

## 시작하기

### 사전 요구사항

- Python 3.11
- [uv](https://github.com/astral-sh/uv) 또는 pip
- Docker (Docker 실행 시)

### 로컬 실행

**1. 가상환경 생성 및 활성화**

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

**2. 패키지 설치**

```bash
uv pip install -r requirements.txt
```

**3. 환경변수 설정**

`.env` 파일을 프로젝트 루트에 생성합니다.

```env
UPLOAD_DIR=uploads
TEMP_DIR=temp
EASYOCR_LANGUAGES=["en","ko"]
```

**4. 서버 실행**

```bash
uvicorn app.main:app --reload
```

서버가 실행되면 아래 주소에서 접근할 수 있습니다.

| 주소 | 설명 |
|---|---|
| http://localhost:8000 | API 서버 |
| http://localhost:8000/docs | Swagger UI (API 문서 + 테스트) |
| http://localhost:8000/health | 서버 상태 확인 |

---

### Docker 실행

**1. 이미지 빌드 및 컨테이너 실행**

```bash
docker-compose up --build
```

**2. 백그라운드 실행**

```bash
docker-compose up --build -d
```

**3. 컨테이너 중지**

```bash
docker-compose down
```

---

## API 사용법

### `POST /ocr/upload`

파일을 업로드하면 OCR 결과를 마크다운 형식으로 반환합니다.

**지원 파일 형식**

| 형식 | MIME 타입 |
|---|---|
| JPEG | `image/jpeg` |
| PNG | `image/png` |
| WebP | `image/webp` |
| TIFF | `image/tiff` |
| PDF | `application/pdf` |

**요청 예시 (curl)**

```bash
# 이미지 파일
curl -X POST http://localhost:8000/ocr/upload \
  -F "file=@sample.png"

# PDF 파일
curl -X POST http://localhost:8000/ocr/upload \
  -F "file=@document.pdf"
```

**응답 예시**

```json
{
  "filename": "sample.png",
  "markdown": "## 제목\n\n본문 텍스트가 여기에 들어갑니다."
}
```

**에러 응답**

| 상태 코드 | 원인 |
|---|---|
| `415` | 지원하지 않는 파일 형식 |
| `422` | 파일 없이 요청한 경우 |

---

### `GET /health`

서버 상태를 확인합니다.

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok" }
```

---

## 테스트

```bash
pytest tests/ -v
```

---

## 환경변수 목록

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `UPLOAD_DIR` | `uploads` | 업로드 파일 저장 경로 |
| `TEMP_DIR` | `temp` | PDF 임시 파일 저장 경로 |
| `EASYOCR_LANGUAGES` | `["en","ko"]` | EasyOCR 인식 언어 목록 |

---

## 코드 읽기 순서

처음 코드를 파악할 때는 아래 순서로 읽으면 흐름을 따라가기 쉽습니다.

```
1. app/schemas/ocr.py            # 데이터 구조 정의
2. app/core/config.py            # 설정값 관리
3. app/main.py                   # 앱 진입점 및 라우터 등록
4. app/api/routes/ocr.py         # HTTP 요청 수신 및 분기
5. app/services/easyocr_service.py  # 이미지 OCR 처리
6. app/services/marker_service.py   # PDF OCR 처리
```
