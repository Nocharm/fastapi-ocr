# syntax=docker/dockerfile:1
# BuildKit 활성화 선언 — 캐시 마운트(--mount=type=cache) 사용에 필요
# 빌드 시: docker buildx build . 또는 DOCKER_BUILDKIT=1 docker build .

FROM python:3.11-slim

# 시스템 의존성 설치
# --mount=type=cache : apt 캐시를 이미지 레이어 밖에 보관
#   → 재빌드 시 이미 받은 .deb 파일을 재다운로드하지 않음
#   → rm -rf /var/lib/apt/lists/* 불필요 (캐시가 이미지에 포함되지 않음)
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

WORKDIR /app

COPY requirements.txt .

# torch CPU 전용 버전 먼저 설치
# --mount=type=cache : pip이 내려받은 wheel 파일을 이미지 레이어 밖에 보관
#   → requirements.txt가 바뀌어도 이미 받은 wheel은 재다운로드하지 않음
#   → --no-cache-dir 옵션 제거 (캐시를 적극 활용하기 위함)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch==2.2.2 torchvision==0.17.2 \
    --index-url https://download.pytorch.org/whl/cpu

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# EasyOCR 모델 사전 다운로드 (이미지에 포함시켜 콜드 스타트 제거)
# 캐시 마운트를 쓰지 않는 이유: 모델이 최종 이미지 레이어에 포함되어야 함
RUN python -c "import easyocr; easyocr.Reader(['en', 'ko'], gpu=False)"

# 비루트 사용자 생성 및 디렉터리 준비 — COPY 전에 수행
# (COPY 후에 useradd/mkdir 하면 레이어 순서가 꼬여 캐시 효율 저하)
RUN useradd --no-create-home --shell /bin/false appuser \
    && mkdir -p uploads temp

# --chown 플래그로 복사 시점에 소유권 지정
# 기존 방식 문제: COPY . . 후 RUN chown -R → 전체 파일을 복제한 새 레이어 생성
# 개선된 방식:    COPY --chown=... .  → 복사와 소유권 지정을 단일 레이어로 처리
COPY --chown=appuser:appuser . .

USER appuser

# Tesseract 내부 스레드와 외부 ThreadPool 충돌 방지
ENV OMP_THREAD_LIMIT=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
