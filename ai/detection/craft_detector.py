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
import logging
import os
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional

from craft_text_detector import Craft

logger = logging.getLogger(__name__)

_FINETUNED_WEIGHT = os.path.join(
    os.path.dirname(__file__), "..", "models", "craft_finetuned_raw.pth"
)

# ── 자소→음절 병합 파라미터 (DETECTION_IMPROVEMENT_PLAN.md 3단계) ────────────
# 기준 높이(ref_h)는 행(row) 단위로 추정: 박스가 자소 파편뿐이어도(소형 밀집
# 손글씨) 같은 행 파편들의 y범위 전체는 음절 높이에 가깝다. 전역 박스 통계는
# 전부 파편인 경우 음절보다 훨씬 작게 나와 병합을 봉쇄하는 문제가 있었음.
_MERGE_H_GAP_RATIO = 0.18    # 가로 병합 허용 간격 (행 ref_h 대비)
_MERGE_V_GAP_RATIO = 0.35    # 세로 병합 허용 간격 (받침/모음이 아래 떨어진 경우)
_MERGE_X_OVERLAP_MIN = 0.40  # 세로 병합 시 요구되는 x 겹침 비율 (좁은 쪽 기준)
_MERGE_Y_OVERLAP_MIN = 0.40  # 가로 병합 시 요구되는 y 겹침 비율 (낮은 쪽 기준)
# 병합 폭주 방지 (음절 기하 제약):
_MERGE_W_CAP_REF = 1.35      # 클러스터 폭 ≤ 1.35 × 행 ref_h
_MERGE_W_CAP_ASPECT = 1.6    # 클러스터 폭 ≤ 1.6 × 클러스터 높이 (음절은 대략 정사각형)
_MERGE_H_CAP_REF = 1.10      # 클러스터 높이 ≤ 1.10 × 행 ref_h (행 넘는 세로 병합 차단)


def _group_rows(chars: List[Dict]) -> List[List[int]]:
    """y구간이 겹치는 박스들을 같은 행으로 묶는다 (파편이어도 키 큰 자소와 겹침)."""
    order = sorted(range(len(chars)), key=lambda i: chars[i]["y"])
    rows: List[List[int]] = []
    spans: List[List[float]] = []  # 행별 [y0, y1]
    for i in order:
        y0, y1 = chars[i]["y"], chars[i]["y"] + chars[i]["h"]
        placed = False
        for row, span in zip(rows, spans):
            if min(y1, span[1]) - max(y0, span[0]) > 0:  # y 겹침
                row.append(i)
                span[0], span[1] = min(span[0], y0), max(span[1], y1)
                placed = True
                break
        if not placed:
            rows.append([i])
            spans.append([y0, y1])
    return rows


# 세로 잉크 확장: CRAFT region score는 글자 중심에서만 강하게 반응해 소형 글씨의
# 박스가 세로 중앙 띠만 덮는 경우가 많다(실측: 음절 높이 30px에 박스 높이 14px).
# 박스의 x창 안에서 잉크가 연속되는 세로 구간까지 박스를 늘려 원래 높이를 복원한다.
# [기록] "세로 잉크 확장" 후처리(박스를 잉크 범위까지 늘려 소형 글씨의 잘린 박스를
# 복원)는 행 투영/노이즈 차단/CC 기반 세 가지 변형을 전부 실측했으나 모두 순효과가
# 음수여서 미채택 — 상세는 DETECTION_IMPROVEMENT_PLAN.md 8단계, 코드는 git 히스토리.

# 과폭 박스 분할: 행 높이 대비 이 배수보다 넓으면 다음절 병합으로 보고 분할 시도
_SPLIT_W_TRIGGER = 1.35
# 분할 경계 탐색 창: 등분 지점 기준 ± (조각 폭 × 이 비율) 안에서 잉크 최소 열을 찾음
_SPLIT_SEARCH_RATIO = 0.25


def split_wide_boxes(chars: List[Dict], binary: np.ndarray) -> List[Dict]:
    """
    CRAFT가 처음부터 붙여서 낸 다음절 박스를 분할하는 후처리 (7단계).

    행 높이(ref_h) 대비 폭이 _SPLIT_W_TRIGGER를 넘는 박스는 N음절 병합으로 보고,
    N등분 지점 근처에서 잉크 수직 투영이 최소가 되는 열을 찾아 그곳에서 자른다.
    잘린 조각은 잉크 기준 tight bbox로 재계산하며, 과하게 잘렸다면 뒤따르는
    merge_jaso_boxes가 음절 기하 제약 안에서 다시 붙인다.
    """
    if not chars:
        return chars

    img_h, img_w = binary.shape[:2]
    out: List[Dict] = []
    for row in _group_rows(chars):
        members = [chars[i] for i in row]
        n = len(members)
        y0s = sorted(c["y"] for c in members)
        y1s = sorted(c["y"] + c["h"] for c in members)
        ref_h = y1s[min(n - 1, int(n * 0.9))] - y0s[int(n * 0.1)]

        for c in members:
            if ref_h <= 0 or c["w"] <= ref_h * _SPLIT_W_TRIGGER:
                out.append(c)
                continue
            k = max(2, int(round(c["w"] / ref_h)))
            x0, y0 = int(c["x"]), int(c["y"])
            x1, y1 = min(img_w, int(c["x"] + c["w"]) + 1), min(img_h, int(c["y"] + c["h"]) + 1)
            roi = binary[y0:y1, x0:x1]
            if roi.size == 0 or not np.any(roi > 0):
                out.append(c)
                continue
            col_ink = (roi > 0).sum(axis=0)

            # k-1개의 분할 열: 등분 지점 근처에서 잉크가 가장 적은 열
            piece_w = (x1 - x0) / k
            search = max(1, int(piece_w * _SPLIT_SEARCH_RATIO))
            cuts = []
            for i in range(1, k):
                center = int(i * piece_w)
                lo = max(1, center - search)
                hi = min(len(col_ink) - 1, center + search)
                if lo >= hi:
                    continue
                cuts.append(lo + int(np.argmin(col_ink[lo:hi])))
            cuts = sorted(set(cuts))
            if not cuts:
                out.append(c)
                continue

            # 조각별 잉크 tight bbox 재계산
            bounds = [0] + cuts + [x1 - x0]
            pieces = []
            for b0, b1 in zip(bounds[:-1], bounds[1:]):
                part = roi[:, b0:b1]
                ys, xs = np.where(part > 0)
                if len(xs) == 0:
                    continue
                pieces.append({
                    "x": float(x0 + b0 + xs.min()),
                    "y": float(y0 + ys.min()),
                    "w": float(xs.max() - xs.min() + 1),
                    "h": float(ys.max() - ys.min() + 1),
                    "angle": c["angle"], "conf": c["conf"],
                })
            if len(pieces) >= 2:
                out.extend(pieces)
            else:
                out.append(c)
    return out


def merge_jaso_boxes(chars: List[Dict]) -> List[Dict]:
    """
    자소 수준으로 과분할된 박스들을 음절 단위로 병합하는 후처리.

    행 단위 Union-Find + "가까운 쌍부터" 그리디 병합. 병합 결과가 음절 기하
    제약(행 높이 대비 폭 상한 + 종횡비 상한)을 넘으면 그 병합은 거부한다 —
    인접 음절끼리 붙는 것을 구조적으로 차단하면서, 이미 음절 크기인 박스
    (큰 글씨)는 병합할 것이 없어 회귀가 최소화된다.
    """
    if len(chars) <= 1:
        return chars

    merged_all: List[Dict] = []
    for row in _group_rows(chars):
        merged_all.extend(_merge_row([chars[i] for i in row]))
    return merged_all


def _merge_row(chars: List[Dict]) -> List[Dict]:
    n = len(chars)
    if n == 1:
        return chars

    # 행 기준 높이: 극단값에 덜 민감하도록 y0의 10분위 ~ y1의 90분위 범위 사용
    y0s = sorted(c["y"] for c in chars)
    y1s = sorted(c["y"] + c["h"] for c in chars)
    ref_h = y1s[min(n - 1, int(n * 0.9))] - y0s[int(n * 0.1)]
    if ref_h <= 0:
        return chars

    h_gap_max = ref_h * _MERGE_H_GAP_RATIO
    v_gap_max = ref_h * _MERGE_V_GAP_RATIO
    w_cap_ref = ref_h * _MERGE_W_CAP_REF
    h_cap = ref_h * _MERGE_H_CAP_REF

    parent = list(range(n))
    cluster = [[c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]] for c in chars]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _ov(a0, a1, b0, b1):
        return max(0.0, min(a1, b1) - max(a0, b0))

    pairs = []
    for i in range(n):
        xi0, yi0, xi1, yi1 = cluster[i]
        for j in range(i + 1, n):
            xj0, yj0, xj1, yj1 = cluster[j]
            x_gap = max(xj0 - xi1, xi0 - xj1)
            y_gap = max(yj0 - yi1, yi0 - yj1)
            y_ov = _ov(yi0, yi1, yj0, yj1)
            min_h = min(yi1 - yi0, yj1 - yj0)
            x_ov = _ov(xi0, xi1, xj0, xj1)
            min_w = min(xi1 - xi0, xj1 - xj0)

            horizontal_ok = (x_gap <= h_gap_max
                             and min_h > 0 and y_ov / min_h >= _MERGE_Y_OVERLAP_MIN)
            vertical_ok = (y_gap <= v_gap_max
                           and min_w > 0 and x_ov / min_w >= _MERGE_X_OVERLAP_MIN)
            if horizontal_ok or vertical_ok:
                pairs.append((max(x_gap, y_gap), i, j))
    pairs.sort()

    for _, i, j in pairs:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        bi, bj = cluster[ri], cluster[rj]
        mx0, my0 = min(bi[0], bj[0]), min(bi[1], bj[1])
        mx1, my1 = max(bi[2], bj[2]), max(bi[3], bj[3])
        mw, mh = mx1 - mx0, my1 - my0
        if mw > w_cap_ref or mw > mh * _MERGE_W_CAP_ASPECT or mh > h_cap:
            continue  # 음절 기하 제약 위반 → 병합 거부
        parent[rj] = ri
        cluster[ri] = [mx0, my0, mx1, my1]

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    merged: List[Dict] = []
    for root, members in groups.items():
        if len(members) == 1:
            merged.append(chars[members[0]])
            continue
        x0, y0, x1, y1 = cluster[root]
        areas = [chars[m]["w"] * chars[m]["h"] for m in members]
        total = sum(areas) or 1.0
        conf = sum(chars[m]["conf"] * a for m, a in zip(members, areas)) / total
        biggest = members[int(np.argmax(areas))]
        merged.append({
            "x": float(x0), "y": float(y0),
            "w": float(x1 - x0), "h": float(y1 - y0),
            "angle": chars[biggest]["angle"], "conf": float(conf),
        })
    return merged


class CraftDetector:

    def __init__(
        self,
        cuda: bool = False,
        long_size: int = 960,
        text_threshold: float = 0.7,
        link_threshold: float = 1.0,
        low_text: float = 0.4,
        use_dist_transform: bool = True,
        adaptive_scale: bool = True,
    ):
        # long_size=960: 실사용 시나리오(연습장의 중대형 손글씨) 평가에서 1280보다
        # 정확도가 높고(글자가 CRAFT 수용영역의 적정 크기에 가까워짐) 추론도
        # ~1.8배 빠름. 단 소형 밀집 글씨(양식지 등)는 더 나빠짐 — 알려진 한계.
        # (평가 근거: DETECTION_IMPROVEMENT_PLAN.md 3·4단계)
        #
        # adaptive_scale=True면 이미지별 잉크 blob 크기로 음절 크기를 추정해
        # long_size를 자동 결정(위 고정값 대신). CRAFT는 글자가 입력에서 특정
        # 픽셀 크기 범위일 때만 잘 반응하므로, 글씨가 작은 이미지는 확대하고
        # 큰 이미지는 그대로/축소해 스케일 트레이드오프를 해소한다 (6단계).
        # link_threshold=1.0: affinity(link) score를 디코딩에서 사실상 제외해
        # region score 단독으로 박스를 만든다. affinity는 "인접 글자를 단어로
        # 묶는" 신호라서 글자 단위 분리가 목표인 이 프로젝트에서는 켜두면
        # 인접 음절이 한 박스로 병합된다 (평가 근거: DETECTION_IMPROVEMENT_PLAN.md
        # 2단계 — 평균 F1@0.3 0.378→0.574, 폰트 텍스트 25/25 정확 일치).
        weight_path = os.path.normpath(_FINETUNED_WEIGHT)
        craft_weight = weight_path if os.path.exists(weight_path) else None
        if craft_weight is None:
            logger.warning(
                "파인튜닝 가중치를 찾을 수 없습니다: %s — 기본 pretrained 가중치로 폴백합니다.",
                weight_path,
            )

        self._craft = self._load_craft(
            craft_weight, text_threshold, link_threshold, low_text, cuda, long_size,
        )
        self._use_dist = use_dist_transform
        self._adaptive_scale = adaptive_scale
        self._base_long_size = long_size

    @staticmethod
    def _load_craft(craft_weight, text_threshold, link_threshold, low_text, cuda, long_size) -> Craft:
        """
        지정된 가중치로 Craft를 생성한다. 체크포인트가 현재 CraftNet 구조와
        호환되지 않는 경우(state_dict 키 불일치 등) 조용히 죽는 대신 pretrained로
        폴백한다 — 학습/추론 아키텍처가 어긋난 옛 체크포인트가 남아 있어도
        서비스 자체는 항상 뜨도록 하기 위함.
        """
        try:
            return Craft(
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
                weight_path_craft_net=craft_weight,
            )
        except Exception:
            if craft_weight is None:
                raise
            logger.exception(
                "파인튜닝 가중치 로드 실패(%s) — 현재 CraftNet 구조와 호환되지 않는 "
                "체크포인트일 수 있습니다. pretrained 가중치로 폴백합니다.",
                craft_weight,
            )
            return Craft(
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
                weight_path_craft_net=None,
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
        chars = self._process_boxes(pred, binary_image)
        chars = split_wide_boxes(chars, binary_image)
        chars = merge_jaso_boxes(chars)
        chars = self._sort_reading_order(chars, binary_image.shape)
        print(f"    → {len(chars)} chars detected")
        return self._format_output(chars)

    def unload(self):
        del self._craft

    # ------------------------------------------------------------------ #
    # 핵심 파이프라인
    # ------------------------------------------------------------------ #

    # 적응형 스케일: CRAFT 입력에서의 목표 음절 높이(px)와 long_size 허용 범위.
    # 평가 근거: 음절이 입력에서 ~77-135px일 때 F1 최고, ~25px에서는 미반응.
    _TARGET_SYLLABLE_PX = 90.0
    _LONG_SIZE_MIN = 768
    _LONG_SIZE_MAX = 2560
    _BLOB_TO_SYLLABLE = 1.8   # 잉크 blob(자소 조각) 높이 중앙값 → 음절 높이 근사 계수

    def _choose_long_size(self, binary: np.ndarray) -> int:
        """잉크 blob 크기로 음절 높이를 추정해 CRAFT 입력 long_size를 결정."""
        n, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        heights = [
            int(stats[i, cv2.CC_STAT_HEIGHT]) for i in range(1, n)
            if stats[i, cv2.CC_STAT_AREA] >= 40 and stats[i, cv2.CC_STAT_HEIGHT] >= 8
        ]
        if not heights:
            return self._base_long_size
        heights.sort()
        est_syllable = heights[len(heights) // 2] * self._BLOB_TO_SYLLABLE
        img_long = max(binary.shape[:2])
        long_size = int(round(img_long * self._TARGET_SYLLABLE_PX / est_syllable / 32) * 32)
        return max(self._LONG_SIZE_MIN, min(self._LONG_SIZE_MAX, long_size))

    def _craft_prediction(self, binary: np.ndarray) -> dict:
        """
        binary → CRAFT 추론.

        use_dist_transform=True (기본):
          Distance Transform으로 잉크 영역에 그레디언트를 복원.
          CRAFT가 텍스처/그레디언트를 기반으로 학습됐으므로 순수 binary보다
          탐지율이 높아짐.
        """
        if self._adaptive_scale:
            chosen = self._choose_long_size(binary)
            self._craft.long_size = chosen
            print(f"  [scale] long_size={chosen} (adaptive)")
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
