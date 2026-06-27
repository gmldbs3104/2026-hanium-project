"""
AI 모델 어댑터 모듈

백엔드와 AI 모델 트랙의 연결 지점(인터페이스)을 정의한다.
AI 모델이 완성되면 각 함수의 내부 구현만 교체하면 된다.
함수 시그니처(입출력 형식)는 변경하지 않는다.

교체 대상 함수 3개:
  1. lstm_refine_grouping    — 획 그룹핑 2차 보정 (LSTM)
  2. lstm_analyze_stroke_order — 획순 분석 (LSTM)
  3. craft_detect_chars      — 문자 영역 탐지 (CRAFT)
"""

from typing import List, Dict, Any
import math


# ────────────────────────────────────────────────────────────────
# 1. LSTM 획 그룹핑 보정 (SFR-004C)
# ────────────────────────────────────────────────────────────────

def lstm_refine_grouping(
    stroke_groups: List[List[Dict[str, Any]]],
) -> List[List[Dict[str, Any]]]:
    """
    규칙 기반 1차 그룹핑 결과를 LSTM으로 보정한다.

    [AI팀 구현 스펙]
    Input:
        stroke_groups: 규칙 기반으로 묶인 획 그룹 리스트
            [
                [  # 한 문자 후보
                    {
                        "stroke_id": str,
                        "points": [
                            {"x": float, "y": float, "pressure": float, "timestamp": int},
                            ...
                        ]
                    },
                    ...
                ],
                ...
            ]

    Output:
        보정된 stroke_groups (형식 동일)
        - 잘못 묶인 획은 분리, 잘못 나뉜 획은 합쳐서 반환
        - 입력과 동일한 구조를 유지해야 함

    현재: placeholder — 1차 결과를 그대로 반환
    교체: LSTM 분류 결과로 재그룹핑
    """
    return stroke_groups


# ────────────────────────────────────────────────────────────────
# 2. LSTM 획순 분석 (SFR-005C)
# ────────────────────────────────────────────────────────────────

def lstm_analyze_stroke_order(
    strokes: List[Dict[str, Any]],
    expected_sequence: List[str],
) -> Dict[str, Any]:
    """
    한 문자를 구성하는 획들의 순서가 올바른지 분석한다.

    [AI팀 구현 스펙]
    Input:
        strokes: 한 문자를 구성하는 획 리스트 (char_group["strokes"])
            [
                {
                    "stroke_id": str,
                    "points": [
                        {"x": float, "y": float, "pressure": float, "timestamp": int},
                        ...
                    ]
                },
                ...
            ]
        expected_sequence: 표준 DB의 올바른 획순 레이블 리스트
            예) ["horizontal", "vertical", "dot"]

    Output:
        {
            "expected_sequence": List[str],   # 표준 획순
            "actual_sequence":   List[str],   # 모델이 인식한 실제 획순
            "error_count":       int,         # 틀린 획 수
            "corrections":       List[str]    # 교정 메시지 (선택)
        }

    현재: placeholder — stroke 개수 비교만 수행
    교체: 각 stroke의 방향 벡터 시퀀스를 LSTM에 입력해 획순 분류
    """
    actual_sequence = [f"stroke_{i}" for i in range(len(strokes))]
    error_count = abs(len(expected_sequence) - len(actual_sequence)) if expected_sequence else 0

    return {
        "expected_sequence": expected_sequence,
        "actual_sequence": actual_sequence,
        "error_count": error_count,
        "corrections": [],
    }


# ────────────────────────────────────────────────────────────────
# 3. CRAFT 문자 영역 탐지 (SFR-004I)
# ────────────────────────────────────────────────────────────────

def craft_detect_chars(
    binary_image_list: List[List[int]],
    image_width: int,
    image_height: int,
) -> List[Dict[str, Any]]:
    """
    이진화 이미지에서 문자 영역 Bounding Box를 탐지한다.

    [AI팀 구현 스펙]
    Input:
        binary_image_list: 이진화 이미지를 2D 리스트로 변환한 값
            (0 = 배경, 255 = 전경/획)
            shape: [image_height][image_width]
        image_width:  원본 이미지 너비 (px)
        image_height: 원본 이미지 높이 (px)

    Output:
        [
            {
                "char_id":      str,    # "char_0", "char_1", ...
                "bounding_box": {
                    "x":      float,   # 좌상단 x (px)
                    "y":      float,   # 좌상단 y (px)
                    "width":  float,   # 너비 (px)
                    "height": float,   # 높이 (px)
                },
                "angle": float,        # 기울기 (degree, 시계방향 양수)
                "confidence": float    # 탐지 신뢰도 0.0~1.0
            },
            ...
        ]
        - 좌상단 → 우하단 순서로 정렬해서 반환

    현재: placeholder — OpenCV contour 기반 탐지, angle=0
    교체: CRAFT 모델 추론 결과 반환
    """
    import cv2
    import numpy as np

    binary_image = np.array(binary_image_list, dtype=np.uint8)
    h, w = binary_image.shape
    min_area = h * w * 0.0002
    max_area = h * w * 0.4

    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if min_area <= area <= max_area:
            x, y, cw, ch = cv2.boundingRect(contour)
            results.append({
                "bounding_box": {"x": float(x), "y": float(y), "width": float(cw), "height": float(ch)},
                "angle": 0.0,
                "confidence": 1.0,
            })

    row_height = max(h / 10, 1)
    results.sort(key=lambda b: (
        int(b["bounding_box"]["y"] / row_height),
        b["bounding_box"]["x"],
    ))
    for i, r in enumerate(results):
        r["char_id"] = f"char_{i}"

    return results
