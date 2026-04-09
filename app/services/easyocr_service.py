# =====================================================================
# [읽기 순서 5/6] app/services/easyocr_service.py
#
# 이 파일의 역할:
#   이미지 파일을 받아서 EasyOCR로 텍스트를 추출하고
#   마크다운 형식의 문자열로 변환해서 반환한다.
#
# ┌─────────────────────────────────────────────────────────┐
# │  비유: 음식점의 "이미지 담당 주방"                       │
# │                                                         │
# │  홀 직원(routes/ocr.py)이 "이미지 주문이요!" 라고 하면  │
# │  이 주방이 받아서 재료(이미지)를 가공(OCR)해            │
# │  완성된 요리(마크다운 텍스트)를 내보낸다.               │
# │                                                         │
# │  주방장(EasyOCR 모델)은 출근하는 데 시간이 걸리므로     │
# │  첫 번째 주문 때만 불러오고(모델 로딩),                 │
# │  이후에는 이미 출근해 있는 주방장이 계속 일한다.        │
# │  (싱글턴 패턴)                                          │
# └─────────────────────────────────────────────────────────┘
# =====================================================================

import easyocr          # OCR 엔진 라이브러리
import numpy as np      # 이미지를 숫자 배열로 변환하는 수치 계산 라이브러리
from fastapi import UploadFile  # 업로드 파일 타입 (타입 힌트용)
from PIL import Image   # 이미지 파일을 열고 처리하는 라이브러리 (Pillow)
import io               # 바이트 데이터를 파일처럼 다루는 파이썬 표준 라이브러리

from app.core.config import settings  # 설정값 (언어 목록 등)


# ---------------------------------------------------------------
# 싱글턴 패턴을 위한 전역 변수
#
# 비유: "주방장이 현재 출근해 있는가?" 를 기록하는 칠판
#   None  → 아직 출근 전 (모델 미로딩)
#   Reader → 이미 출근함 (모델 로딩 완료, 재사용 가능)
#
# 모듈 수준(함수 바깥)에 선언하면 서버가 실행되는 동안 계속 유지된다.
# ---------------------------------------------------------------
_reader = None


def get_reader() -> easyocr.Reader:
    """
    EasyOCR Reader를 반환한다. 최초 1회만 초기화하고 이후엔 재사용.

    반환 타입 힌트 '-> easyocr.Reader':
        이 함수가 easyocr.Reader 타입을 반환한다는 것을 명시.
        실행에는 영향 없고 코드 가독성과 IDE 자동완성을 위해 사용.
    """

    global _reader
    # global 키워드: 함수 안에서 함수 밖의 변수(_reader)를 수정하겠다고 선언.
    # 비유: "나는 개인 수첩이 아니라 사무실 공용 칠판에 쓸 것이다"

    if _reader is None:
        # 칠판이 비어있으면(아직 모델 미로딩이면) 모델을 새로 로딩
        #
        # easyocr.Reader() 가 하는 일:
        #   - 딥러닝 모델 파일(수백 MB)을 디스크에서 메모리로 읽어들임
        #   - 처음 실행 시 인터넷에서 모델을 다운로드하기도 함
        #   - 이 작업이 수 초~수십 초 걸리기 때문에 매 요청마다 하면 안 됨
        #
        # 인자 설명:
        #   settings.easyocr_languages : 인식할 언어 목록 ["en", "ko"]
        #   gpu=False : CPU만 사용. Docker 기본 환경에는 GPU가 없으므로.
        _reader = easyocr.Reader(settings.easyocr_languages, gpu=False)

    # 이미 로딩된 Reader(주방장)를 그대로 반환
    return _reader


async def extract_image(file: UploadFile) -> str:
    """
    업로드된 이미지에서 텍스트를 추출해 마크다운 문자열로 반환.

    처리 흐름:
        바이트 읽기 → Pillow 이미지 → numpy 배열 → EasyOCR → 마크다운
    """

    # await file.read() : 업로드 파일의 내용을 바이트(bytes)로 읽음
    #
    # 비유: 택배 상자를 열어서 내용물을 꺼내는 것
    #   file        = 택배 상자 (메타 정보 포함)
    #   contents    = 상자 안의 실제 내용물 (이미지의 날 것 데이터, bytes)
    #
    # await를 쓰는 이유:
    #   파일 읽기는 디스크/네트워크 I/O 작업이라 시간이 걸린다.
    #   await 덕분에 읽는 동안 서버가 다른 요청을 처리할 수 있다.
    #   비유: 커피 기계 버튼 누르고 다음 손님 주문 받기
    contents = await file.read()

    # io.BytesIO(contents) : 바이트 데이터를 메모리상의 "가상 파일"로 포장
    #
    # 비유: 사진 파일을 하드디스크에 저장하지 않고
    #       메모리 안에 임시 봉투를 만들어서 담아두는 것.
    #       PIL.Image.open()이 "파일 객체"를 기대하기 때문에 이렇게 포장해야 함.
    #
    # .convert("RGB") : 이미지 색상 모드를 RGB로 통일
    #   PNG는 투명도 채널을 가진 RGBA일 수 있고
    #   스캔 문서는 흑백(L 모드)일 수 있어서 통일이 필요하다.
    #   비유: 레시피에 "재료를 모두 같은 크기로 썰어라" 처럼 전처리 단계
    image = Image.open(io.BytesIO(contents)).convert("RGB")

    # np.array(image) : Pillow 이미지 객체를 numpy 숫자 배열로 변환
    #
    # 비유: 그림을 모눈종이 위에 옮겨 각 칸의 색상을 숫자로 표현한 것
    #   이미지 = 픽셀들의 집합
    #   numpy 배열 = [[255,255,255], [0,0,0], ...] 같은 숫자 행렬
    #   EasyOCR의 readtext()가 numpy 배열을 입력으로 요구하기 때문에 변환 필요
    img_array = np.array(image)

    reader = get_reader()  # 싱글턴 Reader 가져오기 (이미 로딩되어 있으면 즉시 반환)

    # reader.readtext() : 이미지에서 텍스트를 인식
    #
    # 반환값 형식: [(바운딩박스, 텍스트, 신뢰도), ...]
    #   바운딩박스 : 텍스트가 있는 영역의 좌표 ([[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
    #   텍스트     : 인식된 문자열 (예: "Hello World")
    #   신뢰도     : 0.0~1.0 사이의 인식 확실성 (1.0에 가까울수록 정확)
    #
    # 예시 반환값:
    #   [([[10,5],[100,5],[100,20],[10,20]], "Hello", 0.97),
    #    ([[10,25],[80,25],[80,40],[10,40]], "World", 0.85)]
    results = reader.readtext(img_array)

    return _to_markdown(results)


def _to_markdown(results: list) -> str:
    """
    EasyOCR 결과 리스트를 마크다운 문자열로 변환.

    함수 이름 앞의 _ (언더스코어):
        이 함수가 이 파일 내부에서만 사용되는 "비공개" 함수라는 관례적 표시.
        비유: 주방 내부에서만 쓰는 도구 (손님한테 보여줄 필요 없음)
    """

    # 리스트 컴프리헨션 + 언패킹 + 필터링을 한 줄로 처리
    #
    # (_, text, confidence) : 튜플 언패킹
    #   _ (언더스코어) : 바운딩박스 값은 필요 없으므로 버린다는 관례적 표시
    #   text          : 인식된 텍스트
    #   confidence    : 신뢰도 (0.0 ~ 1.0)
    #
    # if confidence > 0.3 : 신뢰도 30% 미만은 제외
    #   비유: 흐릿하게 들려서 30% 이하로만 알아들은 말은 받아 적지 않음.
    #         너무 낮은 신뢰도의 텍스트를 포함하면 오인식이 결과에 섞임.
    lines = [text for (_, text, confidence) in results if confidence > 0.3]

    # "\n\n".join(lines) : 텍스트들 사이에 빈 줄을 넣어서 하나의 문자열로 합침
    #
    # 마크다운에서 \n\n (빈 줄)은 "단락 구분"을 의미한다.
    # \n만 쓰면 줄바꿈, \n\n을 써야 단락이 나뉜다.
    #
    # 예시:
    #   lines = ["Hello", "World", "FastAPI"]
    #   결과  = "Hello\n\nWorld\n\nFastAPI"
    return "\n\n".join(lines)
