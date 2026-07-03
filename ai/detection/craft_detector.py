"""
SFR-004I: CRAFT character score map 기반 글자 탐지

CRAFT 설계 원리
--------------
score_text : 각 픽셀이 어떤 글자(character)의 중심부일 확률.
             글자 하나당 하나의 Gaussian blob 형태로 나타남.
score_link : 인접 두 글자가 같은 단어일 확률 (여기서는 사용 안 함).

score_text 단독 사용 + threshold 이진화만으로 개별 글자 blob 분리 가능.
dilation 없음 — dilation을 넣으면 인접 글자 blob이 합쳐짐.

반환 메타데이터 (글자당)
-----------------------
char_id      : "char_0", "char_1", ...  (reading order)
bounding_box : x, y, width, height      (binary image 픽셀 기준 tight bbox)
center       : x, y                     (tight bbox 중심점)
angle        : float (도)               (minAreaRect 기반 기울기, -45~+45)
confidence   : float                    (해당 blob의 score_text 최댓값)
"""
import cv2
import numpy as np
from typing import List, Dict, Tuple

from craft_text_detector import Craft

# CRAFT score_text 이진화 임계값
# 손글씨는 인쇄체보다 score가 낮은 경향 → 0.4 사용
SCORE_THRESH: float = 0.40

# blob 면적 필터: median 면적의 이 비율 미만은 잡음 파편으로 제거
MIN_AREA_RATIO: float = 0.10
MIN_AREA_ABS: int = 6  # score map 픽셀 단위 절대 최솟값


class CraftDetector:
    """CRAFT score_text 기반 개별 글자 탐지기."""

    def __init__(self, cuda: bool = False, long_size: int = 1280):
        self._craft = Craft(
            output_dir=None,
            rectify=True,
            export_extra=False,
            text_threshold=0.4,
            link_threshold=0.5,
            low_text=0.3,
            cuda=cuda,
            long_size=long_size,
            refiner=False,
            crop_type="box",
        )

    # ------------------------------------------------------------------ #
    # 공개 API
    # ------------------------------------------------------------------ #

    def detect(self, binary_image: np.ndarray) -> List[Dict]:
        """
        전처리된 binary image에서 개별 글자를 탐지한다.

        Parameters
        ----------
        binary_image : (H, W) uint8
            ImagePreprocessor 출력 — THRESH_BINARY_INV (0=배경, 255=획)

        Returns
        -------
        List[Dict]  reading order 정렬 완료, char_id 부여 완료.
        각 항목:
          char_id      : str
          bounding_box : {"x", "y", "width", "height"}  — tight, 픽셀 단위
          center       : {"x", "y"}
          angle        : float  (도, -45 ~ +45)
          confidence   : float  (0 ~ 1)
        """
        pred = self._craft_prediction(binary_image)
        raw  = self._extract_chars(pred, binary_image)
        raw  = self._sort_reading_order(raw, binary_image.shape)

        chars = []
        for i, r in enumerate(raw):
            chars.append({
                "char_id": f"char_{i}",
                "bounding_box": {
                    "x":      float(r["x"]),
                    "y":      float(r["y"]),
                    "width":  float(r["w"]),
                    "height": float(r["h"]),
                },
                "center": {
                    "x": float(r["x"] + r["w"] / 2.0),
                    "y": float(r["y"] + r["h"] / 2.0),
                },
                "angle":      float(r["angle"]),
                "confidence": float(r["conf"]),
            })
        return chars

    def unload(self):
        del self._craft

    # ------------------------------------------------------------------ #
    # 내부 구현
    # ------------------------------------------------------------------ #

    def _craft_prediction(self, binary: np.ndarray) -> dict:
        """CRAFT 추론. predict.py 패치로 score_text_raw / target_ratio 포함."""
        rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
        return self._craft.detect_text(rgb)

    def _extract_chars(self, pred: dict, binary: np.ndarray) -> List[Dict]:
        """
        score_text_raw → threshold 이진화 → CC 추출 → tight bbox + 메타데이터.

        핵심: dilation 없음.
        CRAFT score_text는 이미 글자별 Gaussian blob이므로
        threshold만으로 개별 글자를 분리할 수 있다.
        """
        score_text   = pred.get("score_text_raw")
        target_ratio = pred.get("target_ratio", 1.0)
        if score_text is None:
            return []

        img_h, img_w = binary.shape[:2]
        # score map 해상도 → 원본 해상도 변환 비율
        scale = 2.0 / target_ratio

        # ── 1. threshold 이진화 ───────────────────────────────────────────
        mask = (score_text >= SCORE_THRESH).astype(np.uint8) * 255
        n_labels, _, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )

        # ── 2. 면적 필터 (잡음 파편 제거) ────────────────────────────────
        areas = [stats[lbl, cv2.CC_STAT_AREA] for lbl in range(1, n_labels)]
        if not areas:
            return []
        min_area = max(MIN_AREA_ABS, int(np.median(areas) * MIN_AREA_RATIO))
        print(f"  [CRAFT] blobs={len(areas)}  median_area={np.median(areas):.1f}"
              f"  min_area={min_area}  thresh={SCORE_THRESH}")

        result = []
        for lbl in range(1, n_labels):
            if stats[lbl, cv2.CC_STAT_AREA] < min_area:
                continue

            # score map 좌표
            sx = stats[lbl, cv2.CC_STAT_LEFT]
            sy = stats[lbl, cv2.CC_STAT_TOP]
            sw = stats[lbl, cv2.CC_STAT_WIDTH]
            sh = stats[lbl, cv2.CC_STAT_HEIGHT]

            # ── 3. score 좌표 → 원본 이미지 좌표 ────────────────────────
            x0 = max(0, int(sx * scale))
            y0 = max(0, int(sy * scale))
            x1 = min(img_w, int((sx + sw) * scale))
            y1 = min(img_h, int((sy + sh) * scale))
            if x1 <= x0 or y1 <= y0:
                continue

            # ── 4. binary image에서 실제 잉크 픽셀 tight bbox ────────────
            seg = binary[y0:y1, x0:x1]
            if not np.any(seg > 0):
                continue
            ys = np.where(np.any(seg > 0, axis=1))[0]
            xs = np.where(np.any(seg > 0, axis=0))[0]
            if not len(ys) or not len(xs):
                continue

            tx = x0 + int(xs[0])
            ty = y0 + int(ys[0])
            tw = int(xs[-1] - xs[0]) + 1
            th = int(ys[-1] - ys[0]) + 1

            # ── 5. 회전각 계산 (minAreaRect on ink pixels) ───────────────
            angle = self._calc_angle(binary, tx, ty, tw, th)

            # ── 6. confidence = 해당 score blob의 최댓값 ─────────────────
            score_crop = score_text[sy:sy + sh, sx:sx + sw]
            conf = float(score_crop.max()) if score_crop.size > 0 else 0.0

            result.append({
                "x": tx, "y": ty, "w": tw, "h": th,
                "angle": angle,
                "conf":  conf,
            })

        return result

    def _calc_angle(
        self, binary: np.ndarray,
        x: int, y: int, w: int, h: int
    ) -> float:
        """
        글자 영역 잉크 픽셀의 minAreaRect로 기울기 계산.
        반환값: -45 ~ +45 도 (수평=0, 시계방향=양수)
        """
        seg = binary[y:y + h, x:x + w]
        pts = np.column_stack(np.where(seg > 0))  # (row, col)
        if len(pts) < 5:
            return 0.0
        # cv2는 (x, y) 순서
        pts_xy = pts[:, ::-1].astype(np.float32)
        rect   = cv2.minAreaRect(pts_xy)
        angle  = float(rect[2])
        # minAreaRect 각도 정규화: -90~0 → -45~+45
        if angle < -45:
            angle += 90
        return angle

    def _sort_reading_order(
        self, chars: List[Dict], img_shape: Tuple[int, int]
    ) -> List[Dict]:
        """
        읽기 순서 정렬: 위→아래(행), 같은 행 내 왼쪽→오른쪽.
        행 판정: 두 글자 중심 y 차이가 작은 쪽 높이의 60% 이내면 같은 행.
        """
        if not chars:
            return chars

        # 중심 y 기준 정렬 후 행 그룹화
        sorted_c = sorted(chars, key=lambda c: c["y"] + c["h"] / 2.0)
        rows: List[List[Dict]] = []

        for c in sorted_c:
            cy = c["y"] + c["h"] / 2.0
            placed = False
            for row in rows:
                row_cy = np.mean([r["y"] + r["h"] / 2.0 for r in row])
                row_h  = np.mean([r["h"] for r in row])
                if abs(cy - row_cy) < row_h * 0.6:
                    row.append(c)
                    placed = True
                    break
            if not placed:
                rows.append([c])

        result = []
        for row in rows:
            result.extend(sorted(row, key=lambda c: c["x"]))
        return result


# ------------------------------------------------------------------ #
# SFR-004I 인터페이스 함수 (백엔드 연동용)
# ------------------------------------------------------------------ #

def craft_detect_chars(
    binary_image_list: List[List[int]],
    image_width: int,
    image_height: int,
    cuda: bool = False,
) -> List[Dict]:
    """
    AI_MODEL_INTERFACE.md SFR-004I 규격 함수.

    Parameters
    ----------
    binary_image_list : 2D list (rows × cols), 값 0 또는 255
    image_width       : 이미지 너비 (px)
    image_height      : 이미지 높이 (px)

    Returns
    -------
    List[Dict]  char_id / bounding_box / center / angle / confidence
    """
    image = np.array(binary_image_list, dtype=np.uint8)
    if image.shape != (image_height, image_width):
        image = cv2.resize(
            image, (image_width, image_height), interpolation=cv2.INTER_NEAREST
        )
    detector = CraftDetector(cuda=cuda)
    result   = detector.detect(image)
    detector.unload()
    return result
