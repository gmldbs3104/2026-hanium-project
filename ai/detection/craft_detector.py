"""
SFR-004I: CRAFT 글자 탐지

방식 A (score_map, 기본): CRAFT character score map → dilation → CC → 글자 bbox
방식 B (row_col): CRAFT 행 박스 → _split_para_into_rows → column projection
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

    def detect(self, binary_image: np.ndarray, method: str = "score_map") -> List[Dict]:
        """
        Parameters
        ----------
        binary_image : (H, W) uint8  — THRESH_BINARY_INV (0=배경, 255=획)
        method       : "score_map" (기본) | "row_col" (기존 행→컬럼 방식)

        Returns
        -------
        List[Dict]  reading order 정렬, char_id 재부여 완료
        """
        img_h, img_w = binary_image.shape[:2]
        pred = self._craft_raw_prediction(binary_image)

        if method == "score_map":
            raw_boxes = self._chars_from_score_map(pred, binary_image)
            chars: List[Dict] = []
            for b in raw_boxes:
                chars.append({
                    "char_id": f"char_{len(chars)}",
                    "bounding_box": {
                        "x":      float(b["x"]),
                        "y":      float(b["y"]),
                        "width":  float(b["w"]),
                        "height": float(b["h"]),
                    },
                    "angle":      0.0,
                    "confidence": 1.0,
                })
        else:
            # 기존 행 → 컬럼 방식
            row_boxes = pred.get("boxes", [])
            if not row_boxes:
                return []
            merged_rows = self._merge_overlapping_rows(row_boxes, img_w, img_h)
            chars = []
            for rx0, ry0, rx1, ry1 in merged_rows:
                sub_rows = self._split_para_into_rows(binary_image, ry0, ry1, rx0, rx1)
                for sub_ry0, sub_ry1 in sub_rows:
                    row_h = sub_ry1 - sub_ry0
                    pad = int(row_h * ROW_PAD_RATIO)
                    ry0p = max(0, sub_ry0 - pad)
                    ry1p = min(img_h, sub_ry1 + pad)
                    rx0p = max(0, rx0 - pad)
                    rx1p = min(img_w, rx1 + pad)
                    char_boxes = self._segment_chars_in_row(binary_image, ry0p, ry1p, rx0p, rx1p)
                    for cb in char_boxes:
                        chars.append({
                            "char_id": f"char_{len(chars)}",
                            "bounding_box": {
                                "x": float(cb["x"]), "y": float(cb["y"]),
                                "width": float(cb["w"]), "height": float(cb["h"]),
                            },
                            "angle": 0.0, "confidence": 1.0,
                        })

        # 공통 후처리
        chars = sort_reading_order(chars)
        for i, c in enumerate(chars):
            c["char_id"] = f"char_{i}"

        if len(chars) > 2:
            median_h = float(np.median([c["bounding_box"]["height"] for c in chars]))
            median_w = float(np.median([c["bounding_box"]["width"]  for c in chars]))
            chars = [c for c in chars if
                     c["bounding_box"]["height"] >= median_h * 0.50 and
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

    def _craft_raw_prediction(self, binary: np.ndarray) -> dict:
        """CRAFT 순방향 → 전체 prediction dict 반환."""
        rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
        return self._craft.detect_text(rgb)

    def _craft_row_boxes(self, binary: np.ndarray) -> list:
        """CRAFT 순방향 → 행 단위 박스 리스트 반환 (debug_levels.py용)."""
        pred = self._craft_raw_prediction(binary)
        return pred.get("boxes", [])

    def _chars_from_score_map(self, pred: dict, binary: np.ndarray) -> List[Dict]:
        """
        CRAFT character score map에서 직접 글자 bbox 추출.

        Pass 1 (no dilation): blob 밀도(density)로 adaptive DIL_R 결정
          density = blob수 / (score_map면적/1000)
          - density < 0.08 → 큰/띄어쓴 손글씨 → DIL_R=5 (자소 blob 합치기)
          - density < 0.40 → 중간 밀도           → DIL_R=3
          - density ≥ 0.40 → 빽빽한 편지         → DIL_R=2 (글자간 gap 보존)
        Pass 2 (adaptive dilation): 음절 내 자소 blob 합치기
        사이즈 필터: median × 15% 미만 파편 제거
        넓은 박스 (w > 40px AND w > h×1.4): column projection으로 재분할
          - 40px 미만은 자소 단위 → col proj 금지 (분리 방지)
        """
        score_text = pred.get("score_text_raw")
        target_ratio = pred.get("target_ratio", 1.0)
        if score_text is None:
            return []

        img_h, img_w = binary.shape[:2]
        scale = 2.0 / target_ratio
        score_h, score_w = score_text.shape

        thresh = (score_text >= 0.5).astype(np.uint8) * 255

        # Pass 1: dilation 없이 blob 밀도 측정 → adaptive DIL_R / score_thresh
        n1, _, stats1, _ = cv2.connectedComponentsWithStats(thresh, connectivity=8)
        n_blobs1 = sum(1 for lbl in range(1, n1) if stats1[lbl, cv2.CC_STAT_AREA] >= 8)
        density = n_blobs1 / (score_h * score_w / 1000.0)
        if density < 0.05:
            DIL_R = 7;  score_thresh = 0.50   # 큰 손글씨: 자소 blob 최대 합치기
        elif density < 0.08:
            DIL_R = 5;  score_thresh = 0.50   # 넓은 손글씨
        elif density < 0.20:
            DIL_R = 3;  score_thresh = 0.50   # 중간 밀도
        elif density < 0.80:
            DIL_R = 2;  score_thresh = 0.65   # 중간밀도 편지: 엄격한 이진화로 음절 분리
        else:
            DIL_R = 2;  score_thresh = 0.50   # 빽빽한 편지
        print(f"  [score_map] density={density:.3f}  DIL_R={DIL_R}  thresh={score_thresh}")

        # Pass 2: adaptive threshold + adaptive dilation → CC
        thresh2 = (score_text >= score_thresh).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (DIL_R * 2 + 1, DIL_R * 2 + 1)
        )
        dilated = cv2.dilate(thresh2, kernel)
        n_labels, _, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)

        # 적응형 사이즈 필터: median × 15% 미만 파편 제거
        all_areas = [stats[lbl, cv2.CC_STAT_AREA] for lbl in range(1, n_labels)]
        if not all_areas:
            return []
        min_area = max(15, int(float(np.median(all_areas)) * 0.15))

        # score map 좌표 → 원본 좌표 변환 (score 좌표도 함께 보관)
        rough_boxes = []
        for lbl in range(1, n_labels):
            if stats[lbl, cv2.CC_STAT_AREA] < min_area:
                continue
            sx = stats[lbl, cv2.CC_STAT_LEFT]
            sy = stats[lbl, cv2.CC_STAT_TOP]
            sw = stats[lbl, cv2.CC_STAT_WIDTH]
            sh = stats[lbl, cv2.CC_STAT_HEIGHT]
            x0 = max(0, int(sx * scale))
            y0 = max(0, int(sy * scale))
            x1 = min(img_w, int((sx + sw) * scale))
            y1 = min(img_h, int((sy + sh) * scale))
            if x1 > x0 and y1 > y0:
                rough_boxes.append((x0, y0, x1, y1, sx, sy, sw, sh))

        result = []
        for x0, y0, x1, y1, sx, sy, sw, sh in rough_boxes:
            w_box = x1 - x0
            h_box = y1 - y0

            # 넓은 박스: score_text 컬럼 프로파일로 글자 경계 탐지
            # (binary col proj는 자소 획에도 반응해 과분할 → score map 사용)
            if w_box > 40 and w_box > h_box * 1.2 and h_box > 15:
                sub = self._split_wide_by_score(
                    score_text, sx, sy, sw, sh, scale, x0, y0, y1, binary, img_w
                )
                result.extend(sub)
            else:
                # 단일 글자 → binary로 정밀 bbox 보정
                seg = binary[y0:y1, x0:x1]
                if not np.any(seg > 0):
                    continue
                ink_rows = np.any(seg > 0, axis=1)
                ink_cols = np.any(seg > 0, axis=0)
                if not np.any(ink_rows) or not np.any(ink_cols):
                    continue
                ys = np.where(ink_rows)[0]
                xs = np.where(ink_cols)[0]
                result.append({
                    "x": x0 + int(xs[0]),
                    "y": y0 + int(ys[0]),
                    "w": int(xs[-1]) - int(xs[0]) + 1,
                    "h": int(ys[-1]) - int(ys[0]) + 1,
                })

        # sparse 손글씨에서 한 음절이 두 score blob으로 분리되는 경우 합치기
        # (예: 실 → ㅅ+ㄹ, 음 → ㅇ+본체 등)
        if density < 0.10:
            result = self._vertical_merge_result_boxes(result)

        return result

    def _vertical_merge_result_boxes(self, boxes: List[Dict]) -> List[Dict]:
        """
        X 방향으로 크게 겹치고 수직으로 인접한 박스 쌍을 합친다.
        sparse 손글씨에서 단일 음절(실, 음 등)이 ㅅ+ㄹ, ㅇ+몸통 등
        두 개 score blob으로 분리될 때 복원하는 후처리.
        """
        changed = True
        while changed:
            changed = False
            n = len(boxes)
            merged_flags = [False] * n
            new_boxes: List[Dict] = []
            for i in range(n):
                if merged_flags[i]:
                    continue
                a = boxes[i]
                found_j = -1
                for j in range(i + 1, n):
                    if merged_flags[j]:
                        continue
                    b = boxes[j]
                    top, bot = (a, b) if a["y"] <= b["y"] else (b, a)
                    tx0 = top["x"]; tx1 = tx0 + top["w"]
                    ty1 = top["y"] + top["h"]
                    bx0 = bot["x"]; bx1 = bx0 + bot["w"]
                    by0 = bot["y"]
                    x_overlap = max(0, min(tx1, bx1) - max(tx0, bx0))
                    x_ratio = x_overlap / max(1, min(top["w"], bot["w"]))
                    y_gap = by0 - ty1  # 음수면 수직 중첩
                    if x_ratio > 0.50 and -10 <= y_gap <= 20:
                        found_j = j
                        break
                if found_j >= 0:
                    b = boxes[found_j]
                    nx0 = min(a["x"], b["x"])
                    ny0 = min(a["y"], b["y"])
                    nx1 = max(a["x"] + a["w"], b["x"] + b["w"])
                    ny1 = max(a["y"] + a["h"], b["y"] + b["h"])
                    new_boxes.append({"x": nx0, "y": ny0,
                                      "w": nx1 - nx0, "h": ny1 - ny0})
                    merged_flags[found_j] = True
                    changed = True
                else:
                    new_boxes.append(a)
            boxes = new_boxes
        return boxes

    def _split_wide_by_score(
        self,
        score_text: np.ndarray,
        sx: int, sy: int, sw: int, sh: int,
        scale: float,
        x0: int, y0: int, y1: int,
        binary: np.ndarray,
        img_w: int,
    ) -> List[Dict]:
        """
        넓은 score-map blob을 score_text 컬럼 프로파일로 분할.

        binary col proj는 자소 획 단위로 반응해 과분할 발생.
        score_text는 CRAFT가 학습한 글자 경계를 직접 반영하므로
        인접 글자 사이에서 자연스럽게 낮은 값이 나타남.
        """
        crop = score_text[sy:sy + sh, sx:sx + sw]
        if crop.size == 0:
            return []

        # 컬럼별 최댓값 프로파일 (글자 영역 = 높은 값)
        col_max = np.max(crop, axis=0)
        if col_max.max() == 0:
            return []

        # score 공간에서 smoothing (blob 너비의 ~10%)
        k = max(1, sw // 10)
        col_s = np.convolve(col_max, np.ones(k) / k, mode='same')
        col_n = col_s / col_s.max()

        # 글자 영역: score > 15% (inter-char valley 탐지 민감도 높임)
        in_char = col_n > 0.15
        spans: List[List[int]] = []
        start = None
        for i, v in enumerate(in_char):
            if v and start is None:
                start = i
            elif not v and start is not None:
                spans.append([start, i])
                start = None
        if start is not None:
            spans.append([start, sw])

        if not spans:
            return []

        # 1 score-pixel 이하 gap 병합
        merged: List[List[int]] = [spans[0][:]]
        for s in spans[1:]:
            if s[0] - merged[-1][1] <= 1:
                merged[-1][1] = s[1]
            else:
                merged.append(s[:])

        # score 좌표 → 원본 좌표 + binary 정밀 bbox
        result = []
        for s0, s1 in merged:
            bx0 = max(0, int((sx + s0) * scale))
            bx1 = min(img_w, int((sx + s1) * scale))
            if bx1 <= bx0:
                continue
            seg = binary[y0:y1, bx0:bx1]
            if not np.any(seg > 0):
                continue
            ys = np.where(np.any(seg > 0, axis=1))[0]
            xs = np.where(np.any(seg > 0, axis=0))[0]
            if len(ys) == 0 or len(xs) == 0:
                continue
            result.append({
                "x": bx0 + int(xs[0]),
                "y": y0 + int(ys[0]),
                "w": int(xs[-1]) - int(xs[0]) + 1,
                "h": int(ys[-1]) - int(ys[0]) + 1,
            })
        return result

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
