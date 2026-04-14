# syntax=docker/dockerfile:1
# BuildKit 활성화 선언 — 캐시 마운트(--mount=type=cache) 사용에 필요
# 빌드 시: docker buildx build . 또는 DOCKER_BUILDKIT=1 docker build .
#
# [변경 이력]
#   - EasyOCR 제거에 따라 아래 두 단계 삭제:
#       1) pip install torch torchvision --index-url .../cpu  (수 GB 규모)
#       2) python -c "import easyocr; easyocr.Reader(...)"    (모델 사전 다운로드)
#       3) ENV HOME=/app  (EasyOCR 모델 저장 경로 고정 목적이었으므로 불필요)
#     결과적으로 이미지 빌드 시간과 최종 이미지 크기가 크게 감소한다.

FROM python:3.11-slim

# 시스템 의존성 설치
# --mount=type=cache : apt 캐시를 이미지 레이어 밖에 보관
#   → 재빌드 시 이미 받은 .deb 파일을 재다운로드하지 않음
#   → rm -rf /var/lib/apt/lists/* 불필요 (캐시가 최종 이미지에 포함되지 않음)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl

# tesseract-ocr     : Tesseract OCR 엔진 바이너리 (pytesseract의 런타임 의존성)
# tesseract-ocr-kor : 한국어 학습 데이터 (.traineddata)
# tesseract-ocr-eng : 영어 학습 데이터
# poppler-utils     : pdf2image가 PDF → 이미지 변환에 사용하는 pdftoppm 포함
# libgl1            : OpenCV(cv2) 런타임에 필요한 OpenGL 라이브러리
# libglib2.0-0      : OpenCV 런타임 의존성
# libgomp1          : OpenMP 병렬 처리 라이브러리 (Tesseract 내부 사용)
# curl              : HEALTHCHECK 명령어에서 /health 엔드포인트 호출에 사용

WORKDIR /app

COPY requirements.txt .

# Python 의존성 설치
# --mount=type=cache : pip이 내려받은 wheel 파일을 이미지 레이어 밖에 보관
#   → requirements.txt가 바뀌어도 이미 받은 wheel은 재다운로드하지 않음
#   → --no-cache-dir 옵션 제거 (캐시를 적극 활용하기 위함)
# torch / torchvision 별도 설치 단계 제거:
#   EasyOCR 제거로 torch 의존성이 사라졌으므로 CPU 전용 인덱스 설정이 불필요하다.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 비루트 사용자 생성 및 디렉터리 준비
# 컨테이너를 root로 실행하면 취약점 악용 시 호스트까지 영향을 줄 수 있다.
# 최소 권한 원칙(Principle of Least Privilege)에 따라 비루트 사용자를 사용한다.
#
# chown -R : /app 전체를 appuser 소유로 변경 (uploads, temp 포함)
RUN useradd --no-create-home --shell /bin/false appuser \
    && mkdir -p uploads temp \
    && chown -R appuser:appuser /app

# --chown 플래그로 복사 시점에 소유권 지정
COPY --chown=appuser:appuser . .

USER appuser

# Tesseract/PyTorch 내부 스레드와 외부 ThreadPool 충돌 방지
# OMP_NUM_THREADS=1 : OpenMP 스레드를 1개로 고정.
#   extractor.py의 ThreadPoolExecutor가 전체 병렬성을 제어하도록 하기 위함.
#   이 값이 없으면 Tesseract 내부 스레드와 외부 스레드가 경쟁하여
#   성능 저하 또는 충돌이 발생할 수 있다.
ENV OMP_NUM_THREADS=1

EXPOSE 8000

# 헬스체크: 30초마다 /health 엔드포인트를 호출해 서버 상태를 확인한다.
# --start-period=60s : 서버 기동 시간을 고려하여 초기 60초는 실패해도 무시.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
