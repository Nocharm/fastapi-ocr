# VLM 구현 설계
**Date:** 2026-04-15
**Scope:** `app/services/vlm.py` 구현 + 연동 파일 동기화

---

## 1. 배경 및 목표

현재 `run_vlm()`은 `NotImplementedError`를 발생시키는 stub 상태다.
Tesseract OCR 신뢰도가 `very_low`일 때 VLM 폴백이 트리거되지만 실제 동작하지 않는다.

**목표:** GPT-4V(gpt-4o)로 우선 구현하고, 추후 내부 GPU의 Qwen 로컬 모델로 교체 가능한 구조를 유지한다.

---

## 2. 전체 구조

변경 범위는 `app/services/vlm.py` 내부와 연동 설정 파일에 한정된다.
호출부(`extractor.py`의 `run_ocr_with_fallback()`)는 인터페이스 변경 없음.

```
run_vlm(image: np.ndarray) -> dict
  │
  ├─ 1. OPENAI_API_KEY 미설정 시 NotImplementedError (조기 체크)
  ├─ 2. numpy 배열 → PNG bytes → base64 인코딩
  ├─ 3. OpenAI client.chat.completions.create() 호출
  │       model: settings.vlm_model (기본값: gpt-4o)
  │       messages: [system 프롬프트 + user: base64 이미지]
  │       max_tokens: settings.vlm_max_tokens (기본값: 1024)
  ├─ 4. 응답 텍스트 파싱
  ├─ 5. 신뢰도 계산: 텍스트 길이 → 0~100 선형 매핑
  └─ 6. {"text", "confidence", "quality_flag"} 반환
```

---

## 3. OCR 프롬프트

```
You are an OCR engine. Extract all text from the image exactly as it appears.
- Preserve the original layout, line breaks, and spacing.
- Support Korean and English text.
- Accurately transcribe numbers, symbols, and table content.
- Output only the extracted text. No explanations, no markdown formatting.
```

---

## 4. 신뢰도 휴리스틱

GPT-4V는 단어별 신뢰도를 반환하지 않으므로 텍스트 길이로 근사한다.

```python
# VLM_CONF_TEXT_LIMIT: 신뢰도 100에 대응하는 텍스트 길이 상한 (문자 수)
# 실제 문서는 수백~수천 자이므로 500자를 넘으면 충분히 추출된 것으로 간주한다.
VLM_CONF_TEXT_LIMIT = 500

confidence = min(len(text) / VLM_CONF_TEXT_LIMIT * 100, 100.0)
```

| 텍스트 길이 | confidence | quality_flag |
|---|---|---|
| 0자 | 0.0 | very_low |
| 200자 | 40.0 | low |
| 350자 | 70.0 | medium |
| 500자+ | 100.0 | high |

`quality_flag`는 기존 `_get_quality_flag()`를 재사용한다 (임계값: high≥80, medium≥60, low≥40).

---

## 5. 에러 처리

**API 호출 실패:** `run_vlm()`은 예외를 잡지 않는다. 호출부에서 폴백 처리.

**현재 `extractor.py` 문제:** `except NotImplementedError`만 잡고 있어 `openai.OpenAIError` 등 API 오류가 Tesseract 폴백으로 이어지지 않는다. `except Exception`으로 넓힌다.

**API 키 미설정:** `run_vlm()` 진입 시 `settings.openai_api_key`가 빈 문자열이면 즉시 `NotImplementedError`를 발생시켜 Tesseract 결과를 유지한다.

---

## 6. 설정 연동

CLAUDE.md 규칙 §9 분류 기준 적용:

| 설정값 | 분류 | 배치 |
|---|---|---|
| `OPENAI_API_KEY` | 환경 설정 | `.env` + `Settings` |
| `VLM_MODEL` | 튜닝 파라미터 | `.env` + `Settings` |
| `VLM_MAX_TOKENS` | 튜닝 파라미터 | `.env` + `Settings` |
| `VLM_CONF_TEXT_LIMIT` | 비즈니스 로직 상수 | `vlm.py` 모듈 상수만 |

---

## 7. 변경 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `app/services/vlm.py` | `run_vlm()` 구현 (OpenAI GPT-4V) |
| `app/core/config.py` | `openai_api_key`, `vlm_model`, `vlm_max_tokens` 필드 추가 |
| `.env` | `OPENAI_API_KEY`, `VLM_MODEL`, `VLM_MAX_TOKENS` 항목 추가 |
| `requirements.txt` | `openai` 패키지 추가 |
| `app/services/extractor.py` | `except NotImplementedError` → `except Exception` |
| `docker-compose.yml` | `OPENAI_API_KEY` 환경변수 참조 추가 |
| `Dockerfile` | 변경 없음 (확인) |
| `.dockerignore` | 변경 없음 (확인) |
| `tests/test_ocr.py` | VLM mock 테스트 추가 |
| `tests/test_scenarios.md` | VLM 시나리오 추가 |
| `README.md` | `OPENAI_API_KEY` 환경변수 설명 추가 |

---

## 8. 로컬 Qwen 전환 시

`run_vlm()` 내부만 교체한다. 구체적으로:
- OpenAI 클라이언트 제거
- 로컬 모델 로드 로직으로 대체
- `OPENAI_API_KEY` 설정 불필요
- 호출부(`extractor.py`) 변경 없음
- 인터페이스 (`{"text", "confidence", "quality_flag"}` 반환) 유지 필수
