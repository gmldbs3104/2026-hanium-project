"""
SFR-004I: CRAFT Score Map + Morphology 하이브리드 글자 탐지

파이프라인
---------
1. CRAFT 추론 → score_text_raw (1/2 해상도 히트맵)
2. Hysteresis Thresholding
3. 방향성 Morphology Closing
4. score map 공간에서 Watershed → 글자 단위 분할
5. binary image의 CC를 watershed label에 배정 (투표)
   → CC 경계가 실제 잉크에 정확히 일치 → tight bbox 보장
6. 내부 박스 제거 후처리

반환: AI_MODEL_INTERFACE.md SFR-004I 스펙 준수
  char_id, bounding_box(x/y/width/height), angle, confidence
"""
import cv2
import numpy as np
from collections import defaultdict
from typing import List, Dict, Tuple

from craft_text_detector import Craft
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.segmentation import watershed


HIGH_THRESH:    float = 0.40
LOW_THRESH:     float = 0.20
MIN_AREA_RATIO: float = 0.08


class CraftDetector:
    """CRAFT score map + morphology + CC-assignment 하이브리드 탐지기."""

    def __init__(self, cuda: bool = False, long_size: int = 1280):
        self._craft = Craft(
            output_dir=None,
            rectify=True,
            export_extra=False,
            text_threshold=0.4,
            link_threshold=0.4,
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
        Parameters
        ----------
        binary_image : (H, W) uint8, 값 0(배경) or 255(획)
        """
        pred  = self._craft_prediction(binary_image)
        chars = self._hybrid_detect(pred, binary_image)
        chars = self._filter_noise(chars)
        chars = self._remove_contained(chars)
        chars = self._sort_reading_order(chars, binary_image.shape)
        print(f"    → {len(chars)} chars detected")
        return self._format_output(chars)

    def unload(self):
        del self._craft

    # ------------------------------------------------------------------ #
    # 핵심 파이프라인
    # ------------------------------------------------------------------ #

    def _craft_prediction(self, binary: np.ndarray) -> dict:
        rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
        return self._craft.detect_text(rgb)

    def _hybrid_detect(self, pred: dict, binary: np.ndarray) -> List[Dict]:
        score        = pred.get("score_text_raw")
        target_ratio = pred.get("target_ratio", 1.0)
        if score is None:
            return []

        scale        = 2.0 / target_ratio
        img_h, img_w = binary.shape[:2]

        # ── Step 1: Hysteresis Thresholding ───────────────────────────
        hyst = self._hysteresis_threshold(score)
        print(f"  [hyst]  pixels={int(hyst.sum())}")

        # ── HIGH blob 크기 통계 ────────────────────────────────────────
        high_u8 = (score >= HIGH_THRESH).astype(np.uint8)
        n_high, _, stats_h, _ = cv2.connectedComponentsWithStats(
            high_u8, connectivity=8)
        if n_high < 2:
            return []
        widths  = [stats_h[l, cv2.CC_STAT_WIDTH]  for l in range(1, n_high)]
        heights = [stats_h[l, cv2.CC_STAT_HEIGHT] for l in range(1, n_high)]
        med_w   = float(np.median(widths))
        med_h   = float(np.median(heights))
        print(f"  [blob]  n={n_high-1}  med_w={med_w:.1f}  med_h={med_h:.1f} (score map px)")

        # ── Step 2: 방향성 Morphology Closing ─────────────────────────
        closed = self._directional_close(hyst, med_w, med_h)

        # ── Step 3: score map 공간에서 Watershed ──────────────────────
        labels_score = self._watershed_segment(closed, score, med_w)
        print(f"  [wshed] {int(labels_score.max())} regions")

        # ── Step 4: binary CC를 watershed label에 배정 → tight bbox ───
        return self._extract_chars(labels_score, binary, score, scale, img_w, img_h)

    # ------------------------------------------------------------------ #
    # Step 1: Hysteresis Thresholding
    # ------------------------------------------------------------------ #

    def _hysteresis_threshold(self, score: np.ndarray) -> np.ndarray:
        high_mask = (score >= HIGH_THRESH).astype(np.uint8)
        low_mask  = (score >= LOW_THRESH).astype(np.uint8)
        n, labels, _, _ = cv2.connectedComponentsWithStats(low_mask, connectivity=8)
        result = np.zeros_like(low_mask)
        for lbl in range(1, n):
            if np.any((labels == lbl) & (high_mask > 0)):
                result[labels == lbl] = 1
        return result

    # ------------------------------------------------------------------ #
    # Step 2: 방향성 Morphology Closing
    # ------------------------------------------------------------------ #

    def _directional_close(
        self, hyst: np.ndarray, med_w: float, med_h: float
    ) -> np.ndarray:
        m8 = (hyst > 0).astype(np.uint8) * 255

        if med_w < 18:
            ch, cv_ = 0.50, 0.50
        elif med_w < 40:
            ch, cv_ = 0.28, 0.28
        else:
            ch, cv_ = 0.18, 0.18

        kw_h     = max(2, int(med_w * ch))
        kh_h     = max(1, int(med_h * (ch * 0.40)))
        ker_h    = cv2.getStructuringElement(cv2.MORPH_RECT, (kw_h, kh_h))
        closed_h = cv2.morphologyEx(m8, cv2.MORPH_CLOSE, ker_h)

        kw_v     = max(1, int(med_w * (cv_ * 0.40)))
        kh_v     = max(2, int(med_h * cv_))
        ker_v    = cv2.getStructuringElement(cv2.MORPH_RECT, (kw_v, kh_v))
        closed_v = cv2.morphologyEx(m8, cv2.MORPH_CLOSE, ker_v)

        combined = cv2.bitwise_or(closed_h, closed_v)
        print(f"  [close] ker_h=({kw_h},{kh_h}) ker_v=({kw_v},{kh_v})")
        return combined

    # ------------------------------------------------------------------ #
    # Step 3: score map 공간 Watershed
    # ------------------------------------------------------------------ #

    def _watershed_segment(
        self, mask: np.ndarray, score: np.ndarray, med_w: float
    ) -> np.ndarray:
        binary   = (mask > 0).astype(np.uint8)
        dist     = ndi.distance_transform_edt(binary)

        if med_w < 18:
            md_ratio = 0.90
        elif med_w < 40:
            md_ratio = 0.55
        else:
            md_ratio = 0.50
        min_dist  = max(8, int(med_w * md_ratio))

        local_max = peak_local_max(score, min_distance=min_dist, labels=binary)
        peak_mask = np.zeros(score.shape, dtype=bool)
        if len(local_max) > 0:
            peak_mask[local_max[:, 0], local_max[:, 1]] = True

        markers, _ = ndi.label(peak_mask)
        print(f"  [wshed] min_dist={min_dist}  peaks={int(peak_mask.sum())}")
        return watershed(-dist, markers, mask=binary)

    # ------------------------------------------------------------------ #
    # Step 4: binary CC → watershed label 배정 → tight bbox
    # ------------------------------------------------------------------ #

    def _extract_chars(
        self,
        labels_score: np.ndarray,
        binary: np.ndarray,
        score: np.ndarray,
        scale: float,
        img_w: int,
        img_h: int,
    ) -> List[Dict]:
        """
        binary image의 connected component를 score map watershed label에
        투표 방식으로 배정한다.

        - labels_score를 이미지 크기로 업스케일 → 각 잉크 픽셀의 watershed label 조회
        - 각 binary CC 안에서 가장 많은 watershed label이 그 CC의 글자
        - 같은 글자(wlbl)로 배정된 CC를 합쳐 tight bbox 계산

        이점: CC 경계 = 실제 잉크 경계 → bbox가 잉크에 tight하게 붙음
        """
        # watershed label을 이미지 크기로 업스케일 (1회만)
        labels_img = cv2.resize(
            labels_score.astype(np.int32),
            (img_w, img_h),
            interpolation=cv2.INTER_NEAREST,
        )

        # binary image의 CC 분석
        _, cc_labels, _, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

        # 잉크 픽셀에서 CC label과 watershed label을 동시에 추출
        ink_mask     = binary > 0
        ink_cc       = cc_labels[ink_mask]
        ink_wlbl     = labels_img[ink_mask]

        # watershed label이 있는 픽셀만 사용
        valid        = ink_wlbl > 0
        ink_cc       = ink_cc[valid]
        ink_wlbl     = ink_wlbl[valid]

        if len(ink_cc) == 0:
            return []

        # 각 CC에 대해 가장 많이 겹치는 watershed label을 찾음 (투표)
        n_wlbl = int(labels_score.max()) + 1
        pairs  = ink_cc.astype(np.int64) * n_wlbl + ink_wlbl.astype(np.int64)
        unique_pairs, counts = np.unique(pairs, return_counts=True)
        pair_cc   = (unique_pairs // n_wlbl).astype(np.int32)
        pair_wlbl = (unique_pairs %  n_wlbl).astype(np.int32)

        # CC → 최다득표 watershed label 매핑
        cc_to_wlbl: Dict[int, int] = {}
        for uc in np.unique(pair_cc):
            mask     = pair_cc == uc
            best_idx = np.argmax(counts[mask])
            cc_to_wlbl[int(uc)] = int(pair_wlbl[mask][best_idx])

        # watershed label → CC 목록으로 역인덱스
        wlbl_to_ccs: Dict[int, List[int]] = defaultdict(list)
        for cc, wlbl in cc_to_wlbl.items():
            wlbl_to_ccs[wlbl].append(cc)

        # 각 글자(wlbl)의 CC들을 합쳐 tight bbox 계산
        chars: List[Dict] = []
        score_h, score_w  = score.shape

        for wlbl, cc_list in wlbl_to_ccs.items():
            char_ink = np.isin(cc_labels, cc_list) & ink_mask

            if not np.any(char_ink):
                continue

            ink_ys, ink_xs = np.where(char_ink)
            tx = int(ink_xs.min())
            ty = int(ink_ys.min())
            tw = int(ink_xs.max() - ink_xs.min()) + 1
            th = int(ink_ys.max() - ink_ys.min()) + 1
            if tw < 4 or th < 4:
                continue

            # angle: 해당 글자 잉크 픽셀로만 계산
            pts_xy = np.column_stack([ink_xs, ink_ys]).astype(np.float32)
            angle  = 0.0
            if len(pts_xy) >= 5:
                rect  = cv2.minAreaRect(pts_xy)
                angle = float(rect[2])
                if angle < -45:
                    angle += 90

            # confidence: score map에서 해당 bbox 영역 평균
            sx0  = max(0,       int(tx / scale))
            sy0  = max(0,       int(ty / scale))
            sx1  = min(score_w, int((tx + tw) / scale) + 1)
            sy1  = min(score_h, int((ty + th) / scale) + 1)
            conf = float(np.mean(score[sy0:sy1, sx0:sx1])) \
                   if sy1 > sy0 and sx1 > sx0 else 0.0

            chars.append({
                "x": tx, "y": ty, "w": tw, "h": th,
                "angle": angle, "conf": conf,
            })

        return chars

    # ------------------------------------------------------------------ #
    # 유틸
    # ------------------------------------------------------------------ #

    def _filter_noise(self, chars: List[Dict]) -> List[Dict]:
        """median 면적의 MIN_AREA_RATIO 미만 blob 제거."""
        if len(chars) < 2:
            return chars
        areas  = [c["w"] * c["h"] for c in chars]
        med    = float(np.median(areas))
        before = len(chars)
        chars  = [c for c in chars if c["w"] * c["h"] >= med * MIN_AREA_RATIO]
        if before != len(chars):
            print(f"  [filter] {before - len(chars)}개 노이즈 제거 → {len(chars)}")
        return chars

    def _remove_contained(self, chars: List[Dict]) -> List[Dict]:
        """다른 bbox 안에 75% 이상 포함된 박스 제거 (글자 내부 박스 방지)."""
        if len(chars) < 2:
            return chars
        keep = []
        for i, c in enumerate(chars):
            contained = False
            for j, other in enumerate(chars):
                if i == j:
                    continue
                ix1 = max(c["x"], other["x"])
                iy1 = max(c["y"], other["y"])
                ix2 = min(c["x"] + c["w"], other["x"] + other["w"])
                iy2 = min(c["y"] + c["h"], other["y"] + other["h"])
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    area  = c["w"] * c["h"]
                    if inter / area > 0.75:
                        contained = True
                        break
            if not contained:
                keep.append(c)
        removed = len(chars) - len(keep)
        if removed:
            print(f"  [contain] {removed}개 내부 박스 제거 → {len(keep)}")
        return keep

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
        """AI_MODEL_INTERFACE.md SFR-004I 스펙 형식으로 변환."""
        return [
            {
                "char_id": f"char_{i}",
                "bounding_box": {
                    "x":      float(c["x"]),
                    "y":      float(c["y"]),
                    "width":  float(c["w"]),
                    "height": float(c["h"]),
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
