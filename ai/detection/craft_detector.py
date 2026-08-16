"""
SFR-004I: CRAFT 기본 출력 기반 글자 탐지

파이프라인
---------
1. CRAFT 추론 → boxes (4점 다각형), score_text_raw
2. 각 박스 내 binary image 잉크 픽셀로 tight bbox 재계산
3. score map 평균으로 confidence 계산
4. 읽기 순서 정렬
5. 최종 박스별 세로획 기반 slant 각도 측정 (angle, angle_reliable)

반환: AI_MODEL_INTERFACE.md SFR-004I 스펙 준수
  char_id, bounding_box(x/y/width/height), angle, angle_reliable, confidence

angle 산출 방식 (2026-07-19 교체)
--------------------------------
과거에는 잉크 픽셀 전체의 cv2.minAreaRect 방향을 angle로 썼으나, 이는 글자
외곽 형태가 결정하는 값이라 둥근 글자('둥')·대각획 글자('한')에서 곧게 쓴
글씨도 ±30~45°로 튀는 구조적 오류가 있었다 (E2E 실측). 현재는 사람이 체감하는
"글씨 기울임"에 해당하는 **세로획 slant**를 측정한다:
  - 글자 ROI에 HoughLinesP로 선분 추출 → 수직 ±25° 이내 선분만 채택
  - 선분 길이 가중 평균 slant (양수 = 시계방향 = 글자 상단이 오른쪽으로 기움)
  - 채택된 세로획 총 길이가 글자 높이의 60% 미만이면 측정 불가로 판정하고
    angle=0.0, angle_reliable=False 반환 (ㅇ 위주 글자 등) — 후단 분석기는
    reliable한 글자만 모아 문서 단위 기울기를 평가한다.
"""
import logging
import threading
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional

from craft_text_detector import Craft
from craft_text_detector.predict import get_prediction

logger = logging.getLogger(__name__)

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
_MERGE_W_CAP_ASPECT = 1.4    # 클러스터 폭 ≤ 1.4 × 클러스터 높이 (음절은 대략 정사각형)
# 1.6 → 1.4 하향(2026-07-18): 실측에서 잘못된 2음절 병합 박스는 전부 w/h
# 1.42~1.58 구간이었고, 자소 병합으로 만들어지는 정상 음절은 ~1.2 이하였음.
# 완성 음절 판정 (fragment gate): 높이가 행 ref_h의 이 비율 이상이고 폭이
# _SYLLABLE_W_RATIO 이상이면 "이미 완성된 음절"로 보고, 완성 음절끼리의
# 가로 병합을 금지한다. 병합 후처리는 자소 파편 복구용인데, 자간이 좁은
# 중대형 글씨에서 멀쩡한 인접 음절 두 개를 붙이는 오작동이 있었음(2026-07-18
# 실측: test6 raw 22개(정답)가 병합 후 18개). 파편(낮은 조각·세로획 등)은
# 이 판정에 안 걸려 기존처럼 병합된다.
_SYLLABLE_H_RATIO = 0.70
_SYLLABLE_W_RATIO = 0.50
_MERGE_H_CAP_REF = 1.10      # 클러스터 높이 ≤ 1.10 × 행 ref_h (행 넘는 세로 병합 차단)


# 행 편입에 요구되는 최소 y겹침 (박스 자신 높이 대비 비율).
# 1px만 겹쳐도 같은 행으로 묶던 기존 방식은 밀집 다행 텍스트에서 행끼리 연쇄
# 결합(transitive chaining)되는 문제가 있었음 — 실측: test3에서 실제 5~6개 행이
# 하나의 "행"(y범위 238px)으로 묶여 ref_h가 폭주, 병합 제약이 무력화되어
# 문단 크기 통짜 박스가 생성됨 (2026-07-18 진단).
_ROW_OVERLAP_MIN = 0.40


def _group_rows(chars: List[Dict]) -> List[List[int]]:
    """y구간이 겹치는 박스들을 같은 행으로 묶는다 (파편이어도 키 큰 자소와 겹침).

    편입 조건: 박스 y구간이 행 span과 "박스 자신 높이의 40% 이상" 겹칠 것.
    파편(h≈14px)은 5~6px만 걸쳐도 편입되므로 소형 밀집 파편 행은 기존처럼
    묶이고, 행 사이에 1~2px 걸친 이웃 행 박스의 연쇄 결합만 차단된다.
    """
    order = sorted(range(len(chars)), key=lambda i: chars[i]["y"])
    rows: List[List[int]] = []
    spans: List[List[float]] = []  # 행별 [y0, y1]
    for i in order:
        y0, y1 = chars[i]["y"], chars[i]["y"] + chars[i]["h"]
        need = max(1.0, (y1 - y0) * _ROW_OVERLAP_MIN)
        placed = False
        for row, span in zip(rows, spans):
            if min(y1, span[1]) - max(y0, span[0]) >= need:
                row.append(i)
                span[0], span[1] = min(span[0], y0), max(span[1], y1)
                placed = True
                break
        if not placed:
            rows.append([i])
            spans.append([y0, y1])
    return rows


def _row_ref_height(members: List[Dict]) -> float:
    """
    행 기준 높이(ref_h) — 병합/분할 제약의 스케일 기준.

    - 행 y범위(10~90분위) 단독(기존 v2)은 baseline 출렁임·받침 유무 때문에 실제
      음절 높이보다 1.4~2배 과대해져(실측: test6 h중앙 81 vs ref 122) 인접 음절
      병합을 허용하는 원인이었음.
    - 박스 높이 90분위 단독(v1)은 전부 파편인 행(소형 밀집)에서 과소해져 병합을
      봉쇄했던 실패 이력이 있음 (DETECTION_IMPROVEMENT_PLAN.md 3단계).
    - 절충: y범위를 상한 h90×1.3으로 클램프 — 정상 행에서는 h90 근처로 내려와
      과대를 막고, 파편 행에서는 y범위(≈음절 높이)가 h90×1.3보다 작아 그대로
      유지된다.
    """
    n = len(members)
    y0s = sorted(c["y"] for c in members)
    y1s = sorted(c["y"] + c["h"] for c in members)
    y_range = y1s[min(n - 1, int(n * 0.9))] - y0s[int(n * 0.1)]
    hs = sorted(c["h"] for c in members)
    h90 = hs[min(n - 1, int(n * 0.9))]
    return min(y_range, h90 * 1.3)


# [기록] 8단계의 "세로 잉크 확장" 세 변형은 전부 순효과 음수로 미채택됐으나, 당시
# 실패 원인이던 행 그룹핑 연쇄결합 버그가 11단계에서 수정된 뒤 12단계에서
# 안전장치(과반 소속 기준 + 행 ref 상한)를 갖춘 CC 기반 박스 완성(complete_boxes)
# 으로 재도전해 채택됨. 상세는 DETECTION_IMPROVEMENT_PLAN.md 8·12단계.

# ── 박스 완성 파라미터 (12단계) ─────────────────────────────────────────
_SPECK_MAX_AREA = 12         # 이 면적(px²) 미만 잉크 CC는 점 노이즈로 보고 제거
_COMPLETE_CC_MIN_AREA = 40   # 완성/흡수 대상이 되는 CC 최소 면적 (label_helper와 동일)
_COMPLETE_OWN_RATIO = 0.5    # CC 픽셀의 이 비율 이상을 덮는 박스가 그 CC를 소유
_ORPHAN_X_OVERLAP = 0.6      # 고아 CC 흡수에 요구되는 x겹침 (CC 폭 대비)
_ORPHAN_Y_GAP_RATIO = 0.35   # 고아 CC 흡수 허용 세로 간격 (행 ref_h 대비)
_COMPLETE_H_CAP = 1.15       # 완성 후 박스 높이 ≤ 1.15 × 행 ref_h (이웃 행 침범 차단)
_COMPLETE_W_CAP = 1.35       # 완성 후 박스 폭 상한 배수 (기존 폭보다 좁아지진 않음)
_COMPLETE_X_GROW = 1.20      # 가로 확장은 기존 폭의 1.2배까지만 — 흘림으로 이웃 음절과
                             # 이어진 CC를 물면 가로로 통째 확장되는 것 차단(세로 복원만 수행)


def _remove_specks(binary: np.ndarray, max_area: int = _SPECK_MAX_AREA) -> np.ndarray:
    """점 노이즈(초소형 CC) 제거 — 스캔/이진화 잡점이 tight bbox와 잉크 투영을
    오염시키는 것을 막는다 (실측: test6 '아' 박스가 주변 잡점 때문에 GT 대비
    세로 1.9배로 부풀었음)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    small = np.where(stats[:, cv2.CC_STAT_AREA] < max_area)[0]
    small = small[small != 0]
    if len(small) == 0:
        return binary
    cleaned = binary.copy()
    cleaned[np.isin(labels, small)] = 0
    return cleaned


# ── 세로획 slant 측정 파라미터 (모듈 docstring 'angle 산출 방식' 참고) ────────
_SLANT_MAX_DEG = 25.0        # 수직에서 이 각도 이내인 선분만 "세로획"으로 채택
_SLANT_MIN_COVER = 0.60      # 채택된 세로획 총 길이 ≥ 글자 높이 × 이 값 → 신뢰
_SLANT_MIN_LINE_RATIO = 0.35  # HoughLinesP minLineLength = 글자 높이 × 이 값


def _measure_slant(binary: np.ndarray, x: float, y: float,
                   w: float, h: float) -> Tuple[float, bool]:
    """글자 박스 내 세로획 기울임(slant)을 측정한다.

    Returns
    -------
    (slant_deg, reliable)
      slant_deg : 수직 기준 기울임(도). 양수 = 시계방향(글자 상단이 오른쪽).
                  reliable=False면 0.0.
      reliable  : 세로획이 충분히 검출됐는지. ㅇ 위주 글자·둥근 흘림처럼
                  수직 성분이 없는 글자는 False (측정 불가 — 평가에서 제외).
    """
    H, W = binary.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x + w) + 1), min(H, int(y + h) + 1)
    if x1 - x0 < 4 or y1 - y0 < 8:
        return 0.0, False
    roi = binary[y0:y1, x0:x1]
    ch = y1 - y0
    min_len = max(6, int(ch * _SLANT_MIN_LINE_RATIO))
    lines = cv2.HoughLinesP(roi, 1, np.pi / 180.0,
                            threshold=max(6, min_len // 2),
                            minLineLength=min_len, maxLineGap=3)
    if lines is None:
        return 0.0, False
    num = den = 0.0
    for lx0, ly0, lx1, ly1 in lines[:, 0]:
        dx, dy = float(lx1 - lx0), float(ly1 - ly0)
        if dy > 0:                       # 아래→위 방향으로 정규화 (dy ≤ 0)
            dx, dy = -dx, -dy
        if dy == 0:
            continue
        slant = float(np.degrees(np.arctan2(dx, -dy)))  # 0=수직, +=상단 오른쪽
        if abs(slant) > _SLANT_MAX_DEG:
            continue
        length = float(np.hypot(dx, dy))
        num += slant * length
        den += length
    if den < ch * _SLANT_MIN_COVER:
        return 0.0, False
    return round(num / den, 2), True


def complete_boxes(chars: List[Dict], binary: np.ndarray) -> List[Dict]:
    """
    CC(연결요소) 기반 박스 완성 후처리 (12단계).

    CRAFT region score는 글자 중심부에서만 강하게 반응해 박스가 음절의 위/아래
    자소를 잘라먹는 경우가 있다 (실측: test.jpg '음'의 ㅇ, '트'의 아래 ㅡ,
    '젝'의 ㄱ받침이 박스 밖 — IoU 0.40~0.66).

    1) 소유 CC 확장: 어떤 박스가 잉크 CC 픽셀의 과반을 덮으면 그 CC는 이 글자의
       획으로 보고 박스를 CC 전체 bbox까지 확장 (잘린 획 복원, x/y 양방향).
    2) 고아 CC 흡수: 어느 박스도 과반을 덮지 못한 CC(떨어져 있는 자소 — 예: '음'
       위의 ㅇ)는 x겹침이 크고 세로로 인접한 박스에 흡수.

    두 경우 모두 행 기준높이(ref_h) 상한을 넘는 확장은 거부한다 — 이웃 행의
    획이나 흘림으로 여러 음절에 걸친 CC로의 폭주를 차단 (8단계 실패 교훈).
    """
    if not chars:
        return chars

    n_cc, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n_cc <= 1:
        return chars

    img_h, img_w = binary.shape[:2]
    areas = stats[:, cv2.CC_STAT_AREA]

    # 행별 ref_h (박스 인덱스 → 소속 행 ref_h)
    ref_of = [0.0] * len(chars)
    for row in _group_rows(chars):
        ref = _row_ref_height([chars[i] for i in row])
        for i in row:
            ref_of[i] = ref

    # 박스별 CC 픽셀 수 집계 + CC별 최대 커버 박스 추적
    own: List[Dict[int, int]] = []          # box idx → {cc: pixel count}
    covered = np.zeros(n_cc, dtype=np.int64)  # CC별 "소유된" 픽셀 수(최대 박스 기준)
    for c in chars:
        x0, y0 = max(0, int(c["x"])), max(0, int(c["y"]))
        x1 = min(img_w, int(c["x"] + c["w"]) + 1)
        y1 = min(img_h, int(c["y"] + c["h"]) + 1)
        cnt = np.bincount(labels[y0:y1, x0:x1].ravel(), minlength=n_cc)
        cnt[0] = 0
        own.append({int(cc): int(cnt[cc]) for cc in np.nonzero(cnt)[0]})
        np.maximum(covered, cnt, out=covered)

    def _try_extend(c: Dict, cc: int, ref: float) -> None:
        gx, gy = stats[cc, cv2.CC_STAT_LEFT], stats[cc, cv2.CC_STAT_TOP]
        gw, gh = stats[cc, cv2.CC_STAT_WIDTH], stats[cc, cv2.CC_STAT_HEIGHT]
        nx0, ny0 = min(c["x"], float(gx)), min(c["y"], float(gy))
        nx1 = max(c["x"] + c["w"], float(gx + gw))
        ny1 = max(c["y"] + c["h"], float(gy + gh))
        nw, nh = nx1 - nx0, ny1 - ny0
        # 가로 과확장(흘림으로 이어진 이웃 음절 CC)이면 x는 유지하고 세로만 복원
        if nw > c["w"] * _COMPLETE_X_GROW or (ref > 0 and nw > ref * _COMPLETE_W_CAP):
            nx0, nx1 = c["x"], c["x"] + c["w"]
            nw = c["w"]
        if ref > 0 and nh > max(c["h"], ref * _COMPLETE_H_CAP):
            return
        c["x"], c["y"], c["w"], c["h"] = nx0, ny0, nw, nh

    # 1) 소유 CC로 확장
    for i, c in enumerate(chars):
        for cc, cnt in own[i].items():
            if areas[cc] >= _COMPLETE_CC_MIN_AREA and cnt >= areas[cc] * _COMPLETE_OWN_RATIO:
                _try_extend(c, cc, ref_of[i])

    # 2) 고아 CC 흡수 (어느 박스도 과반 소유하지 못한 CC)
    for cc in range(1, n_cc):
        if areas[cc] < _COMPLETE_CC_MIN_AREA or covered[cc] >= areas[cc] * _COMPLETE_OWN_RATIO:
            continue
        gx, gy = float(stats[cc, cv2.CC_STAT_LEFT]), float(stats[cc, cv2.CC_STAT_TOP])
        gw, gh = float(stats[cc, cv2.CC_STAT_WIDTH]), float(stats[cc, cv2.CC_STAT_HEIGHT])
        best_i, best_key = -1, None
        for i, c in enumerate(chars):
            x_ov = max(0.0, min(c["x"] + c["w"], gx + gw) - max(c["x"], gx))
            if gw <= 0 or x_ov / gw < _ORPHAN_X_OVERLAP:
                continue
            y_gap = max(gy - (c["y"] + c["h"]), c["y"] - (gy + gh))
            if ref_of[i] <= 0 or y_gap > ref_of[i] * _ORPHAN_Y_GAP_RATIO:
                continue
            key = (max(0.0, y_gap), -x_ov)
            if best_key is None or key < best_key:
                best_i, best_key = i, key
        if best_i >= 0:
            _try_extend(chars[best_i], cc, ref_of[best_i])

    return chars

# 과폭 박스 분할: 행 높이 대비 이 배수보다 넓으면 다음절 병합으로 보고 분할 시도
# 1.35 → 1.30 → 1.25 (2026-07-18): test6의 CRAFT 원출력 2음절 박스(쉬운)가 폭
# 150~159 vs 행 ref 118~122 = 1.27~1.30배로 트리거 경계에 걸쳐 있었음. 아래
# 골짜기 검증(_SPLIT_VALLEY_MAX)이 추가되어 정상 단일 음절은 골짜기가 없어
# 잘리지 않으므로 트리거를 공격적으로 낮출 수 있다.
_SPLIT_W_TRIGGER = 1.25
# 분할 경계 탐색 창: 등분 지점 기준 ± (조각 폭 × 이 비율) 안에서 잉크 최소 열을 찾음
_SPLIT_SEARCH_RATIO = 0.25
# 골짜기 검증: 분할 열의 잉크 픽셀 수가 (박스높이 × 이 비율) 이하일 때만 유효한
# 음절 경계로 인정 — 글자 내부(획이 지나가는 곳)를 억지로 자르는 것을 방지.
# 0.25: 세로획 관통부(잉크 ≈ 박스높이의 50~100%)는 확실히 거부하면서, 소형
# 글씨(박스높이 30px → 허용 7.5px)의 정당한 음절 경계는 통과하는 수준
_SPLIT_VALLEY_MAX = 0.25
# 분할 조각 최소 폭 (행 ref_h 대비): 이보다 좁은 조각이 나오는 분할은 음절 경계가
# 아니라 자소/획 조각을 떼어낸 것으로 보고 분할 전체를 포기 — 소형 밀집 글씨에서
# 트리거 하향(1.25)으로 인한 과분할을 억제
_SPLIT_MIN_PIECE = 0.30

# ── 좁게 붙은 2음절 분할 (13단계) ────────────────────────────────────────
# '오른'·'급한'처럼 자간 없이 붙여 쓴 2음절은 폭이 정상 음절 범위(w/h 1.0~1.3)에
# 들어와 위의 과폭 트리거로는 잡히지 않는다. 잉크 골짜기만으로는 자모 사이
# 세로 여백(예: '젝'의 ㅈ|ㅔ — 잉크 0)과 음절 경계를 구분할 수 없음을 실측으로
# 확인('젝' 오분할). 대신 CRAFT region score map을 판정 신호로 사용한다 —
# region score는 "문자 중심 확률"이므로 2음절 박스에는 피크가 2개, 단일 음절에는
# 1개 나타난다. 모델이 이미 제공하는 신호라 글씨체/크기 도메인에 무관하다.
_NSPLIT_W_MIN = 0.95         # 후보 최소 폭 (행 ref_h 대비)
_NSPLIT_ASPECT_MIN = 1.05    # 후보 최소 w/h — 정사각 이하(정상 음절)는 제외
_NSPLIT_PEAK_MIN = 0.35      # 피크로 인정할 최소 region score (low_text 근방)
_NSPLIT_PEAK_DIST = 0.50     # 두 피크의 최소 간격 (행 ref_h 대비) — 자소 피크 배제
_NSPLIT_VALLEY_RATIO = 0.65  # 계곡 score ≤ 낮은 피크 × 이 비율일 때만 "두 중심" 인정
_NSPLIT_MIN_PIECE_W = 0.40   # 두 조각 각각의 최소 폭 (행 ref_h 대비)
_NSPLIT_PIECE_ASPECT = 1.5   # 조각 w/h 상한 (조각이 음절 모양이어야 함)


def _try_narrow_split(c: Dict, roi: np.ndarray, x0: int, y0: int, ref_h: float,
                      score: Optional[np.ndarray], scale: float) -> Optional[List[Dict]]:
    """
    좁게 붙은 2음절 후보를 region score 피크 증거로 2분할 시도. 실패 시 None.

    score : CRAFT score_text_raw (이미지 좌표 = score 좌표 × scale)
    """
    if score is None or ref_h <= 0:
        return None
    sh, sw = score.shape[:2]
    sx0 = max(0, int(c["x"] / scale))
    sx1 = min(sw, int((c["x"] + c["w"]) / scale) + 1)
    sy0 = max(0, int(c["y"] / scale))
    sy1 = min(sh, int((c["y"] + c["h"]) / scale) + 1)
    if sx1 - sx0 < 6 or sy1 - sy0 < 2:
        return None

    prof = score[sy0:sy1, sx0:sx1].max(axis=0).astype(np.float32)
    k = 3
    prof_s = np.convolve(prof, np.ones(k, dtype=np.float32) / k, mode="same")

    # 국소 최대(피크) 탐색 — 최소 간격은 행 높이의 절반 (자소 단위 피크 배제)
    min_dist = max(2, int(ref_h * _NSPLIT_PEAK_DIST / scale))
    peaks: List[int] = []
    for i in range(len(prof_s)):
        lo = max(0, i - min_dist)
        hi = min(len(prof_s), i + min_dist + 1)
        if prof_s[i] >= _NSPLIT_PEAK_MIN and prof_s[i] >= prof_s[lo:hi].max():
            if not peaks or i - peaks[-1] >= min_dist:
                peaks.append(i)
    if len(peaks) != 2:
        return None  # 문자 중심이 2개일 때만 — 1개(단일 음절)/3개+(불확실)는 보류

    valley_rel = peaks[0] + int(np.argmin(prof_s[peaks[0]:peaks[1] + 1]))
    valley_val = prof_s[valley_rel]
    if valley_val > min(prof_s[peaks[0]], prof_s[peaks[1]]) * _NSPLIT_VALLEY_RATIO:
        return None  # 두 피크가 한 덩어리로 이어짐 — 복합 자모일 가능성

    cut = int((sx0 + valley_rel) * scale) - x0  # roi 내 x좌표
    if cut < 2 or cut > roi.shape[1] - 2:
        return None

    pieces = []
    for b0, b1 in ((0, cut), (cut, roi.shape[1])):
        part = roi[:, b0:b1]
        ys, xs = np.where(part > 0)
        if len(xs) == 0:
            return None
        pw = float(xs.max() - xs.min() + 1)
        ph = float(ys.max() - ys.min() + 1)
        if pw < ref_h * _NSPLIT_MIN_PIECE_W:
            return None
        if ph <= 0 or pw / ph > _NSPLIT_PIECE_ASPECT:
            return None
        pieces.append({
            "x": float(x0 + b0 + xs.min()), "y": float(y0 + ys.min()),
            "w": pw, "h": ph,
            "conf": c["conf"], "split_from": id(c),
        })
    return pieces


def split_wide_boxes(chars: List[Dict], binary: np.ndarray,
                     score: Optional[np.ndarray] = None,
                     scale: float = 1.0) -> List[Dict]:
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
        ref_h = _row_ref_height(members)

        for c in members:
            if ref_h <= 0:
                out.append(c)
                continue
            if c["w"] <= ref_h * _SPLIT_W_TRIGGER:
                # 과폭 미달 — 좁게 붙은 2음절 후보인지 검사 (잉크 증거 기반)
                if (c["w"] >= ref_h * _NSPLIT_W_MIN and c["h"] > 0
                        and c["w"] / c["h"] >= _NSPLIT_ASPECT_MIN):
                    nx0, ny0 = max(0, int(c["x"])), max(0, int(c["y"]))
                    nx1 = min(img_w, int(c["x"] + c["w"]) + 1)
                    ny1 = min(img_h, int(c["y"] + c["h"]) + 1)
                    n_roi = binary[ny0:ny1, nx0:nx1]
                    if n_roi.size:
                        pieces = _try_narrow_split(c, n_roi, nx0, ny0, ref_h, score, scale)
                        if pieces:
                            out.extend(pieces)
                            continue
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
            valley_cap = max(2.0, (y1 - y0) * _SPLIT_VALLEY_MAX)
            for i in range(1, k):
                center = int(i * piece_w)
                lo = max(1, center - search)
                hi = min(len(col_ink) - 1, center + search)
                if lo >= hi:
                    continue
                cut = lo + int(np.argmin(col_ink[lo:hi]))
                if col_ink[cut] <= valley_cap:  # 진짜 골짜기일 때만 자름
                    cuts.append(cut)
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
                    "conf": c["conf"],
                    # 같은 원본 박스에서 잘려 나온 조각끼리는 merge_jaso_boxes가
                    # 가로로 도로 붙이지 않도록 원본 id를 기록 (분할 취지 보존).
                    # 세로 병합(잘린 조각과 위/아래 받침 파편)은 허용된다.
                    "split_from": id(c),
                })
            if len(pieces) >= 2 and all(p["w"] >= ref_h * _SPLIT_MIN_PIECE for p in pieces):
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

    ref_h = _row_ref_height(chars)
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
            # split_wide_boxes가 같은 원본에서 자른 조각끼리의 가로 재결합은 금지
            # (분할 결정을 병합이 되돌리는 순환 방지). 세로 결합은 허용.
            if horizontal_ok and chars[i].get("split_from") is not None \
                    and chars[i].get("split_from") == chars[j].get("split_from"):
                horizontal_ok = False
            vertical_ok = (y_gap <= v_gap_max
                           and min_w > 0 and x_ov / min_w >= _MERGE_X_OVERLAP_MIN)
            if horizontal_ok or vertical_ok:
                pairs.append((max(x_gap, y_gap), i, j))
    pairs.sort()

    syl_h = ref_h * _SYLLABLE_H_RATIO
    syl_w = ref_h * _SYLLABLE_W_RATIO

    def _is_syllable(box) -> bool:
        return (box[3] - box[1]) >= syl_h and (box[2] - box[0]) >= syl_w

    for _, i, j in pairs:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        bi, bj = cluster[ri], cluster[rj]
        # fragment gate: 두 클러스터 모두 이미 완성 음절 크기이고 가로로 나란하면
        # (y겹침 존재) 붙일 이유가 없다 — 인접 음절 병합 오작동 차단.
        # 세로 결합(받침 등)은 y겹침이 없어 이 조건에 걸리지 않는다.
        if _is_syllable(bi) and _is_syllable(bj) \
                and _ov(bi[1], bi[3], bj[1], bj[3]) > 0:
            continue
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
            "conf": float(conf),
        })
    return merged


class CraftDetector:

    def __init__(
        self,
        cuda: bool = False,
        long_size: int = 960,
        text_threshold: float = 0.7,
        link_threshold: float = 1.0,
        # ⚠️ text_threshold·low_text가 **요구사항 SFR-004I ④ "낮은 확신 탐지 필터링"의
        # 실제 구현체**다. 명세는 이를 단일 임계값 0.5로 적었지만, 실제로는 봉우리
        # 기준(0.7)과 영역 기준(0.4) 두 단계로 나누는 편이 정확해 평가셋 측정으로
        # 이 값들을 정했다(F1@0.3=0.891이 이 설정 기준 수치).
        # → 응답에 실리는 `confidence`로 뒤늦게 0.5 필터를 또 거는 일을 하지 말 것.
        #   그건 이중 필터링이고 위 수치의 기준선을 무효로 만든다. confidence는
        #   게이트가 아니라 보고용 값이다(DEVLOG 22막).
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
        # pretrained CRAFT 로드 (파인튜닝은 롤백됨 — 추후 상황 보고 재개).
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
            weight_path_craft_net=None,
        )
        self._use_dist = use_dist_transform
        self._adaptive_scale = adaptive_scale
        self._base_long_size = long_size

    # ------------------------------------------------------------------ #
    # 공개 API
    # ------------------------------------------------------------------ #

    def detect(self, binary_image: np.ndarray) -> List[Dict]:
        """
        Parameters
        ----------
        binary_image : (H, W) uint8, 값 0(배경) or 255(획)
        """
        # CRAFT 추론 입력은 원본 그대로 유지 (노이즈 제거가 distance-transform을
        # 바꾸면 region 출력 자체가 흔들림 — 실측: '한' 과분할, '음' 박스 소멸).
        # 점 노이즈 제거본은 박스 기하 연산(tight bbox·분할 투영·완성)에만 사용.
        clean = _remove_specks(binary_image)
        pred  = self._craft_prediction(binary_image)
        score = pred.get("score_text_raw")
        scale = 2.0 / pred.get("target_ratio", 1.0)
        chars = self._process_boxes(pred, clean)
        chars = split_wide_boxes(chars, clean, score=score, scale=scale)
        chars = merge_jaso_boxes(chars)
        chars = complete_boxes(chars, clean)
        chars = self._sort_reading_order(chars, binary_image.shape)
        logger.debug("→ %d chars detected", len(chars))
        return self._format_output(chars, clean)

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
            logger.debug("[scale] long_size=%d (adaptive)", chosen)
        if self._use_dist:
            dist      = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
            dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            rgb = cv2.cvtColor(dist_norm, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
        # poly=False: crop_type="box"라 폴리곤은 쓰지 않는데, 기본 poly=True는 가변 길이
        # 폴리곤을 만들어 adjustResultCoordinates의 np.array(polys)가 터진다(풀해상도·고
        # long_size에서 재현). 박스 결과는 poly 값과 무관하게 동일하다.
        c = self._craft
        return get_prediction(
            image=rgb, craft_net=c.craft_net, refine_net=c.refine_net,
            text_threshold=c.text_threshold, link_threshold=c.link_threshold,
            low_text=c.low_text, cuda=c.cuda, long_size=c.long_size, poly=False,
        )

    def _process_boxes(self, pred: dict, binary: np.ndarray) -> List[Dict]:
        """CRAFT boxes → tight bbox + angle + confidence."""
        boxes        = pred.get("boxes", [])
        score        = pred.get("score_text_raw")
        target_ratio = pred.get("target_ratio", 1.0)
        scale        = 2.0 / target_ratio

        score_h = score.shape[0] if score is not None else 1
        score_w = score.shape[1] if score is not None else 1

        logger.debug("[craft] %d boxes", len(boxes))

        chars: List[Dict] = []
        for box in boxes:
            pts = np.array(box, dtype=np.float32)  # (4, 2) — [[x,y], ...]

            # CRAFT 박스 내 잉크 픽셀로 tight bbox 재계산
            result = self._tighten_box(pts, binary)
            if result is None:
                continue
            tx, ty, tw, th, ink_pts_xy = result

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
                "conf": conf,
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

    def _format_output(self, chars: List[Dict], binary: np.ndarray) -> List[Dict]:
        """AI_MODEL_INTERFACE.md SFR-004I 스펙 형식. angle은 최종 박스의 세로획 slant."""
        out = []
        for i, c in enumerate(chars):
            slant, reliable = _measure_slant(binary, c["x"], c["y"], c["w"], c["h"])
            out.append({
                "char_id": f"char_{i}",
                "bounding_box": {
                    "x":      c["x"],
                    "y":      c["y"],
                    "width":  c["w"],
                    "height": c["h"],
                },
                "angle":          slant,
                "angle_reliable": reliable,
                "confidence":     float(c["conf"]),
            })
        return out


# ------------------------------------------------------------------ #
# SFR-004I 인터페이스 함수 (백엔드 연동용)
# ------------------------------------------------------------------ #

# 서버 환경에서는 요청마다 모델을 새로 로드하면 안 되므로(로드 ~4s) 프로세스당
# 1개의 CraftDetector를 공유한다. detect()가 adaptive long_size로 공유 인스턴스
# 상태를 바꾸므로 동시 호출은 lock으로 직렬화한다 — CPU 추론은 어차피 코어를
# 다 쓰는 단일 작업이라 직렬화로 인한 추가 손해는 사실상 없다.
_shared_lock = threading.Lock()
_shared_detector: Optional["CraftDetector"] = None


def get_shared_detector(cuda: bool = False) -> "CraftDetector":
    """프로세스 전역 CraftDetector 싱글턴 (최초 호출 시 1회 로드)."""
    global _shared_detector
    if _shared_detector is None:
        with _shared_lock:
            if _shared_detector is None:
                logger.info("CraftDetector 최초 로드 (프로세스당 1회)")
                _shared_detector = CraftDetector(cuda=cuda)
    return _shared_detector


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
    cuda              : 최초 로드 시에만 반영됨 (싱글턴 재사용)
    """
    image = np.array(binary_image_list, dtype=np.uint8)
    if image.shape != (image_height, image_width):
        image = cv2.resize(
            image, (image_width, image_height),
            interpolation=cv2.INTER_NEAREST,
        )
    detector = get_shared_detector(cuda=cuda)
    with _shared_lock:
        return detector.detect(image)
