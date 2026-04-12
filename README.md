# OCR API

이미지와 PDF 파일에서 텍스트와 표를 추출해 페이지별 구조화된 JSON으로 반환하는 FastAPI 기반 OCR 서버입니다.

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| 웹 프레임워크 | [FastAPI](https://fastapi.tiangolo.com/) |
| 웹 서버 | [Uvicorn](https://www.uvicorn.org/) |
| 이미지 OCR | [EasyOCR](https://github.com/JaidedAI/EasyOCR) |
| PDF 텍스트 직접 추출 | [pdfplumber](https://github.com/jsvine/pdfplumber) |
| PDF 스캔 이미지 OCR | [Tesseract](https://github.com/tesseract-ocr/tesseract) + [pdf2image](https://github.com/Belval/pdf2image) |
| 이미지 전처리 | [OpenCV](https://opencv.org/) |
| 데이터 검증 | [Pydantic](https://docs.pydantic.dev/) |
| 컨테이너 | [Docker](https://www.docker.com/) |

---

## OCR 처리 전략

```
업로드된 파일
├── 이미지 (JPEG / PNG / WebP / TIFF)
│   └── EasyOCR → 텍스트 + 신뢰도 반환
│
└── PDF
    └── 페이지별 독립 판단
        ├── 텍스트 레이어 ≥ 50자  →  pdfplumber 직접 추출 (method: "direct")
        └── 텍스트 레이어 < 50자  →  pdf2image + Tesseract OCR 폴백 (method: "ocr")
```

- 한 페이지가 `direct`여도 다른 페이지는 독립적으로 `ocr` 방식을 사용할 수 있습니다.
- OCR 페이지는 Laplacian 분산으로 이미지 선명도를 평가하고, 전처리 후 품질이 개선될 때만 적용합니다.
- Tesseract 단어별 신뢰도가 기준 미만(`OCR_WORD_CONF_MIN`, 기본 30)인 단어는 결과에서 제외합니다.

---

## 폴더 구조

```
FastAPI_Project/
├── app/
│   ├── main.py                      # FastAPI 앱 진입점, 라우터 등록
│   ├── api/
│   │   └── routes/
│   │       └── ocr.py               # 업로드 엔드포인트, 파일 타입 분기
│   ├── core/
│   │   └── config.py                # 환경변수 및 상수 (신뢰도 등급, Tesseract 옵션)
│   ├── services/
│   │   ├── easyocr_service.py       # 이미지 OCR 처리 (EasyOCR)
│   │   └── extractor.py             # PDF 처리 (pdfplumber + Tesseract 하이브리드)
│   └── schemas/
│       └── ocr.py                   # PageResult, OCRResponse 데이터 구조
├── tests/
│   ├── test_ocr.py                  # TC-01 ~ TC-14 자동화 테스트
│   └── test_scenarios.md            # 테스트 시나리오 명세
├── uploads/                         # 업로드 파일 저장 (git 추적 제외)
├── temp/                            # PDF 임시 파일 저장 (git 추적 제외)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env                             # 환경변수 설정 (git 추적 제외)
```

---

## 시작하기

### 사전 요구사항

- Python 3.11
- Tesseract 5.x + 한국어 언어팩 (`tesseract-ocr-kor`)
- poppler (pdf2image 의존성)
- Docker (Docker 실행 시)

**macOS 설치 예시**

```bash
brew install tesseract tesseract-lang poppler
```

**Ubuntu 설치 예시**

```bash
apt-get install -y tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng poppler-utils
```

### 로컬 실행

**1. 가상환경 생성 및 활성화**

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

**2. 패키지 설치**

torch/torchvision은 CPU 전용 버전을 먼저 설치해야 합니다. (그렇지 않으면 CUDA 버전 ~2 GB가 설치됩니다.)

```bash
pip install torch==2.2.2 torchvision==0.17.2 \
    --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

**3. 환경변수 설정**

`.env` 파일을 프로젝트 루트에 생성합니다.

```env
UPLOAD_DIR=uploads
TEMP_DIR=temp
EASYOCR_LANGUAGES=["en","ko"]
OCR_TEXT_THRESHOLD=50
OCR_MAX_WORKERS=4
OCR_WORD_CONF_MIN=30
# TESSERACT_CMD=           # 기본값: 시스템 PATH에서 자동 탐색
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

Dockerfile에 BuildKit 캐시 마운트가 적용되어 있으므로 재빌드 시 apt/pip 캐시를 재사용합니다.

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

> Docker 이미지 빌드 시 EasyOCR 모델이 이미지에 포함되어 콜드 스타트 없이 바로 서비스됩니다.

---

## API 사용법

### `POST /ocr/upload`

파일을 업로드하면 OCR 결과를 페이지별 구조화된 JSON으로 반환합니다.

**지원 파일 형식 및 최대 크기**

| 형식 | MIME 타입 | 최대 크기 |
|---|---|---|
| JPEG | `image/jpeg` | 50 MB |
| PNG | `image/png` | 50 MB |
| WebP | `image/webp` | 50 MB |
| TIFF | `image/tiff` | 50 MB |
| PDF | `application/pdf` | 50 MB |

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
  "filename": "document.pdf",
  "pages": [
    {
      "page_num": 0,
      "text": "청구서\n합계 100,000원",
      "tables": ["| 항목 | 금액 |\n| --- | --- |\n| 서비스 | 100,000 |"],
      "method": "direct",
      "confidence": null,
      "quality_flag": "",
      "error": null,
      "success": true
    },
    {
      "page_num": 1,
      "text": "스캔된 텍스트 내용",
      "tables": [],
      "method": "ocr",
      "confidence": 79.41,
      "quality_flag": "medium",
      "error": null,
      "success": true
    }
  ],
  "total": 2,
  "success_count": 2,
  "failed_pages": []
}
```

**응답 필드 설명**

| 필드 | 설명 |
|---|---|
| `method` | `"direct"` = pdfplumber 직접 추출 / `"ocr"` = Tesseract 또는 EasyOCR |
| `confidence` | OCR 평균 신뢰도 (0~100). `direct` 방식은 `null` |
| `quality_flag` | 신뢰도 등급. `direct` 방식은 빈 문자열 |
| `failed_pages` | 처리 실패 페이지 번호 목록 (일부 실패해도 HTTP 200 반환) |

**품질 등급 (`quality_flag`)**

| 등급 | 신뢰도 | 의미 |
|---|---|---|
| `high` | ≥ 80 | 신뢰할 수 있음 |
| `medium` | ≥ 60 | 수용 가능 |
| `low` | ≥ 40 | 재처리 권장 |
| `very_low` | < 40 | 반드시 검토 필요 |

**에러 응답**

| 상태 코드 | 원인 |
|---|---|
| `413` | 파일 크기 50 MB 초과 |
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

| 테스트 | 내용 |
|---|---|
| TC-01 | 헬스체크 |
| TC-02~04 | 이미지 OCR (품질 등급, 포맷 4종) |
| TC-05~08 | PDF 처리 (direct / ocr / 혼합 / 표 포함) |
| TC-09~11 | 입력 유효성 검사 (415 / 422 / 413) |
| TC-12 | 일부 페이지 실패 복구 |
| TC-13~14 | 내부 함수 단위 테스트 (신뢰도 분류, 마크다운 표 변환) |

---

## 환경변수 목록

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `UPLOAD_DIR` | `uploads` | 업로드 파일 저장 경로 |
| `TEMP_DIR` | `temp` | PDF 임시 파일 저장 경로 |
| `EASYOCR_LANGUAGES` | `["en","ko"]` | EasyOCR 인식 언어 목록 |
| `OCR_TEXT_THRESHOLD` | `50` | 직접 추출 최소 글자 수 (미만이면 OCR 폴백) |
| `OCR_MAX_WORKERS` | `4` | PDF 병렬 처리 스레드 수 |
| `OCR_WORD_CONF_MIN` | `30` | Tesseract 단어 최소 신뢰도 (미만 단어 제외) |
| `TESSERACT_CMD` | `` | Tesseract 실행 파일 경로 (비어있으면 PATH 자동 탐색) |

---

## 코드 읽기 순서

처음 코드를 파악할 때는 아래 순서로 읽으면 흐름을 따라가기 쉽습니다.

```
1. app/schemas/ocr.py               # 데이터 구조 정의 (PageResult, OCRResponse)
2. app/core/config.py               # 설정값 및 상수 관리
3. app/main.py                      # 앱 진입점 및 라우터 등록
4. app/api/routes/ocr.py            # HTTP 요청 수신 및 파일 타입 분기
5. app/services/easyocr_service.py  # 이미지 OCR 처리
6. app/services/extractor.py        # PDF 하이브리드 추출 (pdfplumber + Tesseract)
7. tests/test_ocr.py                # 자동화 테스트 (TC-01~TC-14)
```
