"""
SFR-004I: CRAFT 기본 출력 기반 글자 탐지

파이프라인
---------
1. CRAFT 추론 → boxes (4점 다각형), score_text_raw
2. 각 박스 내 binary image 잉크 픽셀로 tight bbox 재계산
3. 잉크 픽셀로 angle 계산 (cv2.minAreaRect)
4. score map 평균으로 confidence 계산
5. 읽기 순서 정렬

반환: AI_MODEL_INTERFACE.md SFR-004I 스펙 준수
  char_id, bounding_box(x/y/width/height), angle, confidence
"""
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional

from craft_text_detector import Craft


class CraftDetector:

    def __init__(
        self,
        cuda: bool = False,
        long_size: int = 1280,
        text_threshold: float = 0.7,
        link_threshold: float = 0.4,
        low_text: float = 0.4,
        use_dist_transform: bool = True,
    ):
        self._craft = Craft(
            output_dir=None,
            rectify=True,
            export_extra=False,
            text_threshold=text_threshold,
            link_threshold=link_threshold,
            low_text=low_text,
            cuda=cuda,
            long_size=long_size,
            refiner=False,
            crop_type="box",
        )
        self._use_dist = use_dist_transform

    # ------------------------------------------------------------------ #
    # 공개 API
    # ------------------------------------------------------------------ #

    def detect(self, binary_image: np.ndarray) -> List[Dict]:
        """
        Parameters
        ----------
        binary_image : (H, W) uint8, 값 0(배경) or 255(획)
        """
        pred  = self._craft_prediction(binary_image)
        chars = self._process_boxes(pred, binary_image)
        chars = self._sort_reading_order(chars, binary_image.shape)
        print(f"    → {len(chars)} chars detected")
        return self._format_output(chars)

    def unload(self):
        del self._craft

    # ------------------------------------------------------------------ #
    # 핵심 파이프라인
    # ------------------------------------------------------------------ #

    def _craft_prediction(self, binary: np.ndarray) -> dict:
        """
        binary → CRAFT 추론.

        use_dist_transform=True (기본):
          Distance Transform으로 잉크 영역에 그레디언트를 복원.
          CRAFT가 텍스처/그레디언트를 기반으로 학습됐으므로 순수 binary보다
          탐지율이 높아짐.
        """
        if self._use_dist:
            dist      = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
            dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            rgb = cv2.cvtColor(dist_norm, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
        return self._craft.detect_text(rgb)

    def _process_boxes(self, pred: dict, binary: np.ndarray) -> List[Dict]:
        """CRAFT boxes → tight bbox + angle + confidence."""
        boxes        = pred.get("boxes", [])
        score        = pred.get("score_text_raw")
        target_ratio = pred.get("target_ratio", 1.0)
        scale        = 2.0 / target_ratio

        score_h = score.shape[0] if score is not None else 1
        score_w = score.shape[1] if score is not None else 1

        print(f"  [craft] {len(boxes)} boxes")

        chars: List[Dict] = []
        for box in boxes:
            pts = np.array(box, dtype=np.float32)  # (4, 2) — [[x,y], ...]

            # CRAFT 박스 내 잉크 픽셀로 tight bbox 재계산
            result = self._tighten_box(pts, binary)
            if result is None:
                continue
            tx, ty, tw, th, ink_pts_xy = result

            # angle: 잉크 픽셀 minAreaRect
            angle = 0.0
            if len(ink_pts_xy) >= 5:
                rect  = cv2.minAreaRect(ink_pts_xy)
                angle = float(rect[2])
                if angle < -45:
                    angle += 90

            # confidence: score map 해당 영역 평균
            if score is not None:
                sx0  = max(0,       int(tx / scale))
                sy0  = max(0,       int(ty / scale))
                sx1  = min(score_w, int((tx + tw) / scale) + 1)
                sy1  = min(score_h, int((ty + th) / scale) + 1)
                conf = float(np.mean(score[sy0:sy1, sx0:sx1])) \
                       if sy1 > sy0 and sx1 > sx0 else 0.0
            else:
                conf = 0.5

            chars.append({
                "x": float(tx), "y": float(ty),
                "w": float(tw), "h": float(th),
                "angle": angle, "conf": conf,
            })

        return chars

    # ------------------------------------------------------------------ #
    # 유틸
    # ------------------------------------------------------------------ #

    def _tighten_box(
        self, pts: np.ndarray, binary: np.ndarray
    ) -> Optional[Tuple[int, int, int, int, np.ndarray]]:
        """
        CRAFT 4점 박스 내 실제 잉크 픽셀을 추출해 tight bbox 재계산.

        Returns
        -------
        (tx, ty, tw, th, ink_pts_xy) or None
          ink_pts_xy : (N, 2) float32, 이미지 좌표 (x, y)
        """
        img_h, img_w = binary.shape[:2]
        x0 = max(0,     int(pts[:, 0].min()))
        y0 = max(0,     int(pts[:, 1].min()))
        x1 = min(img_w, int(pts[:, 0].max()) + 1)
        y1 = min(img_h, int(pts[:, 1].max()) + 1)

        if x1 <= x0 or y1 <= y0:
            return None

        roi = binary[y0:y1, x0:x1]
        if not np.any(roi > 0):
            return None

        # 다각형 마스크 (회전된 박스에서 외부 잉크 제외)
        poly_mask = np.zeros(roi.shape, dtype=np.uint8)
        shifted   = pts - np.array([x0, y0], dtype=np.float32)
        cv2.fillPoly(poly_mask, [shifted.astype(np.int32)], 255)

        ink = (roi > 0) & (poly_mask > 0)
        if not np.any(ink):
            ink = roi > 0  # 폴백: 박스 내 전체 잉크

        iy, ix = np.where(ink)
        if len(iy) == 0:
            return None

        tx = x0 + int(ix.min())
        ty = y0 + int(iy.min())
        tw = int(ix.max() - ix.min()) + 1
        th = int(iy.max() - iy.min()) + 1
        if tw < 4 or th < 4:
            return None

        ink_pts_xy = np.column_stack(
            [ix.astype(np.float32) + x0, iy.astype(np.float32) + y0]
        )
        return tx, ty, tw, th, ink_pts_xy

    def _sort_reading_order(
        self, chars: List[Dict], img_shape: Tuple[int, int]
    ) -> List[Dict]:
        """위→아래(행), 같은 행 내 왼쪽→오른쪽."""
        if not chars:
            return chars
        sorted_c = sorted(chars, key=lambda c: c["y"] + c["h"] / 2.0)
        rows: List[List[Dict]] = []
        for c in sorted_c:
            cy     = c["y"] + c["h"] / 2.0
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

    def _format_output(self, chars: List[Dict]) -> List[Dict]:
        """AI_MODEL_INTERFACE.md SFR-004I 스펙 형식."""
        return [
            {
                "char_id": f"char_{i}",
                "bounding_box": {
                    "x":      c["x"],
                    "y":      c["y"],
                    "width":  c["w"],
                    "height": c["h"],
                },
                "angle":      float(c["angle"]),
                "confidence": float(c["conf"]),
            }
            for i, c in enumerate(chars)
        ]


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
    """
    image = np.array(binary_image_list, dtype=np.uint8)
    if image.shape != (image_height, image_width):
        image = cv2.resize(
            image, (image_width, image_height),
            interpolation=cv2.INTER_NEAREST,
        )
    detector = CraftDetector(cuda=cuda)
    result   = detector.detect(image)
    detector.unload()
    return result
