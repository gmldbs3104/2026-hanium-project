"""
AI Hub 손글씨 OCR 라벨 → CRAFT Ground Truth Score Map 변환

AI Hub JSON 포맷 (어절/단어 단위 bbox) → 글자(음절) 단위로 분할 → region score map

Region Score : 글자별 bbox 중심에 Gaussian blob
Affinity Score: 사용하지 않음(아래 설명) — 항상 0

왜 affinity를 안 쓰는가
------------------------
CRAFT의 affinity는 원래 "인접 글자가 같은 단어에 속한다"를 학습시켜 추론 시
region+affinity를 연결된 성분으로 묶어 단어 단위 박스를 만들기 위한 신호다
(craft_text_detector.craft_utils.getDetBoxes_core: text_score_comb = text_score + link_score
로 두 맵을 합쳐 connected components를 구함). 이 프로젝트(SFR-004I)가 원하는 건 정반대로
**글자 단위로 분리된** bbox이므로, 인접 글자 사이에 affinity를 학습시키면 추론 파이프라인
(ai/detection/craft_detector.py, craft_text_detector 패키지의 box 병합 로직을 그대로 사용)이
글자들을 다시 단어로 합쳐버려 이 작업 전체의 목적을 무효화한다. 그래서 affinity_map은
항상 0으로 두고(모델이 "인접 글자를 연결하지 말라"를 자연히 학습하도록), region만으로
글자 단위 분리가 이뤄지게 한다.
"""
import json

import cv2
import numpy as np


# ── 기준 Gaussian 맵 (한 번만 생성, 재사용) ──────────────────────────────
_GAUSS_SIZE = 200

def _make_reference_gaussian(size: int = _GAUSS_SIZE) -> np.ndarray:
    sigma = size / 6.0
    x = np.arange(size) - size / 2.0
    gauss_1d = np.exp(-0.5 * (x / sigma) ** 2)
    gauss_2d = np.outer(gauss_1d, gauss_1d)
    return (gauss_2d / gauss_2d.max()).astype(np.float32)

_REF_GAUSS = _make_reference_gaussian(_GAUSS_SIZE)


def _place_gaussian(score_map: np.ndarray, pts4: np.ndarray) -> None:
    """
    score_map 위에 pts4(4×2, float32) 영역에 Gaussian을 warp해서 덮어씀.
    CRAFT 원논문 방식: 기준 Gaussian → perspectiveTransform → 합산(max).
    """
    g = _GAUSS_SIZE
    src = np.array([[0, 0], [g, 0], [g, g], [0, g]], dtype=np.float32)
    M   = cv2.getPerspectiveTransform(src, pts4.astype(np.float32))

    h, w = score_map.shape
    warped = cv2.warpPerspective(_REF_GAUSS, M, (w, h))
    np.maximum(score_map, warped, out=score_map)


def split_word_box(word_pts: np.ndarray, num_chars: int) -> list:
    """
    단어(어절) 4점 polygon(좌상,우상,우하,좌하 순서)을 글자 수만큼 가로로 등분해
    글자별 4점 polygon 리스트로 반환.

    상단 변(좌상→우상)과 하단 변(좌하→우하)을 각각 독립적으로 num_chars 등분한 뒤
    대응하는 분할점끼리 연결한다 — 사진 촬영으로 기울어지거나 회전된 단어 bbox에도
    올바르게 적용되도록 x좌표 단순 분할이 아닌 변(edge) 기준 분할을 사용.

    실제 글자 폭 차이(예: "ㅣ" vs "쓰")는 반영하지 못하는 근사치다 — AI Hub 라벨에
    글자별 정답 폭 정보가 없는 이상 현실적인 1차 근사.

    Parameters
    ----------
    word_pts : (4, 2) float32 — [좌상, 우상, 우하, 좌하]
    num_chars : 분할할 글자 수 (1 이상)

    Returns
    -------
    List[np.ndarray (4,2)] — 글자별 polygon, 왼쪽→오른쪽 순서
    """
    if num_chars <= 1:
        return [word_pts.astype(np.float32)]

    tl, tr, br, bl = word_pts.astype(np.float32)
    fractions = [i / num_chars for i in range(num_chars + 1)]
    top_pts    = [tl + (tr - tl) * f for f in fractions]
    bottom_pts = [bl + (br - bl) * f for f in fractions]

    return [
        np.array([top_pts[i], top_pts[i + 1], bottom_pts[i + 1], bottom_pts[i]], dtype=np.float32)
        for i in range(num_chars)
    ]


def generate_score_maps(
    image_h: int,
    image_w: int,
    char_boxes: list,               # List[np.ndarray (4,2)]  — 글자(음절) 단위 bbox
    output_ratio: float = 0.5,      # CRAFT score map = 원본의 1/2
) -> tuple:
    """
    Parameters
    ----------
    char_boxes : 글자 단위 4점 polygon 목록 (이미지 좌표) — parse_aihub_json() 참조

    Returns
    -------
    region_map  : (out_h, out_w) float32  0~1
    affinity_map: (out_h, out_w) float32  항상 0 (모듈 docstring 참조)
    """
    out_h = int(image_h * output_ratio)
    out_w = int(image_w * output_ratio)
    region_map   = np.zeros((out_h, out_w), dtype=np.float32)
    affinity_map = np.zeros((out_h, out_w), dtype=np.float32)

    for box in char_boxes:
        _place_gaussian(region_map, box * output_ratio)

    return region_map, affinity_map


def parse_aihub_json(json_path: str) -> list:
    """
    AI Hub 손글씨 OCR JSON (어절 단위 bbox) → 글자(음절) 단위 bbox 목록.

    실제 포맷:
    {
      "Images": { "identifier": "IMG_OCR_53_...", "width": ..., "height": ... },
      "bbox": [
        { "id": 1, "data": "안녕", "x": [x1,x2,x3,x4], "y": [y1,y2,y3,y4] },
        ...
      ]
    }

    x/y 배열 순서: [좌상, 좌하, 우상, 우하]
    → CRAFT polygon (시계방향 좌상 기준): [좌상, 우상, 우하, 좌하]

    각 bbox의 "data" 텍스트 길이만큼 split_word_box()로 글자 단위 분할한다
    (AI Hub 라벨은 어절 단위라 그대로 쓰면 글자가 아니라 단어 단위로 학습됨).

    Returns
    -------
    List[np.ndarray (4,2)] — 모든 어절의 글자 단위 polygon을 평탄화한 목록,
    이미지 좌표 (x, y) 순서, 시계방향
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    char_boxes = []

    for item in data.get('bbox', []):
        xs = item.get('x', [])
        ys = item.get('y', [])
        text = item.get('data', '')
        if len(xs) != 4 or len(ys) != 4 or not text:
            continue
        # x: [좌상x, 좌하x, 우상x, 우하x]
        # y: [좌상y, 좌하y, 우상y, 우하y]
        # → 시계방향: 좌상(0), 우상(2), 우하(3), 좌하(1)
        word_pts = np.array([
            [xs[0], ys[0]],   # 좌상
            [xs[2], ys[2]],   # 우상
            [xs[3], ys[3]],   # 우하
            [xs[1], ys[1]],   # 좌하
        ], dtype=np.float32)

        num_chars = len(text)
        char_boxes.extend(split_word_box(word_pts, num_chars))

    return char_boxes
