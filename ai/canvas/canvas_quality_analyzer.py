"""
SFR-005C: 캔버스 필기 채점 — 획순 / 획방향 / 성분비율 / 크기 / 자간

stroke_grouping.py(SFR-004C)의 char_groups + 목표 텍스트(target_text) + 화면에
그려준 획순 가이드 상자(guide_box)를 받아 글자마다 다섯 항목을 채점한다.

**연습 종류마다 실제로 채점되는 항목이 다르다** (사용자 결정 2026-09-01):
  · 자음·모음(낱자)  획순 · 획방향 · 크기      — 성분이 하나뿐이라 비율은 없다
  · 한 글자          + 성분비율                — 옆 글자가 없어 자간은 없다
  · 단어·문장        + 자간

측정 불가 항목은 **0점이 아니라 None**이고 종합 점수의 분모에서도 빠진다. 재지도
않은 지표로 칭찬하거나 감점하지 않기 위해서다(DATA_FLOW.md §4-1).

설계 메모
--------
- **좌표 프레임을 반드시 맞춘다.** 사용자 획은 자기 잉크 bbox 기준으로 [0,1]에 펴져
  들어오므로, 비교 대상인 표준 템플릿도 **잉크 기준**으로 정규화해야 한다. 선언
  상자를 그대로 쓰면 템플릿이 상자를 꽉 채우지 않는 만큼 통째로 어긋난다.
- **성분비율은 크기와 무관하다.** 글자를 크게 썼든 작게 썼든 자모 사이 비율은 같게
  나온다 — 절대 크기는 '크기' 항목이 가이드 상자 대비로 따로 본다.
- **획순이 틀려도 성분비율은 살아 있다.** 획을 자모에 붙이는 일을 기하 매칭으로
  하기 때문이다. 획 개수로 순서대로 잘라 나누면(참고한 AI-WritingCorrection 방식)
  순서가 틀리는 순간 자모 분해가 무너져 비율 점수가 의미를 잃는다.

한계 노트
--------
- 획순 위치 매칭(analyze_stroke_order_by_position)은 중심점+모양(가로/세로 비율)
  기반 기하 비교라, 자모 내 두 획이 극단적으로 겹쳐 있거나 사용자가 표준과 완전히
  다른 위치에 그리면 오판할 수 있다. "어떤 stroke가 정확히 무슨 글자·획인지"를
  일반적으로 인식하는 수준의 정교함은 아니고, 목표 글자를 이미 아는 상황(제시형
  UI) 한정으로 쓸 수 있는 근사치.
- speed_profile은 **채점에 쓰지 않고 기록만** 한다(사용자 결정 2026-09-01).
  필압(pressure)은 미지원 기기에서 늘 1.0 상수라 신호가 아니어서 제거했다.
- 임계값은 **실사용자 필기로 보정된 값이 아니다.** 합성 데이터로 로직은 검증했지만
  기준 자체의 적절성은 미검증이다.
"""
import math
from typing import Dict, List, Optional, Tuple

from .stroke_grouping import _stroke_bbox
from .stroke_standards import (
    get_expected_sequence, decompose_syllable,
    ALTERNATIVE_STROKE_ORDERS, standard_order_note, CHOSUNG, JUNGSUNG,
)
from .synthetic_stroke_generator import _syllable_layout, _single_jamo_layout

# 크기/간격 판정 임계값 (handwriting_analyzer.py와 동일한 CV 기반 설계)
SIZE_SCORE_MAX_CV = 0.30
SIZE_LARGE_THRESH = 1.5
SIZE_SMALL_THRESH = 0.65

# 자간: 인접 글자 bbox 간 gap을 "평균 글자 너비" 대비 비율로 판단
SPACING_MIN_RATIO = 0.15   # 이보다 좁으면 너무 붙어씀
SPACING_MAX_RATIO = 1.2    # 이보다 넓으면 너무 띄어씀
SPACING_SCORE_MAX_DEV = 1.0  # 비율 편차 1.0(=평균너비만큼 벗어남) → 0점

# 획순 매칭 시 위치 거리 대비 모양(가로/세로 비율) 차이에 두는 가중치.
# 자모 내 두 획의 중심점이 서로 가까운 경우(예: ㅏ의 세로선과 가로 짧은 획)
# 위치만으로는 헷갈리기 쉬워서, 모양(길쭉한 방향)도 같이 비교해 구분한다.
SHAPE_WEIGHT = 1.5

# 목표 글자와 완전히 다른 걸 썼는지 판단하는 임계값 (둘 중 하나라도 넘으면 "다른 글자로 보임")
MATCH_QUALITY_THRESHOLD = 0.6        # 매칭된 획들의 평균 위치+모양 오차 (정규화 좌표 기준)
COUNT_MISMATCH_RATIO_THRESHOLD = 2.0  # 실제 획수/기대 획수 비율이 이 배수 이상 벗어나면 의심

# ── 채점 기준 (단일 출처) ──────────────────────────────────────────────
# ⚠️ 캔버스 채점 기준은 여기 한 곳에만 둔다. 백엔드 대시보드(dashboard_service)도
# 아래 canvas_item_scores()를 호출한다 — 복사본이나 별도 설정값을 만들지 말 것.
# 종전에는 백엔드 config.py에 다른 계수(크기 0.5 / 자간 0.5 / 획순 10)가 따로 있어,
# 같은 글씨인데 결과 화면과 분석 화면의 점수가 어긋났다(DATA_FLOW.md §8-G).
#
# ⚠️ 아래 숫자는 **실사용자 필기로 보정된 값이 아니다.** 합성 데이터로 로직이 맞게
# 도는지는 확인했지만 "이 기준이 적절한가"는 미검증이다. 실사용 데이터가 모이면
# 재조정해야 한다(REQ-005C-6이 요구하는 설정 외부화도 이 시점에 함께).

ITEM_ORDER    = "획순"
ITEM_DIRECTION = "획방향"
ITEM_TILT     = "기울기"
ITEM_BALANCE  = "성분비율"
ITEM_SIZE     = "크기"
ITEM_SPACING  = "자간"

# 종합 점수 가중치. 바르게 쓰는 것(획순·방향·성분비율)에 3, 보조 지표에 2를 둔다.
# 측정 불가(None) 항목은 분모에서도 빠진다 — 재지도 않은 지표로 칭찬·감점하지 않는다.
ITEM_WEIGHTS = {
    ITEM_ORDER: 3.0,
    ITEM_DIRECTION: 3.0,
    ITEM_TILT: 3.0,
    ITEM_BALANCE: 3.0,
    ITEM_SIZE: 2.0,
    ITEM_SPACING: 2.0,
}

ORDER_PENALTY_PER_ERROR = 25.0   # 획순 오류 1건당 감점 (4건이면 0점)

# 획 방향: 사용자 획의 시작→끝 벡터와 표준 획 벡터의 각도차.
# **역방향만 오류로 센다**(사용자 결정 2026-09-01). 이 항목의 목적은 "ㄱ을 아래에서
# 위로 긋지 마라" 같은 **명백한 역행**을 잡는 것이지 획이 몇 도 기울었나가 아니다.
# 기울기는 아래 STRAIGHT_STROKE_MAX_TILT_DEG가 따로 본다 — 두 가지를 한 항목에
# 섞으면 "30도 기울었는데 방향은 맞다"를 설명할 수 없다.
DIRECTION_REVERSED_DEG = 135.0  # 이 이상 어긋나면 역방향(오류 1건)
# 시작점과 끝점이 이만큼(획 크기 대비) 가까우면 닫힌 획(ㅇ)으로 보고 방향을 안 본다.
DIRECTION_CLOSED_RATIO = 0.25

# 곧게 그어야 하는 획(세로·가로)의 기울기 허용치. 표준 각도에서 이만큼 넘게 어긋나면 오류.
# ㅣ·ㅡ처럼 한쪽 변이 0에 가까운 자모는 **종횡비로 재면 안 된다** — 폭이 0에 가까워
# 10도만 기울어도 비율이 442배로 폭발한다(2026-09-01 실측). 각도로 직접 재야
# "28도 기울었습니다"처럼 설명할 수 있고 10도/30도가 의도대로 갈린다.
STRAIGHT_STROKE_MAX_TILT_DEG = 15.0
# 표준 획이 이 각도 이내로 수평/수직이면 "곧게 그어야 하는 획"으로 본다.
STRAIGHT_STROKE_AXIS_TOL_DEG = 20.0

# 성분 비율: 자모별 (면적 / 종횡비 / 중심 위치) 편차의 허용치.
# 참고한 방식(AI-WritingCorrection)은 면적·종횡비만 ±50%로 봤는데, 그 정도면
# 어지간히 이상하지 않으면 다 통과한다. 우리는 기대 상자가 있어 **중심 위치**까지
# 볼 수 있으므로 세 축을 함께 본다.
#
# ⚠️ 2026-09-01 완화. 종전 값(면적 0.30 / 종횡비 0.30 / 중심 0.15)은 **그림자대로
# 따라 써도 빨간 박스가 떴다**(사용자 실측). 면적은 2차원이라 ±30%가 한 변으로는
# ±14%밖에 안 되는데, 손으로 쓰면 그 정도는 늘 흔들린다. 세 축을 OR로 묶어 "하나라도
# 걸리면 빨강"이니 축마다 조금씩 빠듯한 것이 곱해져 실질 통과율이 훨씬 낮아졌다.
# 한 변 기준 ±20% 정도까지는 정상 필기로 보도록 넓힌다.
# 2026-09-01 두 번째 완화(사용자 요청) — 0.45/0.45/0.22에서 한 단계 더 넓혔다.
# 합성 필기로는 이미 안 걸렸지만 실제 손글씨에서는 아직 빡빡했다. 합성 노이즈가
# 사람 손의 흔들림을 과소평가한다는 뜻이므로, 실사용 쪽 신고를 기준으로 삼는다.
BALANCE_TOL_AREA = 0.55      # 기대 면적 대비 ±55% (≈ 한 변 ±25%)
BALANCE_TOL_ASPECT = 0.55    # 기대 종횡비 대비 ±55%
BALANCE_TOL_CENTER = 0.26    # 기대 중심에서 글자 크기의 26%

# 중성(모음)만 한 번 더 완화한다(사용자 요청 2026-09-01).
# 모음은 ㅏ·ㅓ·ㅗ처럼 **획이 성글어** 상자 안이 거의 비어 있다. 그래서 세로획을
# 조금만 길게 빼거나 곁가지를 짧게 붙여도 상자 넓이가 크게 출렁이는데, 정작 글씨는
# 멀쩡해 보인다. 자음은 획이 상자를 촘촘히 채워 이만큼 흔들리지 않는다.
BALANCE_TOL_MEDIAL_RELIEF = 1.3     # 중성에 한해 허용치 ×1.3
_MEDIAL_BLOCK = 1                   # 0=초성 1=중성 2=종성

# 크기(절대) — **표준 자형 대비** 얼마나 크게 썼나. 1.0이면 표준과 같은 크기다.
# 참고한 방식은 "칸 대비 50~85%"라는 고정 비율을 썼는데, 자형마다 차지하는 면적이
# 달라(각 0.38 / 낱자 ㄱ 0.09) 우리 템플릿에는 그대로 못 쓴다. 그래서 기준을
# template_ink_fill()로 자형마다 잡고, 그 대비 배율로 본다.
# 2026-09-01 완화 — 성분 비율과 같은 이유다. 글자를 조금 크게/작게 쓰는 건 습관이지
# 잘못이 아니다. 한눈에 "너무 크다/작다"고 보일 때만 잡는다.
SIZE_REL_MIN_OK, SIZE_REL_MAX_OK = 0.70, 1.40
SIZE_REL_ZERO_LOW, SIZE_REL_ZERO_HIGH = 0.40, 1.90  # 여기서 0점

# 크기(상대) — 가이드 박스를 못 받았을 때만 쓰는 폴백. 글자가 2개 이상이어야 의미가 있다.
SIZE_PENALTY_COEFF, SIZE_PENALTY_MAX = 0.8, 50.0        # 크기 편차(%) 1당 감점 / 상한
SPACING_PENALTY_COEFF, SPACING_PENALTY_MAX = 0.3, 30.0  # 자간 편차(px) 1당 감점 / 상한



def _clamp_score(v: float) -> float:
    return max(0.0, min(100.0, v))


def size_score_from_fill(size_rel: Optional[float]) -> Optional[float]:
    """표준 자형 대비 크기 배율 → 크기 점수. 못 재면 None.

    1.0이면 표준과 같은 크기다. 적정 구간(0.75~1.30) 안이면 만점이고, 벗어난 쪽으로
    선형 감점해 0.40/1.90에서 0점. **한 글자만 쓰는 연습에서 크기를 채점할 수 있는
    유일한 기준**이다 — 종전의 '세션 중앙값 대비'는 글자가 하나면 중앙값이 자기
    자신이라 편차가 늘 0, 즉 항상 만점이었다.
    """
    if size_rel is None:
        return None
    if SIZE_REL_MIN_OK <= size_rel <= SIZE_REL_MAX_OK:
        return 100.0
    if size_rel < SIZE_REL_MIN_OK:
        span = SIZE_REL_MIN_OK - SIZE_REL_ZERO_LOW
        return _clamp_score(100.0 * (size_rel - SIZE_REL_ZERO_LOW) / span)
    span = SIZE_REL_ZERO_HIGH - SIZE_REL_MAX_OK
    return _clamp_score(100.0 * (SIZE_REL_ZERO_HIGH - size_rel) / span)


def canvas_item_scores(size_deviation_pct: Optional[float] = None,
                       spacing_deviation_px: Optional[float] = None,
                       stroke_order_result: Optional[Dict] = None,
                       direction_result: Optional[Dict] = None,
                       tilt_result: Optional[Dict] = None,
                       balance_result: Optional[Dict] = None,
                       size_fill_ratio: Optional[float] = None,
                       ) -> Dict[str, Optional[float]]:
    """글자 하나의 항목별 점수(0~100). **측정 불가한 항목은 None**.

    None의 의미가 중요하다 — 0점이 아니라 "재지 않았다"이고, 종합 점수의 분모에서도
    빠진다. 0건 오류로 보고 만점을 주면 "재지도 않은 지표로 칭찬"이 된다(§4-1).
      · 획순·획방향·성분비율 → 목표 글자(target_text)를 알 때만 잴 수 있다
      · 성분비율            → 낱자(ㄱ·ㅏ)는 성분이 하나뿐이라 애초에 성립하지 않는다
      · 크기                → 가이드 박스가 있으면 절대 기준, 없으면 상대 폴백
      · 자간                → 글자가 2개 이상일 때만

    세션 종합 점수(analyze_canvas_writing)와 대시보드 항목 집계가 **같은 기준**을
    쓰도록 하는 단일 출처다.
    """
    order: Optional[float] = None
    if stroke_order_result:
        n_err = stroke_order_result.get("error_count", 0)
        order = _clamp_score(100.0 - n_err * ORDER_PENALTY_PER_ERROR)

    direction: Optional[float] = None
    if direction_result and direction_result.get("checked", 0) > 0:
        direction = _clamp_score(direction_result["score"])

    tilt: Optional[float] = None
    if tilt_result and tilt_result.get("checked", 0) > 0:
        tilt = _clamp_score(tilt_result["score"])

    balance: Optional[float] = None
    if balance_result and balance_result.get("components"):
        balance = _clamp_score(balance_result["score"])

    # 크기: 가이드 박스 기준이 정본. 못 받았을 때만 상대 편차로 폴백한다.
    size = size_score_from_fill(size_fill_ratio)
    if size is None and size_deviation_pct is not None:
        size = _clamp_score(100.0 - min(SIZE_PENALTY_MAX,
                                        abs(size_deviation_pct) * SIZE_PENALTY_COEFF))

    spacing: Optional[float] = None
    if spacing_deviation_px is not None:
        spacing = _clamp_score(100.0 - min(SPACING_PENALTY_MAX,
                                           abs(spacing_deviation_px) * SPACING_PENALTY_COEFF))

    return {
        ITEM_ORDER: order,
        ITEM_DIRECTION: direction,
        ITEM_TILT: tilt,
        ITEM_BALANCE: balance,
        ITEM_SIZE: size,
        ITEM_SPACING: spacing,
    }


def overall_from_items(items: Dict[str, Optional[float]]) -> Optional[int]:
    """항목 점수 → 종합 점수(가중 평균). 잰 항목이 하나도 없으면 None.

    종전에는 감점을 전부 더해 100에서 뺐는데(이론상 120점까지 깎임), 항목이 늘면
    한 항목만 나빠도 0점으로 내려앉는다. 가중 평균은 항목 수가 달라도(낱자 3개 /
    한 글자 4개 / 문장 5개) 같은 잣대로 비교된다.
    """
    num = den = 0.0
    for name, score in items.items():
        if score is None:
            continue
        w = ITEM_WEIGHTS.get(name, 1.0)
        num += score * w
        den += w
    return round(num / den) if den else None


def _path_descriptor(path: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    """path의 (중심x, 중심y, 너비, 높이)."""
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return cx, cy, max(xs) - min(xs), max(ys) - min(ys)


def _path_ink_box(path: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    """path가 실제로 잉크를 남기는 범위 (x0, y0, x1, y1)."""
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    return min(xs), min(ys), max(xs), max(ys)


def _union_box(boxes: List[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _renormalize(box: Tuple[float, float, float, float],
                 frame: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """box를 frame이 [0,1]x[0,1]이 되도록 다시 편다."""
    fx0, fy0, fx1, fy1 = frame
    fw, fh = max(fx1 - fx0, 1e-6), max(fy1 - fy0, 1e-6)
    return ((box[0] - fx0) / fw, (box[1] - fy0) / fh,
            (box[2] - fx0) / fw, (box[3] - fy0) / fh)


def _renormalize_point(pt: Tuple[float, float],
                       frame: Tuple[float, float, float, float]) -> Tuple[float, float]:
    fx0, fy0, fx1, fy1 = frame
    fw, fh = max(fx1 - fx0, 1e-6), max(fy1 - fy0, 1e-6)
    return (pt[0] - fx0) / fw, (pt[1] - fy0) / fh


def template_ink_fill(target_char: str) -> Optional[float]:
    """표준 자형이 **가이드 상자 안에서 차지하는 면적 비율**.

    크기 채점의 기준점이다. 자형마다 다르다 — '각'은 0.38, 낱자 'ㄱ'은 0.09
    수준이라 고정 임계값(참고한 방식의 '칸 대비 50~85%')을 그대로 쓸 수 없다.
    표준 자형 자체를 기준으로 삼아야 "표준만큼 썼는가"를 물을 수 있다.
    """
    layout = _layout_for_char(target_char)
    if not layout:
        return None
    x0, y0, x1, y1 = _union_box([_path_ink_box(p) for _, paths in layout for p in paths])
    area = (x1 - x0) * (y1 - y0)
    return area if area > 0 else None


def _descriptor_distance(a: Tuple[float, float, float, float],
                          b: Tuple[float, float, float, float]) -> float:
    pos_dist   = math.dist(a[:2], b[:2])
    shape_dist = math.dist(a[2:], b[2:])
    return pos_dist + SHAPE_WEIGHT * shape_dist


def _layout_for_char(target_char: str) -> List[Tuple[str, List[Tuple[float, float]]]]:
    """목표 글자(완성형 음절 또는 낱개 자모)의 자모별 배치.

    완성형 음절은 _syllable_layout로 초성/중성/종성이 서로 자리를 나눠 쓰지만,
    낱개 자모(ㄱ·ㅏ 등)는 나눠 쓸 다른 자모가 없으므로 화면 전체를 혼자 쓰는
    _single_jamo_layout을 쓴다. 둘 다 아니면(한글이 아니거나 조합형이 아니면) 빈 리스트.
    """
    decomposed = decompose_syllable(target_char)
    if decomposed is not None:
        cho, jung, jong = decomposed
        return _syllable_layout(cho, jung, jong)
    if target_char in CHOSUNG:
        return _single_jamo_layout(target_char, is_vowel=False)
    if target_char in JUNGSUNG:
        return _single_jamo_layout(target_char, is_vowel=True)
    return []


def _path_direction(path: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """획의 시작→끝 단위 벡터. 닫힌 획(ㅇ)이면 None — 방향을 논할 수 없다."""
    if len(path) < 2:
        return None
    (x0, y0), (x1, y1) = path[0], path[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    span = max(max(p[0] for p in path) - min(p[0] for p in path),
               max(p[1] for p in path) - min(p[1] for p in path))
    if span <= 0 or length < DIRECTION_CLOSED_RATIO * span:
        return None          # 시작점과 끝점이 거의 같다 = 원형 획
    return dx / length, dy / length


def _stroke_direction(stroke: Dict) -> Optional[Tuple[float, float]]:
    """사용자 획의 시작→끝 단위 벡터. 템플릿과 같은 규칙으로 잰다."""
    pts = stroke["points"]
    return _path_direction([(p["x"], p["y"]) for p in pts])


def _canonical_stroke_specs(
    target_char: str,
) -> List[Tuple[int, str, Tuple[float, float, float, float], Optional[Tuple[float, float]]]]:
    """기대 획을 (자모블록 번호, 자모라벨, (cx,cy,w,h), 방향벡터)로 반환 (정규화 [0,1] 공간).

    synthetic_stroke_generator.py의 기하 템플릿을 그대로 재사용한다.

    **자모블록 번호가 왜 필요한가**: '각'처럼 초성과 종성이 같은 자모('ㄱ')면 라벨만으로는
    어느 쪽 획인지 구분되지 않는다. 성분 비율 채점은 획을 자모별로 묶어야 하므로
    라벨이 아니라 **자리(블록)** 로 묶는다.
    """
    layout = _layout_for_char(target_char)
    if not layout:
        return []

    # ⚠️ 사용자 획은 **자기 잉크 bbox 기준으로 [0,1]에 펴져** 들어온다
    # (_actual_stroke_centroid). 반면 템플릿은 가이드 상자 기준이라 잉크가 0.15~0.78
    # 언저리만 쓴다. 프레임을 안 맞추면 완벽하게 쓴 글씨도 다르게 보인다.
    #
    # 특히 **획이 하나뿐인 낱자**(ㄱ·ㄴ·ㅇ·ㅡ·ㅣ)에서 치명적이었다: 획이 하나면
    # 정규화 후 폭·높이가 정의상 1.0이 되는데 템플릿은 0.42/0.31이라 모양 거리가
    # 1.4까지 벌어져 MATCH_QUALITY_THRESHOLD(0.6)를 넘고, "목표 글자와 많이 달라
    # 보입니다"로 오판했다. 자음 탭 첫 두 글자(ㄱ·ㄴ)가 여기 해당했다.
    frame = _union_box([_path_ink_box(p) for _, paths in layout for p in paths])

    specs = []
    for block_idx, (jamo_label, paths) in enumerate(layout):
        for path in paths:
            normed = [_renormalize_point(pt, frame) for pt in path]
            specs.append((block_idx, jamo_label,
                          _path_descriptor(normed), _path_direction(normed)))
    return specs


def _canonical_stroke_points(target_char: str) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    """기대 획 순서를 (자모라벨, (cx,cy,w,h))로 반환 — 획순 판정이 쓰는 축약형."""
    return [(label, desc) for _, label, desc, _ in _canonical_stroke_specs(target_char)]


def _match_strokes(strokes: List[Dict], bbox: Dict, target_char: str) -> Dict:
    """사용자 획을 표준 획에 그리디 매칭한다.

    획순·획방향·성분비율 **세 항목이 모두 이 한 번의 매칭 결과**를 쓴다. 항목마다
    따로 매칭하면 같은 획이 항목별로 다른 자모에 붙어 판정이 서로 어긋난다.

    참고: 이 매칭이 우리 방식의 핵심이다. 획 개수로 순서대로 잘라 자모를 나누면
    (AI-WritingCorrection 방식) 획순이 틀리는 순간 자모 분해가 통째로 무너지지만,
    기하 매칭은 순서가 틀려도 각 획이 어느 자모 자리에 있는지는 그대로 알아낸다.
    """
    specs = _canonical_stroke_specs(target_char)
    if not specs or not strokes:
        return {"specs": specs, "matched": [], "dists": []}

    actual = [_actual_stroke_centroid(s, bbox) for s in strokes]
    remaining = list(range(len(specs)))
    matched: List[int] = []
    dists: List[float] = []
    for ac in actual:
        if not remaining:
            matched.append(-1)      # 표준보다 많이 그린 여분 획
            continue
        best = min(remaining, key=lambda ci: _descriptor_distance(ac, specs[ci][2]))
        matched.append(best)
        dists.append(_descriptor_distance(ac, specs[best][2]))
        remaining.remove(best)
    return {"specs": specs, "matched": matched, "dists": dists}


def _actual_stroke_centroid(stroke: Dict, bbox: Dict) -> Tuple[float, float, float, float]:
    """실제 stroke의 (중심x,중심y,너비,높이)를 글자 bounding box 기준 [0,1] 정규화 좌표로 변환."""
    xs = [p["x"] for p in stroke["points"]]
    ys = [p["y"] for p in stroke["points"]]
    bw, bh = bbox["width"] or 1.0, bbox["height"] or 1.0
    cx = (sum(xs) / len(xs) - bbox["x"]) / bw
    cy = (sum(ys) / len(ys) - bbox["y"]) / bh
    w = (max(xs) - min(xs)) / bw
    h = (max(ys) - min(ys)) / bh
    return (cx, cy, w, h)


def _acceptable_orders(target_char: str) -> List[Tuple[List[int], frozenset]]:
    """목표 글자에 대해 감점 없이 허용되는 전체 획 순서 목록.

    각 항목은 (draw-position별 기대 canonical 인덱스 시퀀스, 사용된 대안 자모 집합).
    표준(identity)은 항상 첫 번째로 포함하며, 대안이 있는 자모는 표준+대안 후보를
    갖고 자모 블록별 데카르트 곱으로 전체 순서를 만든다. 대안이 없으면 표준 하나뿐.
    """
    layout = _layout_for_char(target_char)
    if not layout:
        return [([], frozenset())]

    # 자모 블록별 canonical 인덱스 범위
    blocks: List[Tuple[str, List[int]]] = []
    idx = 0
    for jamo_label, paths in layout:
        n = len(paths)
        blocks.append((jamo_label, list(range(idx, idx + n))))
        idx += n

    results: List[Tuple[List[int], frozenset]] = [([], frozenset())]
    for jamo, indices in blocks:
        # 이 블록의 후보: 표준(첫 번째) + 유효한 대안 순열
        block_options: List[Tuple[List[int], object]] = [(indices, None)]
        for perm in ALTERNATIVE_STROKE_ORDERS.get(jamo, []):
            if len(perm) == len(indices):
                block_options.append(([indices[p] for p in perm], jamo))
        results = [
            (seq + reordered, alts | ({alt} if alt else frozenset()))
            for seq, alts in results
            for reordered, alt in block_options
        ]
    return results


def _order_mismatches(matched: List[int], target: List[int]) -> int:
    """draw-position별 매칭 canonical 인덱스가 기대 순서와 다른 개수.
    target 길이를 넘는 draw 위치(여분 획)는 무조건 불일치로 센다(기존 동작 보존)."""
    total = 0
    for i, m in enumerate(matched):
        t = target[i] if i < len(target) else None
        if m != t:
            total += 1
    return total


def analyze_stroke_order_by_position(strokes: List[Dict], bbox: Dict, target_char: str) -> Dict:
    """
    ML 분류 모델 없이 순서 오류를 감지하는 위치 기반 획순 분석.

    아이디어: "이 획이 무슨 모양인지"를 처음부터 분류할 필요 없이(그건 실제로 학습
    데이터가 필요한 문제), 목표 글자를 이미 아는 상황(제시형 UI)이라는 점을 이용해
    "N번째로 그린 획이 표준상 기대되는 N번째 위치에 있는가"만 비교한다 — 순수 기하
    비교라 학습 데이터가 필요 없다. 타임스탬프(그린 순서)는 strokes 리스트 순서
    그대로 사용한다(stroke_grouping.py가 이미 시간순 정렬해서 넘겨줌).
    """
    canonical = _canonical_stroke_points(target_char)
    if not canonical or not strokes:
        return {
            "expected_sequence": [c[0] for c in canonical],
            "actual_sequence": [],
            "error_count": 0,
            "used_alternative_order": False,
            "notes": [],
            "corrections": [],
        }

    # 사용자가 그린 순서대로, 아직 안 쓰인 정답 획 중 위치가 가장 가까운 것에 그리디 매칭
    match = _match_strokes(strokes, bbox, target_char)
    matched_indices = match["matched"]
    matched_dists = match["dists"]

    # ── 애초에 목표 글자를 쓴 게 맞는지 먼저 확인 ──────────────────────────
    # 목표와 전혀 다른 글자(혹은 낙서)를 썼다면, 그걸 억지로 목표 템플릿에 끼워
    # 맞춰서 "몇 번째 획이 틀렸다"는 세부 피드백을 주는 건 오히려 혼란만 줌.
    # (1) 매칭된 획들의 평균 위치·모양 오차가 크거나 (2) 획 수 자체가 크게
    # 다르면 "다른 글자로 보임"으로 판단하고 세부 피드백은 생략한다.
    avg_match_dist = sum(matched_dists) / len(matched_dists) if matched_dists else 1.0
    count_ratio = len(strokes) / len(canonical) if canonical else 1.0
    likely_wrong_character = (
        avg_match_dist > MATCH_QUALITY_THRESHOLD
        or count_ratio > COUNT_MISMATCH_RATIO_THRESHOLD
        or count_ratio < 1.0 / COUNT_MISMATCH_RATIO_THRESHOLD
    )

    if likely_wrong_character:
        return {
            "expected_sequence": [c[0] for c in canonical],
            "actual_sequence": [canonical[m][0] if m != -1 else "unknown" for m in matched_indices],
            "error_count": len(canonical),
            "likely_wrong_character": True,
            "used_alternative_order": False,
            "notes": [],
            "corrections": [f"목표 글자('{target_char}')와 많이 달라 보입니다. 다시 확인해주세요."],
        }

    # 감점 없이 허용되는 순서(표준 + 논쟁 자모의 대안 필순) 중 오류가 가장 적은 것을 채택.
    # best[i] = i번째로 그린 획이 있어야 할 canonical 인덱스. matched_indices[i]가 이와
    # 다르면 순서 오류. _acceptable_orders는 표준을 먼저 넣으므로 동점이면 표준을 택한다.
    acceptable = _acceptable_orders(target_char)
    best_seq, best_alts = min(acceptable, key=lambda t: _order_mismatches(matched_indices, t[0]))

    error_count = _order_mismatches(matched_indices, best_seq)
    corrections: List[str] = []
    # 자모 블록별 오류 수 — 성분 박스가 "이 성분에서 순서가 틀렸나"를 이걸로 본다.
    order_per_block: Dict[int, int] = {}
    specs = _canonical_stroke_specs(target_char)
    for i, m in enumerate(matched_indices):
        expected = best_seq[i] if i < len(best_seq) else None
        if m not in (expected, -1) and 0 <= m < len(specs):
            blk = specs[m][0]
            order_per_block[blk] = order_per_block.get(blk, 0) + 1
        if m not in (expected, -1):
            corrections.append(
                f"{i + 1}번째로 그린 획은 표준 순서상 {m + 1}번째({canonical[m][0]}) "
                f"위치에 그려야 합니다."
            )
    if len(strokes) != len(canonical):
        corrections.append(
            f"획 수가 {'부족합니다' if len(strokes) < len(canonical) else '많습니다'} "
            f"(작성 {len(strokes)}개 / 표준 {len(canonical)}개)"
        )

    notes = [standard_order_note(jamo) for jamo in sorted(best_alts)]

    return {
        "expected_sequence": [c[0] for c in canonical],
        "actual_sequence": [canonical[m][0] if m != -1 else "unknown" for m in matched_indices],
        "error_count": error_count,
        "likely_wrong_character": False,
        "used_alternative_order": bool(best_alts),
        "notes": notes,
        "corrections": corrections,
        "per_block": order_per_block,
    }


def analyze_stroke_direction(strokes: List[Dict], bbox: Dict,
                             target_char: str) -> Optional[Dict]:
    """각 획을 **올바른 방향으로 그었는가**.

    표준 획 템플릿은 점 순서를 가진 경로라 방향 정보를 이미 담고 있다 — 새 데이터가
    필요 없다. 사용자 획의 시작→끝 벡터와 매칭된 표준 획의 벡터가 이루는 각도를 본다.

      135° 미만  → 정상
      135° 이상  → 역방향(오류 1건)  예: 'ㄱ'을 아래에서 위로 그은 경우

    **기울기는 여기서 안 본다**(사용자 결정 2026-09-01). 30도 비스듬해도 진행 방향이
    맞으면 통과다 — 곧게 그어야 하는 획의 기울기는 analyze_stroke_tilt가 따로 15도
    기준으로 잡는다. 한 항목에 섞으면 두 가지를 구분해 설명할 수 없다.

    ㅇ처럼 시작점과 끝점이 겹치는 닫힌 획은 방향을 논할 수 없어 세지 않는다.
    잴 수 있는 획이 하나도 없으면 None(미측정)이다.
    """
    match = _match_strokes(strokes, bbox, target_char)
    specs, matched = match["specs"], match["matched"]
    if not specs or not matched:
        return None

    checked = 0
    errors = 0.0
    corrections: List[str] = []
    per_block: Dict[int, int] = {}   # 자모 블록별 오류 수 — 성분 박스 색이 이걸 쓴다
    for i, m in enumerate(matched):
        if m == -1:
            continue                      # 표준에 없는 여분 획 — 획순 쪽에서 지적한다
        expected_dir = specs[m][3]
        if expected_dir is None:
            continue                      # 닫힌 획(ㅇ)
        actual_dir = _stroke_direction(strokes[i])
        if actual_dir is None:
            continue                      # 사용자가 제자리에 점을 찍은 경우 등
        checked += 1
        cos = actual_dir[0] * expected_dir[0] + actual_dir[1] * expected_dir[1]
        deg = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
        if deg >= DIRECTION_REVERSED_DEG:
            errors += 1.0
            per_block[specs[m][0]] = per_block.get(specs[m][0], 0) + 1
            corrections.append(
                f"{i + 1}번째 획('{specs[m][1]}')을 반대 방향으로 그었습니다.")

    if checked == 0:
        return None
    return {
        "checked": checked,
        "error_count": round(errors, 1),
        "score": 100.0 * (1.0 - errors / checked),
        "corrections": corrections,
        "per_block": per_block,
    }


def _axis_angle_deg(vec: Tuple[float, float]) -> float:
    """벡터의 방향각(0~180). 방향(위/아래)은 무시하고 **기울기만** 본다 —
    같은 세로선을 위에서 아래로 긋든 반대로 긋든 기울기는 같다."""
    deg = math.degrees(math.atan2(vec[1], vec[0])) % 180.0
    return deg


def _is_straight_axis(vec: Tuple[float, float]) -> bool:
    """표준 획이 '곧게 그어야 하는 획'(수평 또는 수직)인가."""
    a = _axis_angle_deg(vec)
    return (a <= STRAIGHT_STROKE_AXIS_TOL_DEG
            or a >= 180.0 - STRAIGHT_STROKE_AXIS_TOL_DEG
            or abs(a - 90.0) <= STRAIGHT_STROKE_AXIS_TOL_DEG)


def analyze_stroke_tilt(strokes: List[Dict], bbox: Dict,
                        target_char: str) -> Optional[Dict]:
    """**곧게 그어야 하는 획을 곧게 그었는가** — 기울기 판정 (2026-09-01 신설).

    'ㅣ'는 일자로, 'ㅡ'는 수평으로 써야 한다. 그런데 이런 자모는 폭(또는 높이)이
    0에 가까워서 **성분비율의 종횡비로 재면 안 된다** — 10도만 기울어도 비율이
    442배로 튀어 과잉 판정이 나고, 반대로 몇 도 기울었는지는 설명할 수 없다
    (2026-09-01 실측). 그래서 표준 획이 수평·수직인 것만 골라 **각도를 직접** 잰다.

    표준 각도에서 STRAIGHT_STROKE_MAX_TILT_DEG(15도)를 넘게 어긋나면 오류.
    사선 획(ㅅ·ㅈ의 삐침 등)은 애초에 곧게 그을 획이 아니라 대상에서 뺀다.
    """
    match = _match_strokes(strokes, bbox, target_char)
    specs, matched = match["specs"], match["matched"]
    if not specs or not matched:
        return None

    checked = 0
    errors = 0
    corrections: List[str] = []
    per_block: Dict[int, int] = {}
    worst = 0.0
    for i, m in enumerate(matched):
        if m == -1:
            continue
        expected_dir = specs[m][3]
        if expected_dir is None or not _is_straight_axis(expected_dir):
            continue                      # 닫힌 획(ㅇ)이거나 원래 사선인 획
        actual_dir = _stroke_direction(strokes[i])
        if actual_dir is None:
            continue
        checked += 1
        # 0~180 축 각도끼리 비교하되 179도와 1도가 2도 차이가 되도록 감싼다.
        diff = abs(_axis_angle_deg(actual_dir) - _axis_angle_deg(expected_dir))
        tilt = min(diff, 180.0 - diff)
        worst = max(worst, tilt)
        if tilt > STRAIGHT_STROKE_MAX_TILT_DEG:
            errors += 1
            per_block[specs[m][0]] = per_block.get(specs[m][0], 0) + 1
            corrections.append(
                f"{i + 1}번째 획('{specs[m][1]}')이 {tilt:.0f}도 기울었습니다. "
                f"곧게 그어보세요.")

    if checked == 0:
        return None
    return {
        "checked": checked,
        "error_count": errors,
        "max_tilt_deg": round(worst, 1),
        "score": 100.0 * (1.0 - errors / checked),
        "corrections": corrections,
        "per_block": per_block,
    }


def _normalized_group_box(strokes: List[Dict], bbox: Dict) -> Tuple[float, float, float, float]:
    """획 묶음의 bbox를 글자 bounding box 기준 [0,1] 정규화 좌표로."""
    xs = [p["x"] for s in strokes for p in s["points"]]
    ys = [p["y"] for s in strokes for p in s["points"]]
    bw, bh = bbox["width"] or 1.0, bbox["height"] or 1.0
    return ((min(xs) - bbox["x"]) / bw, (min(ys) - bbox["y"]) / bh,
            (max(xs) - bbox["x"]) / bw, (max(ys) - bbox["y"]) / bh)


# 종횡비 비교를 포기하는 기준. 기대 상자의 짧은 변이 이보다 작으면 'ㅣ·ㅡ'처럼
# 선에 가까운 자모라, 종횡비가 조금만 기울어도 폭발한다 — 기울기 항목에 맡긴다.
_ASPECT_MIN_SIDE = 0.08


def _pixel_group_box(strokes: List[Dict]) -> Dict[str, float]:
    """획 묶음의 실제 캔버스 좌표 bbox — 화면에 성분 박스를 그리는 데 쓴다."""
    xs = [p["x"] for st in strokes for p in st["points"]]
    ys = [p["y"] for st in strokes for p in st["points"]]
    return {"x": round(min(xs), 1), "y": round(min(ys), 1),
            "width": round(max(xs) - min(xs), 1), "height": round(max(ys) - min(ys), 1)}


def _box_metrics(box: Tuple[float, float, float, float]):
    """(면적, 종횡비, 중심) — 0 나눗셈을 막기 위해 폭·높이에 하한을 둔다.
    'ㅡ'처럼 높이가 거의 0인 자모가 실제로 있다."""
    x0, y0, x1, y1 = box
    w, h = max(x1 - x0, 1e-3), max(y1 - y0, 1e-3)
    return w * h, w / h, ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def analyze_component_balance(strokes: List[Dict], bbox: Dict,
                              target_char: str) -> Optional[Dict]:
    """초성·중성·종성의 **크기와 자리 균형**.

    글자 하나를 통째로 보는 대신 자모별로 나눠 "받침만 너무 크다", "초성이 가운데로
    쏠렸다"를 짚는다. 성분이 하나뿐인 낱자(ㄱ·ㅏ)는 '성분 간' 비율이 성립하지 않아
    None(미측정)이다.

    자모별로 세 축을 본다 — **면적**(글자에서 차지하는 몫), **종횡비**(납작한지
    길쭉한지), **중심 위치**(제자리에 있는지). 참고한 방식(AI-WritingCorrection)은
    앞의 둘만 ±50%로 봤지만, 우리는 기대 상자를 갖고 있어 위치까지 볼 수 있다.

    획을 자모에 붙이는 일은 _match_strokes가 기하로 하므로 **획순이 틀려도 이 점수는
    살아 있다** — 순서 오류와 비율 오류가 서로를 오염시키지 않는다.
    """
    if decompose_syllable(target_char) is None:
        return None                        # 낱자 — 나눌 성분이 없다
    layout = _layout_for_char(target_char)
    if len(layout) < 2:
        return None

    match = _match_strokes(strokes, bbox, target_char)
    specs, matched = match["specs"], match["matched"]
    if not specs or not matched:
        return None

    by_block: Dict[int, List[Dict]] = {}
    for i, m in enumerate(matched):
        if m == -1:
            continue
        by_block.setdefault(specs[m][0], []).append(strokes[i])

    # ⚠️ 좌표 프레임을 맞춘다. 사용자 획은 **자기 잉크 bbox 기준으로 [0,1]에 펴져**
    # 들어오므로(_normalized_group_box), 기대값도 **선언 상자가 아니라 실제 잉크**로
    # 잡고 그 합집합을 기준으로 다시 정규화한다. 선언 상자를 그대로 쓰면 템플릿이
    # 상자를 꽉 채우지 않는 만큼(ㄱ은 상자의 절반쯤만 쓴다) 통째로 어긋난다.
    #
    # 이렇게 하면 성분 비율이 **글자를 크게 썼든 작게 썼든 동일**해진다 — 의도한
    # 성질이다. 절대 크기는 '크기' 항목이 가이드 박스 대비로 따로 본다.
    # 기대 영역 = 배치 정본(jamo_boxes)이 정하는 자리. 2026-09-01부터 그 값이
    # **실측 명조 글리프**에서 나오고, 합성 획도 그 상자를 꽉 채우므로 '상자 = 잉크'다.
    # 종전에는 합성 획의 잉크 범위를 따로 쟀는데 상자와 최대 57% 어긋나 있었다.
    ink = [(jamo, _union_box([_path_ink_box(p) for p in paths])) for jamo, paths in layout]
    frame = _union_box([b for _, b in ink])
    expected = [(jamo, _renormalize(b, frame)) for jamo, b in ink]

    # ⚠️ 사용자 획을 **자기 잉크 상자**로 정규화하면, 한 성분만 커져도 상자 전체가
    # 커져서 **멀쩡한 나머지 성분까지 작아 보인다**(2026-09-01 실측: 받침만 2배로
    # 키웠는데 초성 10.9점·중성 35.4점). 그러면 "하나라도 오류면 빨강" 규칙에서
    # 잘못 쓰지도 않은 성분이 전부 빨개진다.
    #
    # 그래서 **가장 표준에 가까운 성분을 기준으로 배율을 맞춘다**. 성분 비율은 원래
    # 성분들 사이의 상대 관계이므로, 전체 배율은 '크기' 항목이 따로 볼 몫이다.
    act_raw = {}
    for block_idx, _ in enumerate(expected):
        grp = by_block.get(block_idx)
        if grp:
            act_raw[block_idx] = _normalized_group_box(grp, bbox)
    scale, shift = 1.0, (0.0, 0.0)
    if act_raw:
        ratios, dxs, dys = [], [], []
        for block_idx, act_box in act_raw.items():
            exp_a, _, exp_c = _box_metrics(expected[block_idx][1])
            act_a, _, act_c = _box_metrics(act_box)
            ratios.append(act_a / exp_a if exp_a > 0 else 1.0)
            dxs.append(act_c[0] - exp_c[0])
            dys.append(act_c[1] - exp_c[1])
        # 중앙값을 쓰는 이유: 한 성분만 튀어도 중앙값은 정상 성분 쪽에 남으므로,
        # 튄 성분만 편차로 드러나고 나머지는 상쇄된다.
        med = lambda v: sorted(v)[len(v) // 2]
        scale = med(ratios) or 1.0
        # 위치도 같이 상쇄한다. 받침이 커지면 글자 상자가 아래로 늘어나 **멀쩡한
        # 초성의 상대 위치까지 위로 밀린다**(2026-09-01 실측: 초성 중심 편차 1.50).
        shift = (med(dxs), med(dys))

    components: List[Dict] = []
    corrections: List[str] = []
    for block_idx, (jamo, exp_box) in enumerate(expected):
        group = by_block.get(block_idx)
        if not group:
            continue        # 이 자모를 아예 안 썼다 — 획수/획순 쪽에서 이미 지적된다
        act_box = _normalized_group_box(group, bbox)
        exp_area, exp_aspect, exp_center = _box_metrics(exp_box)
        act_area, act_aspect, act_center = _box_metrics(act_box)
        act_area /= scale        # 전체 배율 상쇄 — 성분 간 '비율'만 남긴다
        act_center = (act_center[0] - shift[0], act_center[1] - shift[1])

        # 중성은 획이 성글어 상자가 잘 출렁인다 — 허용치를 한 번 더 넓혀 준다.
        relief = BALANCE_TOL_MEDIAL_RELIEF if block_idx == _MEDIAL_BLOCK else 1.0
        tol_area = BALANCE_TOL_AREA * relief
        tol_aspect = BALANCE_TOL_ASPECT * relief
        tol_center = BALANCE_TOL_CENTER * relief

        center_dev = min(1.0, math.dist(act_center, exp_center) / tol_center)

        # ⚠️ 한쪽 변이 0에 가까운 자모(ㅣ·ㅡ)는 **넓이도 종횡비도 쓰면 안 된다.**
        # 종횡비: 폭이 거의 0이라 10도만 기울어도 비율이 수백 배로 튄다(실측 442배).
        # 넓이:   높이가 거의 0이라 손이 조금만 떨려도 넓이가 몇 배가 된다
        #         (2026-09-01 실측: '글'의 ㅡ가 아주 정갈한 필기에서도 30번 중 16번
        #          '너무 큼'으로 빨개졌다). 종전에는 종횡비만 건너뛰고 넓이는 그대로
        #         비교해서 이 오판이 남아 있었다.
        # 대신 **긴 축의 길이**를 본다 — ㅡ는 가로 길이, ㅣ는 세로 길이. 짧게 그은
        # 것은 그대로 잡히면서 얇은 축의 떨림에는 흔들리지 않는다.
        # 곧게 그었는지는 analyze_stroke_tilt가 각도로 따로 본다.
        ex0, ey0, ex1, ey1 = exp_box
        degenerate = min(ex1 - ex0, ey1 - ey0) < _ASPECT_MIN_SIDE
        if degenerate:
            aspect_dev = 0.0
            horizontal = (ex1 - ex0) >= (ey1 - ey0)
            exp_len = (ex1 - ex0) if horizontal else (ey1 - ey0)
            ax0, ay0, ax1, ay1 = act_box
            act_len = ((ax1 - ax0) if horizontal else (ay1 - ay0)) / math.sqrt(scale)
            # 허용치는 **넓이 기준 숫자**라 길이에 그대로 쓰면 두 배로 헐거워진다
            # (±45% 넓이 = 한 변 ±20%). 길이에는 제곱근으로 환산해서 쓴다.
            tol_len = math.sqrt(1.0 + tol_area) - 1.0
            area_dev = min(1.0, abs(act_len - exp_len) / max(exp_len, 1e-3) / tol_len)
            # 아래 사유 문구가 act_area/exp_area로 크고 작음을 가르므로 같이 맞춘다.
            act_area, exp_area = act_len, max(exp_len, 1e-3)
            devs = (area_dev, center_dev)
        else:
            area_dev = min(1.0, abs(act_area - exp_area) / exp_area / tol_area)
            aspect_dev = min(1.0, abs(act_aspect - exp_aspect) / exp_aspect / tol_aspect)
            devs = (area_dev, aspect_dev, center_dev)
        dev = sum(devs) / len(devs)

        role = ("초성", "중성", "종성")[block_idx] if block_idx < 3 else "?"
        # ★ 항목별 개별 판정 — 하나라도 True면 이 성분은 빨강이 된다(사용자 결정).
        #   종합 점수로 뭉뚱그리면 한 항목의 잘못을 다른 항목이 희석한다.
        failed = area_dev >= 1.0 or center_dev >= 1.0 or aspect_dev >= 1.0
        # 무엇이 잘못됐는지 **방향까지** 남긴다 — 화면에 "성분비율"이라고만 뜨면
        # 크다는 건지 작다는 건지 알 수 없다(사용자 지적 2026-09-01).
        reasons: List[str] = []
        if area_dev >= 1.0:
            reasons.append("너무 큼" if act_area > exp_area else "너무 작음")
        if center_dev >= 1.0:
            reasons.append("자리가 벗어남")
        if not degenerate and aspect_dev >= 1.0:
            reasons.append("납작함" if act_aspect > exp_aspect else "길쭉함")
        components.append({
            "block": block_idx,
            "jamo": jamo,
            "role": role,
            "area_ratio": round(act_area / exp_area, 2),
            "score": round(100.0 * (1.0 - dev), 1),
            "balance_failed": failed,
            "balance_reasons": reasons,
            "box": _pixel_group_box(group),     # 화면에 그릴 성분 박스(캔버스 좌표)
        })
        if area_dev >= 1.0:
            bigger = act_area > exp_area
            corrections.append(
                f"{role} '{jamo}'이(가) 표준보다 너무 {'큽니다' if bigger else '작습니다'}.")
        if center_dev >= 1.0:
            corrections.append(f"{role} '{jamo}'의 자리가 표준에서 많이 벗어났습니다.")
        if not degenerate and aspect_dev >= 1.0:
            corrections.append(f"{role} '{jamo}'의 모양 비율이 표준과 많이 다릅니다.")

    if not components:
        return None
    return {
        "components": components,
        "score": sum(c["score"] for c in components) / len(components),
        "corrections": corrections,
    }


def build_component_boxes(strokes: List[Dict], bbox: Dict, target_char: str,
                          stroke_order_result: Optional[Dict],
                          direction_result: Optional[Dict],
                          tilt_result: Optional[Dict],
                          balance_result: Optional[Dict],
                          size_failed: bool = False) -> Optional[List[Dict]]:
    """화면에 그릴 **성분(초·중·종성) 단위 박스**와 그 색 판정 (2026-09-01 신설).

    박스 단위를 음절에서 성분으로 내린 이유: 채점 단위가 성분인데 박스가 음절이면
    빨간 박스를 봐도 **무엇이 문제인지 알 수 없다.** 성분마다 치면 박스 자체가 답이다.

    색은 두 가지뿐이다(사용자 결정 2026-09-01).
      · 초록 — 이 성분에 걸린 항목이 **전부** 통과
      · 빨강 — **하나라도** 오류

    ★ 종합 점수를 안 쓴다. 항목을 따로 판정하고 OR로 합친다 — 가중 평균을 쓰면
    획순을 통째로 틀려도 다른 항목이 끌어올려 초록이 나온다(2026-09-01 실측:
    낱자 획순 0점인데 종합 62점).

    낱자(ㄱ·ㅏ)는 성분이 하나뿐이라 박스를 만들지 않는다 — 캔버스 테두리를 다시
    그리는 것과 같아서 알려주는 게 없다. None을 돌려주면 화면이 안 그린다.
    """
    if balance_result is None or not balance_result.get("components"):
        return None                     # 낱자이거나 자모를 못 나눔 → 박스 없음

    order_per_block = (stroke_order_result or {}).get("per_block") or {}
    dir_per_block = (direction_result or {}).get("per_block") or {}
    tilt_per_block = (tilt_result or {}).get("per_block") or {}

    boxes: List[Dict] = []
    for comp in balance_result["components"]:
        b = comp["block"]
        reasons: List[str] = []
        n = order_per_block.get(b)
        if n:
            reasons.append(f"{ITEM_ORDER}({n}획 순서 틀림)")
        n = dir_per_block.get(b)
        if n:
            reasons.append(f"{ITEM_DIRECTION}({n}획 반대로 그음)")
        n = tilt_per_block.get(b)
        if n:
            reasons.append(f"{ITEM_TILT}({n}획 기울어짐)")
        if comp["balance_failed"]:
            # "성분비율"이라고만 적지 않고 **어떻게 틀렸는지**를 함께 넣는다.
            detail = ", ".join(comp.get("balance_reasons") or [])
            reasons.append(f"{ITEM_BALANCE}({detail})" if detail else ITEM_BALANCE)
        if size_failed:
            # 크기는 글자 전체 항목이라 그 글자의 **모든 성분**에 걸린다.
            # 성분 탓으로 오해되지 않도록 "글자 전체"라고 못박는다.
            reasons.append(f"{ITEM_SIZE}(글자 전체)")
        boxes.append({
            "block": b,
            "jamo": comp["jamo"],
            "role": comp["role"],
            "box": comp["box"],
            "ok": not reasons,
            "failed_items": reasons,
        })
    return boxes


def _stroke_speed_stats(strokes: List[Dict]) -> Dict:
    """stroke 좌표+시간으로부터 평균 속도(px/ms)를 계산.

    ⚠️ 속도는 **채점에 쓰지 않는다** — 응답·DB에 기록만 한다(사용자 결정 2026-09-01).
    소급이 안 되는 값이라 화면 노출 여부와 무관하게 쌓아 둔다.
    필압(pressure)은 같은 결정으로 **완전히 제거**했다: 지원하지 않는 기기에서 늘 1.0
    상수라 신호가 아니었고, DB에도 남지 않아 잃을 과거 데이터가 없었다.
    """
    speeds = []
    for stroke in strokes:
        pts = stroke["points"]
        for i in range(1, len(pts)):
            dt = pts[i]["timestamp"] - pts[i - 1]["timestamp"]
            if dt <= 0:
                continue
            dist = math.dist((pts[i]["x"], pts[i]["y"]), (pts[i - 1]["x"], pts[i - 1]["y"]))
            speeds.append(dist / dt)

    return {
        "mean_speed_px_per_ms": round(sum(speeds) / len(speeds), 4) if speeds else 0.0,
    }


def analyze_canvas_writing(
    char_groups: List[Dict],
    target_text: Optional[str] = None,
    guide_box: Optional[Dict] = None,
) -> List[Dict]:
    """
    SFR-005C 종합 분석 — 획순 / 획방향 / 성분비율 / 크기 / 자간.

    Parameters
    ----------
    char_groups : stroke_grouping.group_strokes_into_chars() 반환값
                  (읽기 순서 = 리스트 순서로 가정)
    target_text : 이 캔버스 세션에서 사용자에게 제시한 목표 텍스트.
                  "제시형" 연습 화면(CANVAS_DATA_PLAN.md 5.1)처럼 목표를 미리
                  아는 경우에만 획순·획방향·성분비율을 잴 수 있다 — None이면
                  크기/자간만 채점하고 나머지는 None(미측정)으로 둔다.
    guide_box   : 화면에 그려준 획순 가이드 상자 {x, y, width, height}
                  (획 좌표와 같은 캔버스 좌표계). **크기 채점의 절대 기준**이다.
                  없으면 크기는 '세션 내 상대 편차'로 폴백하는데, 글자가 하나뿐인
                  연습에서는 비교 대상이 없어 크기가 미측정으로 남는다.

    Returns
    -------
    List[Dict] — char_id별 {stroke_order_result, direction_result, balance_result,
                 spacing_deviation, size_deviation, size_fill_ratio, item_scores,
                 speed_profile, overall_score, correction_flags}

    측정 불가 항목은 **0이 아니라 None**이고 종합 점수의 분모에서도 빠진다.
    연습 종류별로 실제로 채점되는 항목이 다르다:
      · 자음·모음(낱자)  획순 · 획방향 · 크기
      · 한 글자          + 성분비율
      · 단어·문장        + 자간
    """
    if not char_groups:
        return []

    heights = [g["bounding_box"]["height"] for g in char_groups]
    widths  = [g["bounding_box"]["width"] for g in char_groups]
    median_h = sorted(heights)[len(heights) // 2]
    mean_w   = sum(widths) / len(widths)
    multi_char = len(char_groups) > 1

    guide_area = None
    if guide_box:
        guide_area = (guide_box.get("width", 0.0) or 0.0) * (guide_box.get("height", 0.0) or 0.0)
        if guide_area <= 0:
            guide_area = None

    results: List[Dict] = []
    for i, group in enumerate(char_groups):
        bb = group["bounding_box"]
        correction_flags: List[str] = []

        # ── 크기 ─────────────────────────────────────────────────
        # 정본은 **표준 자형 대비 크기 배율**(절대 기준)이다. 가이드 박스와 목표
        # 글자를 둘 다 알아야 잴 수 있다. 종전의 '세션 중앙값 대비'는 글자가 하나면
        # 중앙값이 자기 자신이라 늘 만점이었다 — 자음·모음과 한 글자 연습에서 크기
        # 채점이 사실상 없던 것과 같다.
        # ★ 크기는 **문장(글자 2개 이상)에서만** 잰다(사용자 결정 2026-09-01).
        # 캔버스에 글자 하나만 쓸 때 "얼마나 크게 썼나"는 임의값이라 의미가 없다 —
        # 크기가 뜻을 갖는 건 글자들끼리 고른지를 볼 수 있을 때다. 덤으로 "크기 실패 →
        # 그 글자의 성분이 전부 빨강"이라는 어색한 동작도 한 글자 연습에서는 사라진다.
        size_fill_ratio = None
        size_failed = False
        target_char = target_text[i] if (target_text and i < len(target_text)) else None
        if multi_char and guide_area and target_char:
            ref_fill = template_ink_fill(target_char)
            if ref_fill:
                actual_fill = (bb["width"] * bb["height"]) / guide_area
                size_fill_ratio = round(actual_fill / ref_fill, 3)
                if size_fill_ratio < SIZE_REL_MIN_OK:
                    correction_flags.append("size_small")
                    size_failed = True
                elif size_fill_ratio > SIZE_REL_MAX_OK:
                    correction_flags.append("size_large")
                    size_failed = True

        # 상대 편차는 가이드가 없을 때의 폴백이자, 글자끼리 크기가 고른지를 보는 값.
        # 글자가 하나뿐이면 비교 대상이 없으므로 None(미측정)이다.
        size_deviation_pct = None
        if multi_char:
            size_ratio = (bb["height"] / median_h) if median_h > 0 else 1.0
            size_deviation_pct = round((size_ratio - 1.0) * 100.0, 1)
            if guide_area is None:
                if size_ratio > SIZE_LARGE_THRESH:
                    correction_flags.append("size_large")
                elif size_ratio < SIZE_SMALL_THRESH:
                    correction_flags.append("size_small")

        # ── 자간 (이전 글자와의 간격) ─────────────────────────────────
        # 글자가 하나뿐인 연습(자음·모음·한 글자)에서는 비교할 옆 글자가 없다.
        # 종전에는 0.0으로 두어 '자간 만점'이 붙었다 — 재지 않은 지표의 만점이다.
        spacing_deviation_px = None
        if i > 0:
            prev_bb = char_groups[i - 1]["bounding_box"]
            gap = bb["x"] - (prev_bb["x"] + prev_bb["width"])
            expected_gap = mean_w * 0.4  # 표준 자간 근사치(평균 글자폭의 40%)
            spacing_deviation_px = round(gap - expected_gap, 1)
            gap_ratio = gap / mean_w if mean_w > 0 else 0.0
            if gap_ratio < SPACING_MIN_RATIO:
                correction_flags.append("spacing_too_narrow")
            elif gap_ratio > SPACING_MAX_RATIO:
                correction_flags.append("spacing_too_wide")

        # ── 획순 · 획방향 · 성분비율 (target_text가 있을 때만) ──────────
        # 셋 다 목표 글자를 알아야 잴 수 있다. 모르면 None으로 두고 종합 점수의
        # 분모에서도 빼서, 재지 않은 지표로 칭찬하지 않는다.
        stroke_order_result = None
        direction_result = None
        tilt_result = None
        balance_result = None
        if target_char:
            stroke_order_result = analyze_stroke_order_by_position(
                group["strokes"], bb, target_char
            )
            if stroke_order_result["error_count"] > 0:
                correction_flags.append("stroke_order_error")

            direction_result = analyze_stroke_direction(group["strokes"], bb, target_char)
            if direction_result and direction_result["error_count"] > 0:
                correction_flags.append("stroke_direction_error")

            tilt_result = analyze_stroke_tilt(group["strokes"], bb, target_char)
            if tilt_result and tilt_result["error_count"] > 0:
                correction_flags.append("stroke_tilt_error")

            balance_result = analyze_component_balance(group["strokes"], bb, target_char)
            if balance_result and balance_result["corrections"]:
                correction_flags.append("component_balance_error")

        # ── 화면에 그릴 성분 박스 + 색 판정 ─────────────────────────
        component_boxes = None
        if target_char:
            component_boxes = build_component_boxes(
                group["strokes"], bb, target_char,
                stroke_order_result, direction_result, tilt_result,
                balance_result, size_failed=size_failed)

        # ── 속도 (채점 미반영, 기록만) ───────────────────────────────
        motion_stats = _stroke_speed_stats(group["strokes"])

        # ── 항목 점수 + 종합 점수 ──────────────────────────────────
        # 항목 점수는 canvas_item_scores() 한 곳에서만 만든다 — 대시보드도 같은 함수를
        # 쓰므로 결과 화면과 분석 화면의 잣대가 갈리지 않는다(DATA_FLOW.md §8-G).
        item = canvas_item_scores(
            size_deviation_pct=size_deviation_pct,
            spacing_deviation_px=spacing_deviation_px,
            stroke_order_result=stroke_order_result,
            direction_result=direction_result,
            tilt_result=tilt_result,
            balance_result=balance_result,
            size_fill_ratio=size_fill_ratio,
        )
        overall_score = overall_from_items(item)

        results.append({
            "char_id": group["char_id"],
            "stroke_order_result": stroke_order_result,
            "direction_result": direction_result,
            "tilt_result": tilt_result,
            "balance_result": balance_result,
            "component_boxes": component_boxes,
            "spacing_deviation": spacing_deviation_px,
            "size_deviation": size_deviation_pct,
            "size_fill_ratio": size_fill_ratio,
            "item_scores": item,
            "speed_profile": {"mean_speed_px_per_ms": motion_stats["mean_speed_px_per_ms"]},
            "overall_score": overall_score,
            "correction_flags": correction_flags,
        })

    return results
