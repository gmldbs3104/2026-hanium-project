"""
SFR-004I: CRAFT + Column Projection 글자 단위 탐지

Pipeline:
  1. CRAFT  → 텍스트 행(row) 영역 박스 탐지
  2. Merge  → y overlap 기준으로 같은 행 박스 병합
  3. ColProj → 열별 잉크 프로파일에서 글자 경계(valley) 탐지
  4. BBox   → 각 글자 구간 내 실제 잉크 bounding box 정밀화
  5. Sort   → reading order 정렬 + char_id 부여
"""
import cv2
import numpy as np
from typing import List, Dict

from craft_text_detector import Craft

from .bbox_utils import sort_reading_order, calc_box_angle, group_components_into_chars

CONFIDENCE_THRESHOLD = 0.5
ROW_PAD_RATIO = 0.15


class CraftDetector:
    """
    CRAFT 행 탐지 + Column Projection 글자 분리 결합 탐지기.
    """

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
        Parameters
        ----------
        binary_image : (H, W) uint8
            ImagePreprocessor 출력 — THRESH_BINARY_INV (0=배경, 255=획)

        Returns
        -------
        List[Dict]  reading order 정렬, char_id 재부여 완료
        """
        img_h, img_w = binary_image.shape[:2]

        # Step 1: CRAFT로 행 단위 텍스트 박스 탐지
        row_boxes = self._craft_row_boxes(binary_image)
        if not row_boxes:
            return []

        # Step 2: y 범위가 겹치는 박스를 같은 행으로 병합
        merged_rows = self._merge_overlapping_rows(row_boxes, img_w, img_h)

        # Step 3: 각 행 안에서 column projection으로 글자 분리
        # CRAFT가 여러 줄을 하나의 단락 박스로 묶은 경우 수평 프로파일로 먼저 행 분리
        chars: List[Dict] = []
        for rx0, ry0, rx1, ry1 in merged_rows:
            sub_rows = self._split_para_into_rows(binary_image, ry0, ry1, rx0, rx1)

            for sub_ry0, sub_ry1 in sub_rows:
                row_h = sub_ry1 - sub_ry0
                pad = int(row_h * ROW_PAD_RATIO)
                ry0p = max(0, sub_ry0 - pad)
                ry1p = min(img_h, sub_ry1 + pad)
                rx0p = max(0, rx0 - pad)
                rx1p = min(img_w, rx1 + pad)

                char_boxes = self._segment_chars_in_row(
                    binary_image, ry0p, ry1p, rx0p, rx1p
                )
                for cb in char_boxes:
                    chars.append({
                        "char_id": f"char_{len(chars)}",
                        "bounding_box": {
                            "x":      float(cb["x"]),
                            "y":      float(cb["y"]),
                            "width":  float(cb["w"]),
                            "height": float(cb["h"]),
                        },
                        "angle":      0.0,
                        "confidence": 1.0,
                    })

        # Step 4: reading order 정렬 + char_id 재부여
        chars = sort_reading_order(chars)
        for i, c in enumerate(chars):
            c["char_id"] = f"char_{i}"

        # Step 5: 노이즈 필터 — 중앙값 대비 너무 작은 박스 제거
        if len(chars) > 2:
            median_h = float(np.median([c["bounding_box"]["height"] for c in chars]))
            median_w = float(np.median([c["bounding_box"]["width"]  for c in chars]))
            chars = [c for c in chars if
                     c["bounding_box"]["height"] >= median_h * 0.25 and
                     c["bounding_box"]["width"]  >= median_w * 0.15]
            for i, c in enumerate(chars):
                c["char_id"] = f"char_{i}"

        return chars

    def unload(self):
        del self._craft

    # ------------------------------------------------------------------ #
    # 내부 구현
    # ------------------------------------------------------------------ #

    def _merge_overlapping_rows(
        self, row_boxes: list, img_w: int, img_h: int
    ) -> List[tuple]:
        """
        y 범위가 겹치는 CRAFT 박스를 같은 행으로 병합.
        """
        rects = []
        for box in row_boxes:
            b = np.array(box, dtype=np.float32)
            x0 = int(np.clip(b[:, 0].min(), 0, img_w))
            x1 = int(np.clip(b[:, 0].max(), 0, img_w))
            y0 = int(np.clip(b[:, 1].min(), 0, img_h))
            y1 = int(np.clip(b[:, 1].max(), 0, img_h))
            rects.append([x0, y0, x1, y1])

        rects.sort(key=lambda r: (r[1] + r[3]) / 2)

        groups: List[List[int]] = []
        for x0, y0, x1, y1 in rects:
            merged = False
            for g in groups:
                if y0 <= g[3] and y1 >= g[1]:
                    g[0] = min(g[0], x0)
                    g[1] = min(g[1], y0)
                    g[2] = max(g[2], x1)
                    g[3] = max(g[3], y1)
                    merged = True
                    break
            if not merged:
                groups.append([x0, y0, x1, y1])

        return [(g[0], g[1], g[2], g[3]) for g in groups]

    def _craft_row_boxes(self, binary: np.ndarray) -> list:
        """CRAFT 순방향 → 행 단위 박스 리스트 반환."""
        rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
        pred = self._craft.detect_text(rgb)
        return pred.get("boxes", [])

    def _split_para_into_rows(
        self,
        binary: np.ndarray,
        ry0: int, ry1: int,
        rx0: int, rx1: int,
    ) -> List[tuple]:
        """
        CRAFT 박스(단락) 안에서 수평 잉크 프로파일로 텍스트 행을 분리.

        절대 valley(잉크 2% 미만인 픽셀 행) 기준으로만 분리.
        행 간 공백이 없는 빽빽한 손글씨나 단일 행 박스는 분리하지 않는다.
        """
        crop = binary[ry0:ry1, rx0:rx1]
        if crop.size == 0:
            return [(ry0, ry1)]

        para_h = ry1 - ry0

        # 수평 잉크 프로파일
        row_proj = np.sum(crop.astype(np.float32), axis=1)
        if row_proj.max() == 0:
            return [(ry0, ry1)]

        # 정규화 + 11px 스무싱
        k = 11
        row_proj_s = np.convolve(row_proj / row_proj.max(), np.ones(k) / k, mode='same')

        # 절대 valley: 잉크가 2% 미만인 픽셀 행 (실제 행 간 공백)
        in_text = row_proj_s > 0.02

        spans: List[List[int]] = []
        start = None
        for i, v in enumerate(in_text):
            if v and start is None:
                start = i
            elif not v and start is not None:
                spans.append([start, i])
                start = None
        if start is not None:
            spans.append([start, para_h])

        if len(spans) <= 1:
            return [(ry0, ry1)]

        # 너무 좁은 gap 병합 (단락 높이의 3% 미만은 글자 내부로 처리)
        min_gap = max(int(para_h * 0.03), 3)
        merged: List[List[int]] = [spans[0][:]]
        for s in spans[1:]:
            if s[0] - merged[-1][1] <= min_gap:
                merged[-1][1] = s[1]
            else:
                merged.append(s[:])

        if len(merged) <= 1:
            return [(ry0, ry1)]

        # 최소 행 높이 20px
        valid = [s for s in merged if (s[1] - s[0]) >= 20]
        return [(ry0 + s[0], ry0 + s[1]) for s in valid] if len(valid) > 1 else [(ry0, ry1)]

    def _segment_chars_in_row(
        self,
        binary: np.ndarray,
        ry0: int, ry1: int,
        rx0: int, rx1: int,
    ) -> List[Dict]:
        """
        Column projection → bbox 정밀화 2단계 글자 분리.

        1. 열별 잉크 합계 프로파일에서 valley(빈 열)를 글자 경계로 탐지
        2. 각 글자 구간 내 실제 잉크 bounding box 계산 (y 방향 trim 포함)

        손글씨/폰트 공통으로 글자 사이 빈 열이 valley로 나타나므로
        CCA gap 병합보다 안정적이다.
        """
        crop = binary[ry0:ry1, rx0:rx1]
        if crop.size == 0:
            return []

        row_h = ry1 - ry0
        if crop.shape[1] < 4 or row_h < 4:
            return []

        # 노이즈 제거
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        clean = cv2.morphologyEx(crop, cv2.MORPH_OPEN, open_k)

        # Step 1: column projection으로 글자 span 탐지
        spans = self._col_projection_spans(clean, row_h)
        if not spans:
            return []

        # Step 2: 각 span 내 실제 잉크 bounding box 계산
        # MORPH_OPEN은 스팬 탐지 전용 — bbox는 원본 crop 기준으로 계산해
        # 획 끝 얇은 부분(1-2px)이 MORPH_OPEN에 의해 제거되어 bbox가 짧아지는 문제 방지
        result = []
        for sx0, sx1 in spans:
            seg = crop[:, sx0:sx1]   # 원본 crop 사용
            if not np.any(seg > 0):
                continue

            # 잡음 CC 제거: 최대 CC 면적 10% 미만 제거
            # 획과 연결된 끝 픽셀은 동일 CC → 유지 / 고립된 잡음 점 → 제거
            n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
                seg, connectivity=8
            )
            if n_labels > 1:
                max_area = int(stats[1:, cv2.CC_STAT_AREA].max())
                min_area = max(int(max_area * 0.10), 6)
                clean_seg = np.zeros_like(seg)
                for lbl in range(1, n_labels):
                    if stats[lbl, cv2.CC_STAT_AREA] >= min_area:
                        clean_seg[labels == lbl] = 255
                seg = clean_seg

            ink_rows = np.any(seg > 0, axis=1)
            ink_cols = np.any(seg > 0, axis=0)
            if not np.any(ink_rows) or not np.any(ink_cols):
                continue
            ys = np.where(ink_rows)[0]
            xs = np.where(ink_cols)[0]

            # 스팬 경계(sx1) 바깥으로 획이 잘렸을 경우 우측 보정
            # crop이 행 끝에서 끊기면 sx1 == crop.shape[1]가 되어
            # crop 기반 검사가 스킵됨 → binary 원본에서 직접 확인
            RIGHT_EXT = 25
            abs_sx1 = rx0 + sx1
            abs_right_end = min(abs_sx1 + RIGHT_EXT, binary.shape[1])
            extend_w = 0
            if abs_right_end > abs_sx1:
                ext = binary[ry0:ry1, abs_sx1:abs_right_end]
                if np.any(ext > 0):
                    ext_cols = np.any(ext > 0, axis=0)
                    extend_w = int(np.where(ext_cols)[0][-1]) + 1

            result.append({
                "x": rx0 + sx0 + int(xs[0]),
                "y": ry0 + int(ys[0]),
                "w": int(xs[-1]) - int(xs[0]) + 1 + extend_w,
                "h": int(ys[-1]) - int(ys[0]) + 1,
            })

        return result

    def _col_projection_spans(
        self, clean: np.ndarray, row_h: int
    ) -> List[tuple]:
        """
        열별 잉크 합계 프로파일에서 글자 구간 리스트 반환.

        smoothing kernel = row_h * 10% → 자소 내부 작은 공백 무시
        valley_thresh = 8%            → 글자 사이 빈 구간 탐지
        min_gap = row_h * 8%          → 너무 좁은 gap은 같은 글자로 병합
        """
        proj = np.sum(clean.astype(np.float32), axis=0)
        if proj.max() == 0:
            return []

        # smoothing: 3px 이하 자소 내 미세 공백만 채움 (글자 간 gap은 유지)
        k = 3
        kernel = np.ones(k, np.float32) / k
        proj_s = np.convolve(proj, kernel, mode='same')
        proj_n = proj_s / proj_s.max()

        # valley: 잉크가 거의 없는 열 (1% 미만)
        in_char = proj_n > 0.01

        spans = []
        start = None
        for i, v in enumerate(in_char):
            if v and start is None:
                start = i
            elif not v and start is not None:
                spans.append([start, i])
                start = None
        if start is not None:
            spans.append([start, len(in_char)])

        if not spans:
            return []

        # Step 1: 2px 이하 gap 병합
        min_gap = 2
        merged = [spans[0][:]]
        for s in spans[1:]:
            if s[0] - merged[-1][1] <= min_gap:
                merged[-1][1] = s[1]
            else:
                merged.append(s[:])

        # Step 2: 너무 좁은 span → 인접 span에 병합 (6px짜리 가짜 ㅣ 조각 제거)
        min_char_w = max(int(row_h * 0.20), 8)
        # 순방향: 좁은 span → 이전 span에 병합
        tmp: List[List[int]] = []
        for s in merged:
            if (s[1] - s[0]) < min_char_w and tmp:
                tmp[-1][1] = s[1]
            else:
                tmp.append(s[:])
        # 역방향: 맨 앞 좁은 span → 다음 span에 병합
        fixed: List[List[int]] = []
        i = 0
        while i < len(tmp):
            s = tmp[i]
            if (s[1] - s[0]) < min_char_w and i + 1 < len(tmp):
                fixed.append([s[0], tmp[i + 1][1]])
                i += 2
            else:
                fixed.append(s[:])
                i += 1

        # Step 3: 너무 넓은 span → 내부 최솟값으로 재분할 (합쳐진 두 글자 분리)
        max_char_w = row_h * 0.90
        final: List[List[int]] = []
        for s in fixed:
            if (s[1] - s[0]) > max_char_w:
                sub = self._split_wide_span(proj_s, float(proj_s.max()), s[0], s[1], max_char_w)
                final.extend(sub)
            else:
                final.append(s)

        return [(s[0], s[1]) for s in final]

    def _split_wide_span(
        self,
        proj_s: np.ndarray,
        proj_max: float,
        sx0: int,
        sx1: int,
        max_char_w: float,
    ) -> List[List[int]]:
        """너무 넓은 span을 내부 최솟값 위치에서 재귀 분할."""
        w = sx1 - sx0
        margin = max(w // 6, 4)
        search_s = sx0 + margin
        search_e = sx1 - margin
        if search_e <= search_s:
            return [[sx0, sx1]]

        min_idx  = int(np.argmin(proj_s[search_s:search_e]))
        split_at = search_s + min_idx

        if proj_s[split_at] < proj_max * 0.85:
            result: List[List[int]] = []
            for seg in ([sx0, split_at], [split_at, sx1]):
                if seg[1] - seg[0] > max_char_w:
                    result.extend(self._split_wide_span(proj_s, proj_max, seg[0], seg[1], max_char_w))
                else:
                    result.append(seg)
            return result

        return [[sx0, sx1]]

    @staticmethod
    def _row_angle(box: np.ndarray) -> float:
        return calc_box_angle(box)


# ------------------------------------------------------------------ #
# SFR-004I 인터페이스 함수
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
    binary_image_list : 2D list (rows × cols), values 0 or 255
    image_width       : 이미지 너비 (px)
    image_height      : 이미지 높이 (px)

    Returns
    -------
    List[Dict]  char_id / bounding_box / angle / confidence
    """
    image = np.array(binary_image_list, dtype=np.uint8)
    if image.shape != (image_height, image_width):
        image = cv2.resize(
            image, (image_width, image_height), interpolation=cv2.INTER_NEAREST
        )
    detector = CraftDetector(cuda=cuda)
    return detector.detect(image)
