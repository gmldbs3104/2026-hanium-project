"""
AI Hub 손글씨 OCR 라벨 → CRAFT Ground Truth Score Map 변환

AI Hub JSON 포맷 (음절 단위 bbox) → region score map + affinity score map

Region Score  : 각 음절 중심에 Gaussian blob
Affinity Score: 인접 음절 쌍의 중간 지점에 Gaussian blob
"""
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


def generate_score_maps(
    image_h: int,
    image_w: int,
    syllable_boxes: list,           # List[np.ndarray (4,2)]  — 음절 bbox
    output_ratio: float = 0.5,      # CRAFT score map = 원본의 1/2
) -> tuple:
    """
    Parameters
    ----------
    syllable_boxes : 음절 단위 4점 polygon 목록 (이미지 좌표)

    Returns
    -------
    region_map : (out_h, out_w) float32  0~1
    affinity_map: (out_h, out_w) float32  0~1
    """
    out_h = int(image_h * output_ratio)
    out_w = int(image_w * output_ratio)
    region_map   = np.zeros((out_h, out_w), dtype=np.float32)
    affinity_map = np.zeros((out_h, out_w), dtype=np.float32)

    scaled = [box * output_ratio for box in syllable_boxes]

    # Region: 각 음절
    for box in scaled:
        _place_gaussian(region_map, box)

    # Affinity: 인접 음절 쌍의 중간 사각형
    for i in range(len(scaled) - 1):
        b1, b2    = scaled[i], scaled[i + 1]
        mid_top   = (b1[1] + b2[0]) / 2.0   # b1 우상단 ↔ b2 좌상단
        mid_bot   = (b1[2] + b2[3]) / 2.0   # b1 우하단 ↔ b2 좌하단
        affinity_box = np.array([
            (b1[0] + b1[1]) / 2.0,   # b1 상단 중점
            mid_top,
            mid_bot,
            (b1[3] + b1[2]) / 2.0,   # b1 하단 중점
        ], dtype=np.float32)
        _place_gaussian(affinity_map, affinity_box)

    return region_map, affinity_map


# ── AI Hub JSON 파싱 ─────────────────────────────────────────────────────
import json

def parse_aihub_json(json_path: str) -> list:
    """
    AI Hub 손글씨 OCR JSON (실제 포맷) → bbox polygon 목록

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

    Returns
    -------
    List[np.ndarray (4,2)]  — 이미지 좌표 (x, y) 순서, 시계방향
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    boxes = []

    for item in data.get('bbox', []):
        xs = item.get('x', [])
        ys = item.get('y', [])
        if len(xs) != 4 or len(ys) != 4:
            continue
        # x: [좌상x, 좌하x, 우상x, 우하x]
        # y: [좌상y, 좌하y, 우상y, 우하y]
        # → 시계방향: 좌상(0), 우상(2), 우하(3), 좌하(1)
        pts = np.array([
            [xs[0], ys[0]],   # 좌상
            [xs[2], ys[2]],   # 우상
            [xs[3], ys[3]],   # 우하
            [xs[1], ys[1]],   # 좌하
        ], dtype=np.float32)
        boxes.append(pts)

    return boxes
