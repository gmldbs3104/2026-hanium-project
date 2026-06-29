import numpy as np
from typing import List, Dict


def sort_reading_order(chars: List[Dict]) -> List[Dict]:
    """Reading order: top-to-bottom rows, left-to-right within each row."""
    if len(chars) <= 1:
        return chars

    def cy(c):
        b = c["bounding_box"]
        return b["y"] + b["height"] / 2.0

    def cx(c):
        b = c["bounding_box"]
        return b["x"] + b["width"] / 2.0

    sorted_by_y = sorted(chars, key=cy)
    avg_h = np.mean([c["bounding_box"]["height"] for c in chars])
    row_gap = avg_h * 0.6

    rows: List[List[Dict]] = []
    for char in sorted_by_y:
        char_cy = cy(char)
        placed = False
        for row in rows:
            row_cy = np.mean([cy(r) for r in row])
            if abs(char_cy - row_cy) < row_gap:
                row.append(char)
                placed = True
                break
        if not placed:
            rows.append([char])

    result = []
    for row in rows:
        result.extend(sorted(row, key=cx))
    return result


def calc_box_angle(corners: np.ndarray) -> float:
    """
    Rotation angle (degrees, clockwise positive) from a quad's top edge.
    corners: (4, 2) array TL→TR→BR→BL from cv2.boxPoints order.
    """
    if corners is None or len(corners) < 2:
        return 0.0
    tl = corners[0].astype(float)
    tr = corners[1].astype(float)
    return float(np.degrees(np.arctan2(tr[1] - tl[1], tr[0] - tl[0])))


def group_components_into_chars(
    components: List[Dict],
    gap_ratio: float = 0.5,
    max_gap: int = None,
) -> List[Dict]:
    """
    Merge nearby CCA components into single character bounding boxes.

    threshold = min(comp.w, group_max_w) × gap_ratio
    max_gap가 주어지면 threshold의 절대 픽셀 상한으로 사용한다.
    이를 통해 글자 크기가 커도 글자 간 간격에서 잘못 병합되는 것을 방지한다.

    Parameters
    ----------
    components : list of dicts with keys x, y, w, h
    gap_ratio  : threshold = min(comp.w, group_max_w) × gap_ratio
    max_gap    : threshold의 절대 픽셀 상한 (행 높이의 10~15% 권장)

    Returns
    -------
    list of merged bounding box dicts (x, y, w, h)
    """
    if not components:
        return []

    comps = sorted(components, key=lambda c: c["x"])

    groups: List[List[Dict]] = []
    for comp in comps:
        cx0 = comp["x"]
        placed = False
        for group in groups:
            gx1 = max(c["x"] + c["w"] for c in group)
            gw  = max(c["w"] for c in group)
            threshold = min(gw, comp["w"]) * gap_ratio
            if max_gap is not None:
                threshold = min(threshold, max_gap)
            if cx0 - gx1 < threshold:
                group.append(comp)
                placed = True
                break
        if not placed:
            groups.append([comp])

    result = []
    for group in groups:
        x0 = min(c["x"] for c in group)
        y0 = min(c["y"] for c in group)
        x1 = max(c["x"] + c["w"] for c in group)
        y1 = max(c["y"] + c["h"] for c in group)
        result.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})

    return result
