# =====================================================================
# [읽기 순서 6/6] app/services/marker_service.py
#
# 이 파일의 역할:
#   PDF 파일을 받아서 Marker 라이브러리로 문서 구조를 분석하고
#   마크다운 형식의 문자열로 변환해서 반환한다.
#
# ┌─────────────────────────────────────────────────────────┐
# │  비유: 음식점의 "PDF 담당 주방"                          │
# │                                                         │
# │  이미지 주방(easyocr_service)이 사진 속 글자를 읽는다면 │
# │  이 주방은 "문서의 구조"까지 파악한다.                  │
# │                                                         │
# │  예) "이 줄은 제목이고, 이건 표이고, 이건 본문이네"     │
# │  → 마크다운의 #, |, ** 등으로 구조를 살려서 변환        │
# │                                                         │
# │  단, Marker는 재료(PDF)를 직접 손에 받지 않고           │
# │  "냉장고(파일 경로)"에서 꺼내야 한다.                   │
# │  그래서 임시로 냉장고에 넣었다가 꺼낸 뒤 다시 버린다.  │
# └─────────────────────────────────────────────────────────┘
#
# EasyOCR과 Marker의 차이:
#   EasyOCR : 이미지에서 "글자"만 뽑아냄 (텍스트 인식)
#   Marker  : PDF의 "구조"까지 이해함 (레이아웃 분석 + 마크다운 변환)
#             내부적으로 Surya OCR + 레이아웃 분석 모델을 함께 사용
# =====================================================================

import tempfile  # 임시 파일을 안전하게 생성/관리하는 파이썬 표준 라이브러리
import os        # 파일 삭제 등 운영체제 작업을 위한 파이썬 표준 라이브러리

from fastapi import UploadFile
from marker.convert import convert_single_pdf  # PDF → 마크다운 변환 핵심 함수
from marker.models import load_all_models      # Marker에 필요한 모든 모델을 로딩

from app.core.config import settings


# ---------------------------------------------------------------
# 싱글턴 패턴 (easyocr_service.py와 동일한 이유)
#
# 비유: "Marker 주방장 팀이 현재 출근해 있는가?" 를 기록하는 칠판
#   Marker는 여러 딥러닝 모델(레이아웃, OCR, 수식 등)을 함께 사용해서
#   EasyOCR보다도 로딩이 더 무거움 → 재사용이 더욱 중요
# ---------------------------------------------------------------
_models = None


def get_models():
    """Marker 모델들을 반환. 최초 1회만 로딩하고 이후엔 재사용."""

    global _models

    if _models is None:
        # load_all_models() : Marker가 필요로 하는 모든 딥러닝 모델을 한 번에 로딩
        #
        # Marker 내부에서 사용하는 모델들:
        #   - 레이아웃 분석 모델  : 제목/본문/표/그림 영역을 구분
        #   - Surya OCR 모델     : 실제 글자 인식
        #   - 수식 인식 모델     : 수학 공식을 LaTeX로 변환
        #
        # 비유: 레스토랑에 여러 명의 전문 요리사(모델)를 한꺼번에 출근시키는 것.
        #       첫 번째 주문 때만 기다리면 이후엔 항상 대기 상태.
        _models = load_all_models()

    return _models


async def extract_pdf(file: UploadFile) -> str:
    """
    업로드된 PDF를 마크다운 문자열로 변환해서 반환.

    임시 파일이 필요한 이유:
        FastAPI의 UploadFile은 파일 내용을 메모리(bytes)에 들고 있음.
        하지만 Marker의 convert_single_pdf()는 "파일 경로(문자열)"를 입력으로 받음.
        → 메모리의 bytes를 디스크에 임시로 저장한 뒤 경로를 전달해야 함.

        비유: 택배로 받은 재료(bytes)를 요리사가 쓸 수 있도록
              일단 냉장고(temp/)에 넣어두고 경로를 알려주는 것.
    """

    contents = await file.read()  # PDF 파일의 내용을 bytes로 읽음

    # ---------------------------------------------------------------
    # 임시 파일 생성
    #
    # tempfile.NamedTemporaryFile() : 임시 파일을 안전하게 생성
    #
    # 비유: 재사용 불가 일회용 냉장고 칸
    #   - 사용할 때만 만들고
    #   - 다 쓰면 반드시 비워야(삭제해야) 하는 칸
    #
    # 파라미터 설명:
    #   dir=settings.temp_dir : temp/ 폴더 안에 생성
    #                           지정하지 않으면 OS의 기본 임시 폴더에 생김
    #   suffix=".pdf"         : 파일명 끝에 .pdf 붙이기
    #                           Marker가 확장자를 보고 PDF임을 판단하기 때문에 필수
    #   delete=False          : with 블록이 끝나도 자동으로 삭제하지 않음
    #
    # delete=False인 이유:
    #   with 블록이 끝나면 파일이 "닫힌다(closed)".
    #   하지만 바로 아래 try 블록에서 파일 경로(tmp_path)로 다시 접근해야 하므로
    #   자동 삭제를 막고 우리가 직접 삭제(os.remove)한다.
    # ---------------------------------------------------------------
    with tempfile.NamedTemporaryFile(
        dir=settings.temp_dir, suffix=".pdf", delete=False
    ) as tmp:
        tmp.write(contents)  # 메모리의 PDF bytes를 임시 파일에 저장
        tmp_path = tmp.name  # 임시 파일의 전체 경로를 기억해둠
                             # 예) "temp/tmpXk39ab.pdf"

    # ---------------------------------------------------------------
    # try / finally 패턴
    #
    # 비유: 냉장고에서 재료를 꺼내 요리한 뒤 반드시 냉장고를 비우는 규칙
    #
    # try    : 실제 작업(요리)을 시도
    # finally: 요리가 성공하든 실패(에러)하든 "냉장고 비우기(임시파일 삭제)"는 반드시 실행
    #
    # finally 없이 그냥 os.remove를 쓰면:
    #   convert_single_pdf()에서 에러가 발생할 경우
    #   os.remove()가 실행되지 않아 임시 파일이 계속 쌓임 → 디스크 용량 부족 위험
    # ---------------------------------------------------------------
    try:
        models = get_models()  # 싱글턴 모델 가져오기

        # convert_single_pdf() : PDF 파일을 분석해서 마크다운으로 변환
        #
        # 반환값이 3개짜리 튜플: (markdown, metadata, images)
        #   markdown : 변환된 마크다운 문자열 ← 우리가 필요한 것
        #   metadata : 페이지 수, 언어 등 문서 정보 (사용 안 함)
        #   images   : 문서 내 이미지들 (사용 안 함)
        #
        # _ (언더스코어) : 필요 없는 반환값을 버릴 때 쓰는 관례적 표시
        #   비유: 택배에서 필요한 물건만 꺼내고 포장재는 버리는 것
        markdown, _, _ = convert_single_pdf(tmp_path, models)

        return markdown

    finally:
        # 성공하든 실패하든 임시 파일은 반드시 삭제
        # os.remove() : 지정한 경로의 파일을 삭제
        #
        # 비유: 요리가 완성되든 실패하든
        #       일회용 냉장고 칸은 반드시 비워야 하는 규칙
        os.remove(tmp_path)
