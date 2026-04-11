FROM python:3.11-slim

# 시스템 의존성
#   tesseract-ocr         : OCR 엔진 본체
#   tesseract-ocr-kor     : 한국어 언어팩
#   tesseract-ocr-eng     : 영어 언어팩 (기본 포함이지만 명시)
#   poppler-utils         : pdf2image가 PDF → 이미지 변환에 사용
#   libgl1 / libglib2.0-0 : OpenCV 런타임 의존성
#   libgomp1              : OpenCV / numpy 병렬 연산 의존성
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads temp

# Tesseract 내부 스레드와 외부 ThreadPool 충돌 방지
ENV OMP_THREAD_LIMIT=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
