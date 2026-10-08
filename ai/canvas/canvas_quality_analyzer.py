"""
SFR-005C: 캔버스 필기 채점 — 네 축 (획순 · 모양 · 짜임새 · 배치)

stroke_grouping.py(SFR-004C)의 char_groups + 목표 텍스트(target_text) + 화면 가이드
(guide_box / char_positions)를 받아 글자마다 축 점수를 매긴다.
설계: docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md

**연습 단계마다 측정되는 축이 다르다** — 단계는 축을 더해 갈 뿐 이름은 바뀌지 않는다.
  · 자모음(낱자)   획순 · 모양
  · 한 글자        + 짜임새 (초·중·종성의 크기·비율·자리)
  · 문장           + 배치   (크기 · 자간 · 위치)

축 점수는 걸린 세부 판정 0건 / 1건 / 2건 이상에 따라 100 / 70 / 40이고, 글자 점수는
측정된 축의 평균이다. 측정 불가 축은 **0점이 아니라 None**이고 평균에서도 빠진다 —
재지도 않은 지표로 칭찬하거나 감점하지 않기 위해서다.

설계 메모
--------
- **좌표 프레임을 반드시 맞춘다.** 사용자 획은 자기 잉크 bbox 기준으로 [0,1]에 펴져
  들어오므로, 비교 대상인 표준 템플릿도 **잉크 기준**으로 정규화해야 한다. 각도·호길이를
  비교할 때는 반대로 표준을 사용자 테두리에 맞춰 편다(_template_paths_in_pixels).
- **짜임새는 크기와 무관하다.** 글자를 크게 썼든 작게 썼든 자모 사이 비율은 같게
  나온다 — 절대 크기는 배치 축이 가이드 대비로 따로 본다.
- **획순이 틀려도 짜임새는 살아 있다.** 획을 자모에 붙이는 일을 기하 매칭으로 하기
  때문이다. 획 개수로 순서대로 잘라 나누면 순서가 틀리는 순간 자모 분해가 무너진다.

한계 노트
--------
- 획 매칭은 중심점+모양 기반 기하 비교라, 목표 글자를 이미 아는 상황(제시형 UI)
  한정으로 쓸 수 있는 근사치다.
- speed_profile은 **채점에 쓰지 않고 기록만** 한다(사용자 결정 2026-09-01).
- 임계값은 **실사용자 필기로 보정된 값이 아니다.** 합성 데이터로 로직은 검증했지만
  기준 자체의 적절성은 미검증이다.
"""
import heapq
import math
from typing import Dict, List, Optional, Tuple

from .stroke_grouping import _stroke_bbox
from .stroke_standards import (
    get_expected_sequence, decompose_syllable,
    ALTERNATIVE_STROKE_ORDERS, standard_order_note, CHOSUNG, JUNGSUNG,
)
from .synthetic_stroke_generator import (
    _syllable_layout, _single_jamo_layout, _consonant_paths, _vowel_paths,
)

# 크기/간격 판정 임계값 (handwriting_analyzer.py와 동일한 CV 기반 설계)
SIZE_LARGE_THRESH = 1.5
SIZE_SMALL_THRESH = 0.65

# 자간: 인접 글자 bbox 간 gap을 "평균 글자 너비" 대비 비율로 판단
SPACING_EXPECTED_RATIO = 0.4   # 표준 자간 근사치(평균 글자폭의 40%)
SPACING_MIN_RATIO = 0.15   # 이보다 좁으면 너무 붙어씀
SPACING_MAX_RATIO = 1.2    # 이보다 넓으면 너무 띄어씀

# 획순 매칭 시 위치 거리 대비 모양(가로/세로 비율) 차이에 두는 가중치.
# 자모 내 두 획의 중심점이 서로 가까운 경우(예: ㅏ의 세로선과 가로 짧은 획)
# 위치만으로는 헷갈리기 쉬워서, 모양(길쭉한 방향)도 같이 비교해 구분한다.
SHAPE_WEIGHT = 1.5

COUNT_MISMATCH_RATIO_THRESHOLD = 2.0  # 기대 획수의 이 배수를 넘게 그리면 낙서로 본다

# ── 채점 거부 (2026-10-08 재설계, 설계 5절) ────────────────────────────────
# 거부 조건은 세 가지다: 획이 없다(건너뜀) · 획 수가 표준의 2배 초과(낙서) ·
# **획 모양이 다르고 잉크도 제자리에 없다**(딴 글자). 종전의 "획 수가 절반 이하" 조건은
# 획을 합쳐 쓴 정상 글씨를 거부해서 뺐다 — 잉크 기준이 그 역할을 대신한다.
#
# 획 모양 기준: 획을 같은 간격의 점으로 다시 찍고 **가로세로 비율을 유지한 채** 정규화한 뒤,
# ±35° 회전과 정·역방향을 허용해 점끼리 비교한다. 기울여 쓴 글씨는 돌리면 겹치지만,
# 직선은 아무리 돌려도 ㄱ이 되지 않는다. 실측(2026-09-17): 정상 글씨 144개(±7% 떨림) 중
# 잘못 거부 0개(최대 0.18), 엉뚱한 글씨 36개 전부 적발.
WRONG_CHAR_MEAN_DIST = 0.20   # 획들의 평균 모양 거리가 이보다 크면 딴 글자(후보)
WRONG_CHAR_MAX_DIST = 0.32    # 한 획이라도 이보다 멀면 딴 글자(후보)
WRONG_CHAR_ROT_DEG = 35       # 이 각도까지는 "기울여 쓴 것"으로 보고 돌려서 맞춰본다
WRONG_CHAR_SAMPLES = 16       # 획 하나를 몇 점으로 다시 찍어 비교하나
UNMATCHED_STROKE_PENALTY = 0.6  # 안 쓴 표준 획 / 남는 여분 획 하나당 거리 벌점(평균에만)

# 잉크 기준: 획 모양 기준이 거부하려 할 때, 잉크가 제자리에 있으면 거부하지 않는다.
# 획 모양 기준은 **획 단위**라 획을 합쳐 쓰면(ㄷ을 한 획에, ㅁ을 두 획에) 제대로 쓴 글씨도
# 딴 글자로 나왔다. 획을 합쳐도 잉크는 같은 자리에 있으므로, 두 글씨의 잉크를 점구름으로
# 펴서 "표준에 있는데 사용자에게 없는 잉크"와 "사용자에게 있는데 표준에 없는 잉크"를 재고
# 각각의 95퍼센타일 중 나쁜 쪽을 쓴다.
# 실측(2026-09-21): 제대로 쓴 글자 234건 최대 0.052 · 획 합쳐 쓴 글자 120건 대부분 0.1 아래
# · 명백한 낙서 35건 최소 0.170. 0.15면 제대로 쓴 글씨의 3배 여유가 있고 낙서와도 안 겹친다.
#
# ⚠️ 비슷한 다른 글자(밤↔방 0.07, 물↔불 0.11)는 어느 기준으로도 못 가른다. 문자 인식
# 문제라 학습 데이터 없이는 풀 수 없다 — 거부는 명백한 낙서만 잡는 것으로 둔다.
INK_MISMATCH_MAX = 0.15
INK_SAMPLE_STEP = 0.025         # 정규화 크기 1 기준 점 간격

# ── 채점 기준 (단일 출처) ──────────────────────────────────────────────
# ⚠️ 캔버스 채점 기준은 여기 한 곳에만 둔다. 백엔드 대시보드(dashboard_service)도
# 백엔드는 AI가 만든 축 점수(build_axes)를 그대로 저장·집계한다 — 복사본이나 별도 설정값을 만들지 말 것.
# 종전에는 백엔드 config.py에 다른 계수(크기 0.5 / 자간 0.5 / 획순 10)가 따로 있어,
# 같은 글씨인데 결과 화면과 분석 화면의 점수가 어긋났다(DATA_FLOW.md §8-G).
#
# ⚠️ 아래 숫자는 **실사용자 필기로 보정된 값이 아니다.** 합성 데이터로 로직이 맞게
# 도는지는 확인했지만 "이 기준이 적절한가"는 미검증이다. 실사용 데이터가 모이면
# 재조정해야 한다(REQ-005C-6이 요구하는 설정 외부화도 이 시점에 함께).

# ── 모서리(2026-09-18 신설, 사용자 신고 "글씨가 둥글한데 잡을 방법이 없나") ──
# ㄷ·ㄹ·ㅁ처럼 직각으로 꺾어야 하는 자리를 둥글게 돌려 쓰는 습관은 지금까지
# **어느 항목에도 안 걸렸다.** 획순·획방향은 순서와 방향만 보고, 기울기는 획의
# 시작→끝 각도만 보며(둥글려도 양 끝점은 그대로다), 성분비율은 테두리 크기만 본다.
#
# 재는 법: 표준 꼭짓점마다 "사용자가 실제로 꺾은 각 ÷ 표준 꺾임각"을 낸다.
# 1.0이면 각지게, 0에 가까우면 완전히 둥글린 것이다. 각도라서 글자 크기와 무관하다.
#
# 실측(자모 13종 × 떨림 4단계, 꼭짓점을 원호로 둥글려 가며):
#   각지게 쓴 표준 평균 0.95 (하위 5%도 0.88)
#   살짝 둥글림(r=0.15) 0.66~0.72 · 뚜렷(r=0.30) 0.46~0.61 · 완전(r=0.45) 0.35~0.49
# 0.6에 선을 그으면 표준과의 여유가 0.28이라 오탐이 거의 없고, 뚜렷하게 둥근 것부터
# 잡힌다. 살짝 둥근 것은 일부러 통과시킨다(사람 손은 원래 조금씩 둥글다).
CORNER_SHARP_MIN_RATIO = 0.6
CORNER_MIN_ANGLE_DEG = 45.0    # 이보다 얕게 꺾이는 자리는 '모서리'로 안 본다
CORNER_SAMPLES = 40            # 획을 호길이 등간격으로 몇 점에 다시 찍나
CORNER_BASELINE = 3            # 꺾임각을 재는 기준선 폭(점 개수) — 떨림에 안 흔들리게
CORNER_WINDOW = 0.15           # 표준 꼭짓점 주변 이 비율(호길이)만큼을 훑는다
CORNER_MIN_POINTS = 8          # 이보다 점이 적은 획은 건너뛴다

# 낱자(자음·모음) 전용 '모양' 항목의 실패 기준 (2026-09-17 신설, 사용자 신고).
#
# 왜 낱자에만 두나 — 음절은 성분비율이 초·중·종성의 크기·자리를 이미 본다. 그런데
# **낱자는 성분이 하나뿐이라 성분비율이 미측정**이고, 크기도 한 글자에선 안 재며,
# 기울기는 곧게 그어야 하는 획만 본다(ㅁ의 꺾인 획은 제외). 그래서 네모가 찌그러지든
# 선이 안 만나든 **잡을 항목이 하나도 없었다** — 사용자가 ㅁ을 쓰고 100점을 받은 사례.
#
# 실측(2026-09-17, ㅁ 기준 max 거리): 표준 0.05 · 손떨림 ±5% 0.12 · 찌그러진 사다리꼴
# 0.12 · 20° 기울임 0.18 · 아래변 안 닿음 0.18 · 세로로 납작 0.21.
# ⚠️ **손떨림과 가벼운 찌그러짐은 이 지표로 갈리지 않는다**(둘 다 0.12). 떨림을 오류로
# 잡지 않으려면 그 위에 선을 그어야 하므로, 눈에 띄는 변형만 잡는다.
SHAPE_FAIL_DIST = 0.15

# ── 채점 축 (2026-10-08 재설계, docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md) ──
# 9개 항목을 "배우는 것" 단위의 네 축으로 묶는다. 단계는 축을 더해 갈 뿐 이름은 바뀌지 않는다.
#   자모음: 획순 · 모양 / 한 글자: + 짜임새 / 문장: + 배치
AXIS_ORDER   = "획순"    # 순서 어긋남 · 반대 방향 · 획 수
AXIS_SHAPE   = "모양"    # 획 기울기 · 글자 기울기(낱자) · 모서리 · 표준과 다른 모양(낱자)
AXIS_BALANCE = "짜임새"  # 초·중·종성의 크기·비율·자리
AXIS_LAYOUT  = "배치"    # 크기 · 자간 · 위치 (문장)
ALL_AXES = (AXIS_ORDER, AXIS_SHAPE, AXIS_BALANCE, AXIS_LAYOUT)

# 축 점수는 세 단계뿐이다 — 걸린 세부 판정 0건 / 1건 / 2건 이상.
# 경고가 있는 축은 100이 될 수 없으므로 경고와 점수가 늘 같은 방향이다.
AXIS_SCORE_PASS, AXIS_SCORE_PARTIAL, AXIS_SCORE_SEVERE = 100, 70, 40


def axis_score(n_failed: int, measured: bool) -> Optional[int]:
    """걸린 세부 판정 건수 → 축 점수. 측정 못 했으면 None(0도 100도 아니다)."""
    if not measured:
        return None
    if n_failed <= 0:
        return AXIS_SCORE_PASS
    return AXIS_SCORE_PARTIAL if n_failed == 1 else AXIS_SCORE_SEVERE


def axis_label(axis: str, reasons: List[str]) -> str:
    """화면 사유 한 줄: '모양(1획 기울어짐, 모서리 1곳 둥글림)'."""
    return f"{axis}({', '.join(reasons)})" if reasons else axis


def overall_from_axes(axes: Dict[str, Dict]) -> Optional[int]:
    """글자 점수 = 측정된 축의 평균(반올림). 측정된 축이 없으면 None."""
    scores = [a["score"] for a in axes.values() if a["score"] is not None]
    return round(sum(scores) / len(scores)) if scores else None


def build_axes(*, stroke_order_result: Optional[Dict], direction_result: Optional[Dict],
               tilt_result: Optional[Dict], char_rotation_deg: Optional[float],
               corner_result: Optional[Dict], shape_failed: Optional[bool],
               balance_result: Optional[Dict], size_reason: Optional[str],
               spacing_reason: Optional[str], position_failed: Optional[bool]) -> Dict[str, Dict]:
    """세부 측정 결과 → 축별 {score, reasons}. 네 축 모두 키가 있고, 못 잰 축은 score None.

    인자의 None은 '이 판정을 하지 않았다'는 뜻이다. shape_failed·position_failed는 bool이면
    판정한 것이고, size_reason·spacing_reason은 문자열이면 걸림 / ""이면 통과 / None이면 미측정.
    """
    axes: Dict[str, Dict] = {}

    # 획순 — 두 획이 자리를 바꾸면 어긋난 자리가 2곳이지만 실수는 하나다(÷2 올림).
    reasons: List[str] = []
    n = 0
    measured = stroke_order_result is not None
    if measured:
        swaps = -(-int(stroke_order_result.get("order_error_count") or 0) // 2)
        if swaps:
            reasons.append(f"{swaps}획 순서 틀림")
        reversed_n = int((direction_result or {}).get("error_count") or 0)
        if reversed_n:
            reasons.append(f"{reversed_n}획 반대로 그음")
        drawn = stroke_order_result.get("stroke_count")
        expected = stroke_order_result.get("expected_count")
        count_off = drawn is not None and expected is not None and drawn != expected
        if count_off:
            # 획을 합치거나 나눠 쓰면 짝이 밀려 '순서 어긋남'이 따라 나온다 — 같은 사건을
            # 두 번 세지 않도록 획 수만 센다(종전 max(순서, 부족)와 같은 뜻).
            reasons = [r for r in reasons if not r.endswith("순서 틀림")]
            swaps = 0
            reasons.append(f"획 수 {drawn}개 / 표준 {expected}개")
        n = swaps + reversed_n + (1 if count_off else 0)
    axes[AXIS_ORDER] = {"score": axis_score(n, measured), "reasons": reasons}

    # 모양 — 기울어짐 · 모서리 · 표준과 다른 모양. 하나라도 쟀으면 측정.
    # ⚠️ 획 기울기와 글자 전체 기울기는 **같은 습관(기울임)이라 합쳐서 1건**이다. 글자를
    # 통째로 기울이면 곧은 획이 전부 기울어지므로 따로 세면 자모에 따라 70도 되고 40도
    # 된다(ㅇ 20° = 70, ㅌ 20° = 40). 같은 이유로 기울어진 글자의 '표준과 다른 모양'은
    # 세지 않는다 — 모양 거리는 회전에 같이 벌어지는 값이라 같은 사건을 다시 센다.
    reasons, n, measured = [], 0, False
    tilted = False
    if tilt_result and tilt_result.get("checked", 0) > 0:
        measured = True
        k = int(tilt_result.get("error_count") or 0)
        if k:
            reasons.append(f"{k}획 기울어짐")
            tilted = True
    if char_rotation_deg is not None:
        measured = True
        if abs(char_rotation_deg) > CHAR_ROT_MAX_DEG:
            side = "오른쪽" if char_rotation_deg > 0 else "왼쪽"
            reasons.append(f"글자 전체가 {side}으로 {abs(char_rotation_deg):.0f}도 기울어짐")
            tilted = True
    if tilted:
        n += 1
    if corner_result and corner_result.get("checked", 0) > 0:
        measured = True
        k = int(corner_result.get("error_count") or 0)
        if k:
            reasons.append(f"모서리 {k}곳 둥글림")
            n += k
    if shape_failed is not None:
        measured = True
        if shape_failed and not tilted:
            reasons.append("표준 모양과 많이 다름")
            n += 1
    axes[AXIS_SHAPE] = {"score": axis_score(n, measured), "reasons": reasons}

    # 짜임새 — 걸린 성분 하나가 1건.
    reasons = []
    comps = (balance_result or {}).get("components") or []
    for c in comps:
        if c.get("balance_failed"):
            detail = "·".join(c.get("balance_reasons") or [])
            reasons.append(f"{c['role']} '{c['jamo']}' {detail}".strip())
    axes[AXIS_BALANCE] = {"score": axis_score(len(reasons), bool(comps)), "reasons": reasons}

    # 배치 — 크기 · 자간 · 위치 각 1건. 셋 중 하나라도 쟀으면 측정.
    reasons = []
    measured = (size_reason is not None or spacing_reason is not None
                or position_failed is not None)
    if size_reason:
        reasons.append(f"크기 {size_reason}")
    if spacing_reason:
        reasons.append(spacing_reason)
    if position_failed:
        reasons.append("글자 칸에서 벗어남")
    axes[AXIS_LAYOUT] = {"score": axis_score(len(reasons), measured), "reasons": reasons}
    return axes

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
# 2026-09-18에 15도 -> 12도로 조였다(사용자 요청 "각 성분 기울기 살짝 더 엄격하게").
# 표준대로 쓴 필기 90건(음절 6 + 낱자 4, 떨림 3단계 × 3회)에서 10도까지 내려도
# 오탐이 0건이라 여유가 있었다. 12도에서 18도 기울인 획 검출이 56% -> 68%,
# 25도는 68% -> 79%로 올라간다. 10도까지 내리면 12도 획도 절반 넘게 걸려
# "살짝"을 넘어서므로 12도에서 멈췄다.
STRAIGHT_STROKE_MAX_TILT_DEG = 12.0
# 글자 크기 대비 이 길이 미만인 획은 기울기를 아예 재지 않는다(ㅊ·ㅎ의 머리획이
# 0.14~0.15인데, 떨림 ±2%만으로 21~25도가 나왔다 — 각도가 사실상 난수다).
TILT_MIN_STROKE_LEN = 0.22
# 짧은 획은 같은 손떨림에도 각도가 더 크게 흔들린다(오차 ∝ 1/길이). 그래서
# 허용치를 길이에 반비례해 늘린다 — 이 길이부터는 기본 허용치를 그대로 쓴다.
TILT_FULL_STROKE_LEN = 0.6
TILT_MAX_TOL_DEG = 24.0       # 아무리 짧아도 여기까지만 봐준다(기본 허용치와 같은 비율로 조임)
# 표준 획이 이 각도 이내로 수평/수직이면 "곧게 그어야 하는 획"으로 본다.
STRAIGHT_STROKE_AXIS_TOL_DEG = 20.0

# ── 글자 전체 기울기 (낱자 전용, 2026-09-17 신설) ───────────────────────────
# 위의 획 단위 기울기는 **표준이 수평·수직인 획**만 본다. 그래서 ㅁ·ㅇ처럼 곧고 긴
# 획이 없는 자모나 ㄱ·ㄴ처럼 꺾인 한 획짜리 자모는 **통째로 30도를 기울여 써도**
# 아무 항목에도 안 걸렸다(사용자 지적 2026-09-17: "ㅁ 썼는데 100점이 나온다").
# 모양 거리(_shape_distance)도 못 잡는다 — 거기는 기울기와 이중 판정이 되지 않도록
# 회전을 **일부러** 허용하기 때문이다. 그래서 estimate_char_rotation이 마디 각도의
# 중앙값으로 따로 잰다. 합성 실측(자모 24종, 명조 비율과 칸에 꽉 채운 비율 양쪽)에서
# 똑바로 쓴 글자는 ±7도 안, ±25도로 기울이면 전부 15도를 넘겨 잡혔다.
# ⚠️ **획 기준(STRAIGHT_STROKE_MAX_TILT_DEG)에 묶지 않는다.** 획 기울기는 각도를
# 직접 재지만 이쪽은 마디 각도의 중앙값으로 **추정**하는 값이라 오차가 더 크다 —
# 똑바로 쓴 글자도 ±7도까지 나왔다(2026-09-18 실측). 획 기준을 12도로 조이면서
# 여기까지 따라 내리면 여유가 5도밖에 안 남아 오탐이 난다.
CHAR_ROT_MAX_DEG = 15.0

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

# 크기(상대) — 가이드 박스를 못 받았을 때만 쓰는 폴백. 글자가 2개 이상이어야 의미가 있다.



def _clamp_score(v: float) -> float:
    return max(0.0, min(100.0, v))


def _position_check(bb: Dict, pos: Optional[Dict]) -> Tuple[Optional[float], bool]:
    """화면에 보여준 글자 칸(pos)에 맞춰 썼나 → (점수, 벗어났나).

    문장 연습에만 쓴다(사용자 결정 2026-09-17). 자음·모음·한 글자는 가이드 위에
    덧쓰는 연습이 아니라서 위치를 볼 필요가 없다.

    판정은 **쓴 글자의 중심이 그 칸 안에 있나**로 한다 — 칸보다 크게 쓰는 건 크기
    항목의 몫이고, 여기서 보려는 건 "옆 글자 자리에 썼다"처럼 자리를 벗어난 경우다.
    """
    if not pos:
        return None, False
    pw = float(pos.get("width") or 0.0)
    ph = float(pos.get("height") or 0.0)
    if pw <= 0 or ph <= 0:
        return None, False
    px, py = float(pos.get("x", 0.0)), float(pos.get("y", 0.0))
    cx = bb["x"] + bb["width"] / 2.0
    cy = bb["y"] + bb["height"] / 2.0
    # 칸 밖으로 얼마나 나갔나(안이면 0)
    dx = max(px - cx, 0.0, cx - (px + pw))
    dy = max(py - cy, 0.0, cy - (py + ph))
    if dx == 0.0 and dy == 0.0:
        return 100.0, False
    off = math.hypot(dx, dy) / max(pw, ph)
    return _clamp_score(100.0 - 100.0 * off), True


def _guide_pitch(positions: Optional[List[Dict]], i: int) -> Optional[Tuple[float, float]]:
    """화면에 보여준 i-1번째·i번째 글자 칸의 (중심 사이 거리, 평균 칸 너비).

    칸 정보가 없거나 쓸 수 없으면 None — 그때는 자유 필기 기준으로 자간을 잰다.
    """
    if not positions or i <= 0 or i >= len(positions):
        return None
    prev, cur = positions[i - 1], positions[i]
    pw, cw = float(prev.get("width") or 0.0), float(cur.get("width") or 0.0)
    if pw <= 0 or cw <= 0:
        return None
    pitch = (float(cur.get("x", 0.0)) + cw / 2.0) - (float(prev.get("x", 0.0)) + pw / 2.0)
    return pitch, (pw + cw) / 2.0


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
    # 1.4까지 벌어져 옛 딴글자 기준(0.6)을 넘고, "목표 글자와 많이 달라
    # 보입니다"로 오판했다. 자음 탭 첫 두 글자(ㄱ·ㄴ)가 여기 해당했다.
    frame = _union_box([_path_ink_box(p) for _, paths in layout for p in paths])

    specs = []
    for block_idx, (jamo_label, paths) in enumerate(layout):
        for path in paths:
            normed = [_renormalize_point(pt, frame) for pt in path]
            specs.append((block_idx, jamo_label,
                          _path_descriptor(normed), _path_direction(normed)))
    return specs


def _template_paths_in_pixels(target_char: str, bbox: Dict) -> List[List[Tuple[float, float]]]:
    """표준 획을 **사용자가 쓴 글자 테두리에 맞춰 편 좌표**(테두리 왼쪽 위가 원점)로 준다.

    ⚠️ 각도나 호길이를 표준과 비교할 때는 반드시 이걸 쓴다. 매칭용 표준
    (_canonical_stroke_specs)은 잉크 틀을 [0,1]×[0,1]로 **가로세로 따로** 편 공간이라,
    틀이 정사각형이 아니면 각도와 호길이 비율이 픽셀 공간과 달라진다. 사용자 획은
    픽셀 그대로 재므로 표준도 같은 공간으로 옮겨야 한다.
    실측: '리'는 틀 폭이 높이의 0.58배라 ㄹ 끝획이 표준 20도 / 실제 32도로 어긋나
    표준대로 써도 "12도 기울었습니다"가 나왔고, '느·그·드·르'는 모서리 위치가
    0.58 / 0.33으로 어긋나 "모서리를 둥글게 돌렸습니다"가 나왔다.
    """
    bw, bh = bbox["width"] or 1.0, bbox["height"] or 1.0
    return [[(x * bw, y * bh) for x, y in path]
            for path in _canonical_stroke_paths(target_char)]


# 시작점과 끝점을 잇는 직선에서 이만큼(직선 길이 대비)까지 벗어나도 곧은 획으로 본다.
STRAIGHT_PATH_MAX_DEV = 0.05


def _is_straight_path(path: List[Tuple[float, float]]) -> bool:
    """꺾이지 않은 곧은 획인가. ㄱ·ㄴ 모양으로 꺾인 획과 닫힌 획(ㅇ)은 아니다."""
    (x0, y0), (x1, y1) = path[0], path[-1]
    chord = math.hypot(x1 - x0, y1 - y0)
    if chord <= 0:
        return False
    dev = max(abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) / chord for x, y in path)
    return dev <= STRAIGHT_PATH_MAX_DEV * chord


def _reliable_blocks(specs: List, matched: List[int]) -> set:
    """획 단위 비교(획방향·기울기·모서리)를 믿어도 되는 자모 블록 번호.

    이 세 항목은 "i번째 사용자 획 = 표준의 이 획"이라는 짝을 전제로 한다. 획을 합쳐
    쓰거나 나눠 쓰면 그 짝이 성립하지 않아, 합친 획을 표준 획 하나와 견주게 된다 —
    한 획에 쓴 ㄷ이 "70도 기울어짐", 두 획에 쓴 ㄱ이 "모서리를 둥글게 돌림"으로 나왔다.
    그래서 **표준과 획 수가 같은 블록만** 본다. 여분 획이 있으면 어느 짝이 밀렸는지
    알 수 없으므로 전부 못 믿는다. 획 수가 다른 것 자체는 획순 항목이 지적한다.
    """
    if any(m == -1 for m in matched):
        return set()
    expected: Dict[int, int] = {}
    for spec in specs:
        expected[spec[0]] = expected.get(spec[0], 0) + 1
    actual: Dict[int, int] = {}
    for m in matched:
        actual[specs[m][0]] = actual.get(specs[m][0], 0) + 1
    return {block for block, n in expected.items() if actual.get(block) == n}


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


def _resample_path(points: List[Tuple[float, float]],
                   n: int = WRONG_CHAR_SAMPLES) -> List[Tuple[float, float]]:
    """획을 길이 기준 등간격 n점으로 다시 찍는다 — 점이 촘촘한 곳에 쏠리지 않도록."""
    if len(points) == 1:
        return [points[0]] * n
    seg = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(seg)
    if total <= 0:
        return [points[0]] * n
    out: List[Tuple[float, float]] = []
    acc, i = 0.0, 0
    for k in range(n):
        target = total * k / (n - 1)
        while i < len(seg) - 1 and acc + seg[i] < target:
            acc += seg[i]
            i += 1
        u = 0.0 if seg[i] == 0 else min(1.0, (target - acc) / seg[i])
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        out.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    return out


def _normalize_uniform(paths: List[List[Tuple[float, float]]]) -> List[List[Tuple[float, float]]]:
    """글자 전체를 **가로세로 같은 배율로** 줄여 무게중심을 원점에 둔다.

    ⚠️ 축마다 따로 늘리면(=매칭이 쓰는 방식) 획의 각도가 바뀌어 모양 비교가 무너진다.
    한 획짜리 자모가 늘 정사각형이 되던 것이 그 때문이다.

    배율은 **테두리의 긴 변**으로 잡는다. 무게중심+평균거리(회전에 불변)로 잡아 보니
    ㅡ·ㅣ처럼 단순한 획에서 손떨림이 배율 대비 너무 커져, 제대로 쓴 글씨가 엉뚱한
    글씨보다 멀어졌다(2026-09-17 실측: ±6% 떨림에 0.47 vs 'ㅂ에 ㅁ' 0.33).
    """
    xs = [x for path in paths for x, _ in path]
    ys = [y for path in paths for _, y in path]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    scale = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    return [[((x - cx) / scale, (y - cy) / scale) for x, y in path] for path in paths]


def _shape_distance(user: List[Tuple[float, float]],
                    template: List[Tuple[float, float]]) -> float:
    """두 획의 모양 거리 — ±WRONG_CHAR_ROT_DEG 회전과 정·역방향 중 가장 가까운 값.

    회전을 허용하는 이유: 기울여 쓴 글씨는 **틀리게 쓴 것이지 다른 글자가 아니다.**
    기울기는 analyze_stroke_tilt가 따로 채점하므로 여기서 또 잡으면 이중 판정이 된다.
    방향을 뒤집어 보는 이유도 같다 — 획방향은 analyze_stroke_direction의 몫이다.
    """
    cx = sum(x for x, _ in user) / len(user)
    cy = sum(y for _, y in user) / len(user)
    best = float("inf")
    for deg in range(-WRONG_CHAR_ROT_DEG, WRONG_CHAR_ROT_DEG + 1, 5):
        a = math.radians(deg)
        ca, sa = math.cos(a), math.sin(a)
        rotated = [(cx + (x - cx) * ca - (y - cy) * sa,
                    cy + (x - cx) * sa + (y - cy) * ca) for x, y in user]
        for candidate in (rotated, rotated[::-1]):
            d = sum(math.dist(p, q) for p, q in zip(candidate, template)) / len(template)
            if d < best:
                best = d
    return best


def _pair_strokes_by_shape(user: List[List[Tuple[float, float]]],
                           tmpl: List[List[Tuple[float, float]]]
                           ) -> List[Tuple[float, int, int]]:
    """모양이 가까운 짝부터 묶는다(그린 순서와 무관) → [(거리, 사용자 획, 표준 획)].

    모든 짝의 _shape_distance를 다 구하면 획 수의 제곱만큼 돌아 글자당 계산의 대부분을
    차지했다(9획 글자 = 81쌍 × 회전 15개 × 정·역). 점 거리의 평균은 **무게중심 사이
    거리보다 작을 수 없고**(_shape_distance는 획을 자기 무게중심 둘레로만 돌린다) 그
    값은 싸게 구해지므로, 그걸 하한으로 줄을 세워 필요한 짝만 정확히 계산한다.
    결과는 전부 계산해 정렬한 것과 같다.
    """
    def centroid(path):
        return (sum(x for x, _ in path) / len(path), sum(y for _, y in path) / len(path))

    cu = [centroid(u) for u in user]
    ct = [centroid(t) for t in tmpl]
    # (거리, 정확한 값인가, 사용자 획, 표준 획). 하한은 반올림 오차만큼 낮춰 둔다.
    heap = [(math.dist(cu[i], ct[j]) - 1e-9, 0, i, j)
            for i in range(len(user)) for j in range(len(tmpl))]
    heapq.heapify(heap)
    used_u: set = set()
    used_t: set = set()
    pairs: List[Tuple[float, int, int]] = []
    while heap:
        d, exact, i, j = heapq.heappop(heap)
        if i in used_u or j in used_t:
            continue
        if not exact:
            heapq.heappush(heap, (_shape_distance(user[i], tmpl[j]), 1, i, j))
            continue
        used_u.add(i)
        used_t.add(j)
        pairs.append((d, i, j))
    return pairs


def _densify(paths: List[List[Tuple[float, float]]], step: float) -> List[Tuple[float, float]]:
    """폴리라인들을 일정 간격의 점구름으로 편다(획 경계는 무시한다)."""
    pts: List[Tuple[float, float]] = []
    for path in paths:
        for a, b in zip(path, path[1:]):
            n = max(1, int(math.dist(a, b) / step))
            for k in range(n):
                pts.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
        if path:
            pts.append(path[-1])
    return pts


def _ink_gap(user_paths: List[List[Tuple[float, float]]],
             template_paths: List[List[Tuple[float, float]]]) -> float:
    """두 글씨의 잉크가 서로 얼마나 벗어났나 — **획 수와 무관한** 비교.

    양쪽을 같은 방식(가로세로 같은 배율)으로 정규화한 뒤,
      빠진 잉크 = 표준 잉크 점마다 가장 가까운 사용자 잉크까지의 거리
      남는 잉크 = 사용자 잉크 점마다 가장 가까운 표준 잉크까지의 거리
    각각의 95퍼센타일 중 **나쁜 쪽**을 돌려준다. 최댓값 대신 95퍼센타일을 쓰는 것은
    획 끝의 삐침 몇 점 때문에 판정이 뒤집히지 않게 하려는 것이다.
    """
    U = _densify(_normalize_uniform(user_paths), INK_SAMPLE_STEP)
    T = _densify(_normalize_uniform(template_paths), INK_SAMPLE_STEP)
    if not U or not T:
        return float("inf")

    def p95(A, B):
        ds = sorted(min(math.dist(a, b) for b in B) for a in A)
        return ds[min(len(ds) - 1, int(len(ds) * 0.95))]
    return max(p95(T, U), p95(U, T))


def assess_character_match(strokes: List[Dict], target_char: str) -> Dict:
    """**목표 글자를 쓴 게 맞는가** — 채점 거부 판정 (2026-10-08 재설계, 설계 5절).

    거부 조건은 세 가지다.
      ① 획이 하나도 없다(건너뜀)                         → missing
      ② 획 수가 표준의 2배를 넘는다(낙서)                → too_many_strokes
      ③ 획 모양이 표준과 다르고 **잉크도 제자리에 없다**  → shape_mismatch
    ③은 두 기준을 **둘 다** 넘어야 한다. 획 모양 기준(획끼리 짝지어 ±35° 회전·역방향을
    허용한 거리)만 쓰면 획을 합쳐 쓴 글씨가 거부되고, 잉크 기준만 쓰면 ㅣ 하나를 25°
    기울인 '리'가 거부된다(2026-10-08 실측) — 기울기는 모양 축이 지적할 몫이지 거부할
    일이 아니다. 종전의 "획 수가 절반 이하면 거부"는 뺐다(잉크 기준이 대신한다).
    """
    if decompose_syllable(target_char) is None:
        if target_char in CHOSUNG:
            template_paths = _consonant_paths(target_char)
        elif target_char in JUNGSUNG:
            template_paths = _vowel_paths(target_char)
        else:
            template_paths = []
    else:
        template_paths = [path for _, paths in _layout_for_char(target_char) for path in paths]
    n_expected = len(template_paths)
    user_paths = [[(p["x"], p["y"]) for p in st["points"]] for st in strokes]
    user_paths = [path for path in user_paths if path]
    base: Dict = {"n_strokes": len(user_paths), "n_expected": n_expected,
                  "mean_distance": None, "max_distance": None, "ink_gap": None}

    if not user_paths:
        return {**base, "scorable": False, "reason": "missing"}
    if not template_paths:
        return {**base, "scorable": True, "reason": None}     # 표준을 모르는 글자는 거부하지 않는다
    if len(user_paths) > n_expected * COUNT_MISMATCH_RATIO_THRESHOLD:
        return {**base, "scorable": False, "reason": "too_many_strokes"}

    # 잉크 비교는 점구름 전수 비교라 글자당 계산의 대부분을 차지한다. 획 모양 기준이
    # 거부하려 할 때만 계산한다 — 정상 글씨에서는 쓸 일이 없다.
    def ink_ok() -> bool:
        if base["ink_gap"] is None:
            base["ink_gap"] = round(_ink_gap(user_paths, template_paths), 3)
        return base["ink_gap"] <= INK_MISMATCH_MAX

    tmpl = [_resample_path(path) for path in _normalize_uniform(template_paths)]

    if len(user_paths) == 1 and len(tmpl) == 1:
        best = _single_stroke_shape_distance(user_paths[0], tmpl[0])
        # 획이 하나라 평균과 최댓값이 같은 값이다 — 두 기준 중 하나라도 넘으면 딴 글자.
        wrong = best > min(WRONG_CHAR_MEAN_DIST, WRONG_CHAR_MAX_DIST) and not ink_ok()
        return {**base, "mean_distance": round(best, 3), "max_distance": round(best, 3),
                "scorable": not wrong, "reason": "shape_mismatch" if wrong else None}

    user = [_resample_path(path) for path in _normalize_uniform(user_paths)]
    # 가장 가까운 짝부터 묶는다(그린 순서와 무관하게) — 획순이 틀린 것은 거부 사유가
    # 아니므로, 순서대로 비교하면 순서 오류를 딴 글자로 오해한다.
    dists: List[float] = [d for d, _, _ in _pair_strokes_by_shape(user, tmpl)]
    # ⚠️ 짝이 안 맞은 획도 세야 한다. 맞은 획만 평균 내면, 획을 하나 빠뜨린 비슷한
    # 글자가 "잘 맞는다"고 나온다('ㅂ' 자리에 ㅁ = 평균 0.09). 벌점은 **평균에만** 넣는다 —
    # 최댓값에 넣으면 획을 하나만 덜 그어도 무조건 거부된다(2026-09-21 '밤' 신고).
    unmatched = (len(tmpl) - len(dists)) + (len(user) - len(dists))
    max_d = max(dists) if dists else 0.0
    dists += [UNMATCHED_STROKE_PENALTY] * unmatched
    mean_d = sum(dists) / len(dists) if dists else 0.0
    wrong = (mean_d > WRONG_CHAR_MEAN_DIST or max_d > WRONG_CHAR_MAX_DIST) and not ink_ok()
    return {**base, "mean_distance": round(mean_d, 3), "max_distance": round(max_d, 3),
            "scorable": not wrong, "reason": "shape_mismatch" if wrong else None}


def _single_stroke_shape_distance(pts: List[Tuple[float, float]],
                                  tmpl: List[Tuple[float, float]]) -> float:
    """한 획짜리 글자의 모양 거리 — **회전을 정규화보다 먼저** 한다.

    획이 곧 글자라서 기울이면 테두리가 통째로 달라지고, 정규화 뒤에 돌리면 아무리 돌려도
    안 겹친다(2026-09-17 실측: ㄱ·ㄴ을 30° 기울이면 제대로 쓴 글씨가 거부됐다).
    tmpl은 이미 정규화·재표본된 표준 획이다.
    """
    best = float("inf")
    cx = sum(x for x, _ in pts) / len(pts)
    cy = sum(y for _, y in pts) / len(pts)
    for deg in range(-WRONG_CHAR_ROT_DEG, WRONG_CHAR_ROT_DEG + 1, 5):
        a = math.radians(deg)
        ca, sa = math.cos(a), math.sin(a)
        turned = [(cx + (x - cx) * ca - (y - cy) * sa,
                   cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]
        u = _resample_path(_normalize_uniform([turned])[0])
        for cand in (u, u[::-1]):
            d = sum(math.dist(q, t) for q, t in zip(cand, tmpl)) / len(tmpl)
            best = min(best, d)
    return best


def jamo_shape_failed(strokes: List[Dict], target_char: str) -> Optional[bool]:
    """낱자의 **모양** 세부 판정 — 표준과 짝지은 획의 최대 모양 거리가 SHAPE_FAIL_DIST를 넘는가.

    낱자이고 획 수가 표준과 같을 때만 판정한다(None = 미측정). 획을 합쳐 쓰면 짝이 안
    맞는 획끼리 견주게 되어 뜻이 없다 — 그 경우는 획순 축이 획 수로 지적한다.
    음절은 짜임새 축이 성분 단위로 보므로 여기서 재지 않는다.
    """
    if decompose_syllable(target_char) is not None:
        return None
    if target_char in CHOSUNG:
        template_paths = _consonant_paths(target_char)
    elif target_char in JUNGSUNG:
        template_paths = _vowel_paths(target_char)
    else:
        return None
    user_paths = [[(p["x"], p["y"]) for p in st["points"]] for st in strokes if st["points"]]
    if len(user_paths) != len(template_paths):
        return None
    tmpl = [_resample_path(path) for path in _normalize_uniform(template_paths)]
    if len(tmpl) == 1:
        return _single_stroke_shape_distance(user_paths[0], tmpl[0]) > SHAPE_FAIL_DIST
    user = [_resample_path(path) for path in _normalize_uniform(user_paths)]
    worst = max((d for d, _, _ in _pair_strokes_by_shape(user, tmpl)), default=0.0)
    return worst > SHAPE_FAIL_DIST


def _segment_angles(path: List[Tuple[float, float]], min_len: float
                    ) -> List[Tuple[float, float]]:
    """폴리라인의 마디마다 (각도[도], 길이). 너무 짧은 마디는 각도가 튀므로 뺀다."""
    out = []
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln >= min_len:
            out.append((math.degrees(math.atan2(dy, dx)), ln))
    return out


def estimate_char_rotation(strokes: List[Dict], target_char: str) -> Optional[float]:
    """**글자를 통째로 몇 도 기울여 썼는가**(도). 양수 = 오른쪽으로 기운 이탤릭.

    획을 표준 획과 짝지은 뒤, **마디(segment)마다** 각도가 표준에서 몇 도 틀어졌는지
    모아 **중앙값**을 쓴다. 왜 이렇게까지 하는가:

    ① 글자 전체를 돌려 가며 제일 잘 맞는 각을 찾는 방식은 **가로세로 비율에
       속는다.** ㅏ를 표준보다 넓게 쓰면 "18도 기울여 썼다"가 나왔다 — 화면 가이드
       자체가 자모를 칸에 맞춰 늘려 그리므로 그대로 따라 쓰면 걸린다(2026-09-17 실측).
       마디 각도는 축 방향 늘림에 **덜** 흔들리고, 늘림이 만드는 편차는 가로 마디와
       세로 마디가 서로 반대로 나므로 중앙값에서 상쇄된다.
    ② 획 단위로만 보면 ㄱ·ㄴ처럼 **꺾인 한 획짜리** 자모를 못 본다. 마디로 쪼개면
       가로 부분과 세로 부분을 따로 보게 되어 ㄱ을 30도 기울인 것도 잡힌다.
    ③ 평균이 아니라 중앙값인 이유는, 한 마디를 삐끗해도 판정이 통째로 흔들리면
       안 되기 때문이다(이 저장소에서 반복해 쓰는 원칙).

    낱자(자음·모음 연습)에서만 쓴다. 음절은 성분을 놓는 자리가 따로 있어서
    "기울여 썼다"와 "성분을 엉뚱한 데 놨다"가 한 각도로 섞인다.
    """
    if not strokes or decompose_syllable(target_char) is not None:
        return None
    if target_char in CHOSUNG:
        template_paths = _consonant_paths(target_char)
    elif target_char in JUNGSUNG:
        template_paths = _vowel_paths(target_char)
    else:
        return None
    if not template_paths:
        return None

    user_paths = [[(p["x"], p["y"]) for p in st["points"]] for st in strokes]
    if any(len(path) < 2 for path in user_paths):
        return None
    # 획을 합쳐 쓰거나 나눠 쓰면 아래 짝짓기가 성립하지 않는다 — 합친 획을 표준 획
    # 하나와 마디끼리 견주게 되어 엉뚱한 각이 나온다(한 획에 쓴 ㄷ = "70도 기울어짐",
    # ㅁ = "90도"). 그럴 땐 재지 않는다. 획 수가 다른 것은 획순 항목이 지적한다.
    if len(user_paths) != len(template_paths):
        return None
    tmpl = [_resample_path(path) for path in _normalize_uniform(template_paths)]
    user = [_resample_path(path) for path in _normalize_uniform(user_paths)]

    # 짝짓기는 회전을 허용해서 한다 — 기울여 쓴 획이 엉뚱한 표준 획에 붙으면
    # 각도 차이가 통째로 무의미해진다.
    diffs: List[Tuple[float, float]] = []
    min_len = 1.0 / (WRONG_CHAR_SAMPLES * 3)      # 전체 크기가 1이므로 마디 평균의 1/3
    for _, i, j in _pair_strokes_by_shape(user, tmpl):
        # 거꾸로 그은 획은 뒤집어서 같은 방향으로 놓고 본다(획방향은 다른 항목의 몫).
        forward = sum(math.dist(p, q) for p, q in zip(user[i], tmpl[j]))
        backward = sum(math.dist(p, q) for p, q in zip(user[i][::-1], tmpl[j]))
        u_path = user[i] if forward <= backward else user[i][::-1]
        u_seg = _segment_angles(u_path, min_len)
        t_seg = _segment_angles(tmpl[j], min_len)
        if len(u_seg) != len(t_seg):
            continue          # 마디 수가 다르면 짝이 어긋난다 — 건너뛴다
        for (ua, ul), (ta, tl) in zip(u_seg, t_seg):
            d = (ua - ta + 90.0) % 180.0 - 90.0     # 축 기준 (-90, 90]
            diffs.append((d, min(ul, tl)))

    if len(diffs) < 2:
        return None
    # 긴 마디일수록 각도가 믿을 만하므로 길이를 가중치로 둔다.
    diffs.sort()
    total = sum(w for _, w in diffs)

    def quantile(q: float) -> float:
        acc = 0.0
        for d, w in diffs:
            acc += w
            if acc >= total * q:
                return d
        return diffs[-1][0]

    # ⚠️ 중앙값 하나로 정하면 **모양이 다른 것**을 기울기로 오해한다. 표준 ㄱ은 내리긋는
    # 부분이 비스듬한데, 그걸 수직으로 곧게 내려 쓰면 마디의 절반이 -19도가 되어
    # 중앙값도 -19도 = "글자 전체가 19도 기울어짐"이 나왔다(세로로 똑바로 쓴 글씨다).
    # 통째로 기울인 글씨는 **거의 모든 마디가 같은 쪽으로** 돈다. 그래서 아래위 사분위가
    # 같은 쪽일 때만 기울었다고 보고, 둘 중 작은 쪽을 기울기로 삼는다.
    lo, hi = quantile(0.25), quantile(0.75)
    if lo * hi <= 0:
        return 0.0
    return round(float(min(lo, hi, key=abs)), 1)


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

    # ⚠️ "목표 글자를 쓴 게 맞는가"는 여기서 판단하지 않는다 — assess_character_match가
    # analyze_canvas_writing 앞단에서 한 번만 보고, 아니면 채점 자체를 건너뛴다.
    # 종전에는 이 자리에서 매칭 거리로 판단했는데, 그 거리는 곧은 획을 10°만 기울여도
    # 최대값이 되어 **기울기를 지적해야 할 글씨를 "딴 글자"로 빠뜨렸다**(2026-09-17).

    # 감점 없이 허용되는 순서(표준 + 논쟁 자모의 대안 필순) 중 오류가 가장 적은 것을 채택.
    # best[i] = i번째로 그린 획이 있어야 할 canonical 인덱스. matched_indices[i]가 이와
    # 다르면 순서 오류. _acceptable_orders는 표준을 먼저 넣으므로 동점이면 표준을 택한다.
    acceptable = _acceptable_orders(target_char)
    best_seq, best_alts = min(acceptable, key=lambda t: _order_mismatches(matched_indices, t[0]))

    # 획을 합쳐 써서 **획 수가 모자란 것도 획순 오류**다. 종전에는 그린 자리가 기대와
    # 다른 획만 셌는데, 마지막 두 획을 합치면 앞 획들은 전부 제자리라 오류가 0건이었다
    # (ㅁ을 2획에 써도 획순 만점). 합친 획은 '순서 어긋남'과 '획 수 부족'이 같은 사건이라
    # 두 번 세지 않고 큰 쪽을 쓴다. 여분 획은 _order_mismatches가 이미 센다.
    # 축 채점용: 기대 순서와 다른 **그린 자리** 수(표준 길이 안에서만 — 여분 획은 획 수로 센다).
    order_error_count = sum(1 for i, m in enumerate(matched_indices)
                            if i < len(best_seq) and m != best_seq[i])
    missing = max(0, len(canonical) - len(strokes))
    error_count = max(_order_mismatches(matched_indices, best_seq), missing)
    corrections: List[str] = []
    # 자모 블록별 오류 수 — 성분 박스가 "이 성분에서 순서가 틀렸나"를 이걸로 본다.
    order_per_block: Dict[int, int] = {}
    specs = _canonical_stroke_specs(target_char)
    # 획 수가 표준과 다른 자모 블록 → (쓴 획 수, 표준 획 수). 여분 획이 있으면 어느
    # 자모 것인지 알 수 없어 비워 둔다(글자 단위 사유로만 나간다).
    count_per_block: Dict[int, Tuple[int, int]] = {}
    if -1 not in matched_indices:
        for blk in {spec[0] for spec in specs}:
            n_expected = sum(1 for spec in specs if spec[0] == blk)
            n_actual = sum(1 for m in matched_indices if specs[m][0] == blk)
            if n_actual != n_expected:
                count_per_block[blk] = (n_actual, n_expected)
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
        "order_error_count": order_error_count,
        "likely_wrong_character": False,
        "used_alternative_order": bool(best_alts),
        "notes": notes,
        "corrections": corrections,
        "per_block": order_per_block,
        "stroke_count": len(strokes),
        "expected_count": len(canonical),
        "count_per_block": count_per_block,
    }


def analyze_stroke_direction(strokes: List[Dict], bbox: Dict,
                             target_char: str) -> Optional[Dict]:
    """각 획을 **올바른 방향으로 그었는가**.

    표준 획 템플릿은 점 순서를 가진 경로라 방향 정보를 이미 담고 있다 — 새 데이터가
    필요 없다. 사용자 획의 시작→끝 벡터와 매칭된 표준 획의 벡터가 이루는 각도를 본다.

      135° 미만  → 정상
      135° 이상  → 역방향(오류 1건)  예: 'ㄱ'을 아래에서 위로 그은 경우

    **기울기는 여기서 안 본다**(사용자 결정 2026-09-01). 30도 비스듬해도 진행 방향이
    맞으면 통과다 — 곧게 그어야 하는 획의 기울기는 analyze_stroke_tilt가 따로
    STRAIGHT_STROKE_MAX_TILT_DEG 기준으로 잡는다. 한 항목에 섞으면 두 가지를 구분해 설명할 수 없다.

    ㅇ처럼 시작점과 끝점이 겹치는 닫힌 획은 방향을 논할 수 없어 세지 않는다.
    잴 수 있는 획이 하나도 없으면 None(미측정)이다.
    """
    match = _match_strokes(strokes, bbox, target_char)
    specs, matched = match["specs"], match["matched"]
    if not specs or not matched:
        return None

    tmpl_paths = _template_paths_in_pixels(target_char, bbox)
    reliable = _reliable_blocks(specs, matched)
    checked = 0
    errors = 0.0
    corrections: List[str] = []
    per_block: Dict[int, int] = {}   # 자모 블록별 오류 수 — 성분 박스 색이 이걸 쓴다
    for i, m in enumerate(matched):
        if m == -1 or specs[m][0] not in reliable:
            continue                      # 획 수가 표준과 다른 자모 — 획순 쪽에서 지적한다
        expected_dir = _path_direction(tmpl_paths[m])
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


def _stroke_length(stroke: Dict, bbox: Dict) -> float:
    """획의 **시작점→끝점 직선 거리**를 글자 크기(테두리 긴 변)로 나눈 값.

    ⚠️ 지나온 궤적 길이를 재면 안 된다 — 손이 떨릴수록 지그재그가 더해져 길이가
    늘어나는데, 정작 각도는 그럴수록 불안정해진다. 실제로 ㅎ의 동그라미가 4.9,
    ㅊ의 짧은 머리획이 0.57로 나와 "짧은 획 걸러내기"가 헛돌았다(2026-09-17).
    각도를 정하는 것은 시작점과 끝점이므로 그 거리로 재야 잣대가 맞는다.
    """
    pts = stroke.get("points") or []
    if len(pts) < 2:
        return 0.0
    span = math.dist((pts[0]["x"], pts[0]["y"]), (pts[-1]["x"], pts[-1]["y"]))
    scale = max(bbox.get("width") or 0.0, bbox.get("height") or 0.0) or 1.0
    return span / scale


def analyze_stroke_tilt(strokes: List[Dict], bbox: Dict,
                        target_char: str) -> Optional[Dict]:
    """**곧게 그어야 하는 획을 곧게 그었는가** — 기울기 판정 (2026-09-01 신설).

    'ㅣ'는 일자로, 'ㅡ'는 수평으로 써야 한다. 그런데 이런 자모는 폭(또는 높이)이
    0에 가까워서 **성분비율의 종횡비로 재면 안 된다** — 10도만 기울어도 비율이
    442배로 튀어 과잉 판정이 나고, 반대로 몇 도 기울었는지는 설명할 수 없다
    (2026-09-01 실측). 그래서 표준 획이 수평·수직인 것만 골라 **각도를 직접** 잰다.

    표준 각도에서 STRAIGHT_STROKE_MAX_TILT_DEG를 넘게 어긋나면 오류.
    사선 획(ㅅ·ㅈ의 삐침 등)과 **꺾인 획**(ㄱ·ㄴ 모양)은 애초에 곧게 그을 획이 아니라
    대상에서 뺀다. 꺾인 획은 시작→끝 벡터가 우연히 축에 가까울 뿐이다 — 종전에는 그
    벡터만 보고 ㄹ의 끝획을 '곧은 획'으로 쟀다.
    """
    match = _match_strokes(strokes, bbox, target_char)
    specs, matched = match["specs"], match["matched"]
    if not specs or not matched:
        return None

    tmpl_paths = _template_paths_in_pixels(target_char, bbox)
    reliable = _reliable_blocks(specs, matched)
    checked = 0
    errors = 0
    corrections: List[str] = []
    per_block: Dict[int, int] = {}
    worst = 0.0
    for i, m in enumerate(matched):
        if m == -1 or specs[m][0] not in reliable:
            continue
        if not _is_straight_path(tmpl_paths[m]):
            continue                      # 꺾인 획이거나 닫힌 획(ㅇ)
        expected_dir = _path_direction(tmpl_paths[m])
        if expected_dir is None or not _is_straight_axis(expected_dir):
            continue                      # 원래 사선인 획
        actual_dir = _stroke_direction(strokes[i])
        if actual_dir is None:
            continue
        # ⚠️ **짧은 획은 각도를 재지 않는다.** ㅊ·ㅎ의 머리 점이나 ㅋ의 짧은 가로처럼
        # 길이가 짧으면 손이 조금만 떨려도 각도가 수십 도씩 흔들린다 — 표준대로 쓴
        # 글자에 "기울어졌다"가 붙었다(2026-09-17 실측: ㅊ·ㅋ·ㅎ가 떨림 ±2%에서 오탐).
        span = _stroke_length(strokes[i], bbox)
        if span < TILT_MIN_STROKE_LEN:
            continue
        checked += 1
        # 0~180 축 각도끼리 비교하되 179도와 1도가 2도 차이가 되도록 감싼다.
        diff = abs(_axis_angle_deg(actual_dir) - _axis_angle_deg(expected_dir))
        tilt = min(diff, 180.0 - diff)
        worst = max(worst, tilt)
        tol = min(TILT_MAX_TOL_DEG,
                  STRAIGHT_STROKE_MAX_TILT_DEG * max(1.0, TILT_FULL_STROKE_LEN / span))
        if tilt > tol:
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


def _canonical_stroke_paths(target_char: str) -> List[List[Tuple[float, float]]]:
    """기대 획의 **폴리라인**을 _canonical_stroke_specs와 **같은 순서로** 반환한다.

    specs는 획을 (중심·크기·방향)으로 줄여 놓아서 모서리를 볼 수 없다. 매칭 결과
    (matched)를 그대로 쓰려면 순서가 같아야 하므로 같은 레이아웃에서 같이 만든다.
    """
    layout = _layout_for_char(target_char)
    if not layout:
        return []
    frame = _union_box([_path_ink_box(p) for _, paths in layout for p in paths])
    return [[_renormalize_point(pt, frame) for pt in path]
            for _, paths in layout for path in paths]


def _drawn_in_reverse(user: List[Tuple[float, float]],
                      template: List[Tuple[float, float]]) -> bool:
    """사용자가 이 획을 표준과 반대 방향으로 그었나. 두 경로는 같은 좌표계여야 한다."""
    u = _resample_path(user)
    t = _resample_path(template)
    forward = sum(math.dist(p, q) for p, q in zip(u, t))
    backward = sum(math.dist(p, q) for p, q in zip(u[::-1], t))
    return backward < forward


def _turn_profile(path: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """(호길이 비율, 꺾임각[도]) 목록.

    ⚠️ 이웃한 두 점으로 각을 재면 손떨림이 그대로 꺾임으로 잡힌다. CORNER_BASELINE
    만큼 떨어진 점을 기준선으로 써서 **넓게** 본다 — 그래야 진짜 모서리만 솟는다.
    """
    pts = _resample_path(path, CORNER_SAMPLES)
    k = CORNER_BASELINE
    out = []
    for i in range(k, CORNER_SAMPLES - k):
        ax, ay = pts[i][0] - pts[i - k][0], pts[i][1] - pts[i - k][1]
        bx, by = pts[i + k][0] - pts[i][0], pts[i + k][1] - pts[i][1]
        if math.hypot(ax, ay) < 1e-9 or math.hypot(bx, by) < 1e-9:
            continue
        ang = abs(math.degrees(math.atan2(ax * by - ay * bx, ax * bx + ay * by)))
        out.append((i / (CORNER_SAMPLES - 1), ang))
    return out


def _template_corners(path: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """표준 폴리라인의 꼭짓점 = (호길이 비율, 꺾임각).

    ⚠️ **양쪽 변이 모두 수평·수직인 모서리만** 센다. 가이드는 자모를 성분 칸에 맞춰
    가로세로 따로 늘리는데, 그러면 사선끼리 이루는 각은 달라지지만 직각은 그대로다.
    사선 모서리까지 보면 "칸에 맞춰 늘어난 것"을 둥글다고 오해한다.
    """
    segs = [math.dist(a, b) for a, b in zip(path, path[1:])]
    total = sum(segs)
    if total <= 0:
        return []
    out = []
    for i in range(1, len(path) - 1):
        a = (path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        b = (path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
        if not (_is_straight_axis(a) and _is_straight_axis(b)):
            continue
        ang = abs(math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0],
                                          a[0] * b[0] + a[1] * b[1])))
        if ang >= CORNER_MIN_ANGLE_DEG:
            out.append((sum(segs[:i]) / total, ang))
    return out


def analyze_corner_sharpness(strokes: List[Dict], bbox: Dict,
                             target_char: str) -> Optional[Dict]:
    """**각지게 꺾어야 할 모서리를 각지게 꺾었는가** (2026-09-18 신설).

    ㄷ·ㄹ·ㅁ의 직각 모서리를 둥글게 돌려 쓰면 글씨가 통째로 둥글둥글해지는데,
    종전 항목은 하나도 이걸 보지 않았다(사용자 신고: '달'이 80점).
    """
    match = _match_strokes(strokes, bbox, target_char)
    specs, matched = match["specs"], match["matched"]
    # 꼭짓점 위치(호길이 비율)를 사용자 획과 같은 공간에서 재야 한다.
    tmpl_paths = _template_paths_in_pixels(target_char, bbox)
    if not specs or not matched or len(tmpl_paths) != len(specs):
        return None

    reliable = _reliable_blocks(specs, matched)
    checked = 0
    errors = 0
    corrections: List[str] = []
    per_block: Dict[int, int] = {}
    worst = 1.0
    for i, m in enumerate(matched):
        if m == -1 or specs[m][0] not in reliable:
            continue
        tmpl_corners = _template_corners(tmpl_paths[m])
        if not tmpl_corners:
            continue
        pts = [(p["x"] - bbox["x"], p["y"] - bbox["y"]) for p in strokes[i]["points"]]
        if len(pts) < CORNER_MIN_POINTS:
            # 점이 몇 개 없으면 모양이랄 게 없다. 문턱을 낮게 잡아도 안전한 이유:
            # _resample_path는 점 사이를 **직선으로** 채우므로, 점이 적을수록 모서리가
            # 더 각져 보인다 — 오탐(둥글다고 잘못 잡기)이 아니라 미탐 쪽으로 기운다.
            continue
        profile = _turn_profile(pts)
        if not profile:
            continue
        # 거꾸로 그은 획은 꼭짓점이 호길이로 반대편에 온다 — 뒤집어서 찾는다. 안 그러면
        # 획방향으로 이미 지적한 실수에 "모서리를 둥글게 돌림"이 한 번 더 붙는다.
        reverse = _drawn_in_reverse(pts, tmpl_paths[m])
        for frac, exp_ang in tmpl_corners:
            if reverse:
                frac = 1.0 - frac
            near = [t for g, t in profile if abs(g - frac) <= CORNER_WINDOW]
            if not near:
                continue
            checked += 1
            ratio = max(near) / exp_ang
            worst = min(worst, ratio)
            if ratio < CORNER_SHARP_MIN_RATIO:
                errors += 1
                per_block[specs[m][0]] = per_block.get(specs[m][0], 0) + 1
                corrections.append(
                    f"{i + 1}번째 획('{specs[m][1]}')의 모서리를 둥글게 돌렸습니다. "
                    f"꺾이는 자리에서 한 번 멈췄다가 각지게 꺾어보세요.")

    if checked == 0:
        return None
    return {
        "checked": checked,
        "error_count": errors,
        "min_sharpness": round(worst, 2),
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


def _line_lengths(exp_box: Tuple[float, float, float, float],
                  act_box: Tuple[float, float, float, float]
                  ) -> Optional[Tuple[float, float]]:
    """기대 상자가 선에 가까운 자모(ㅣ·ㅡ)면 **긴 축**의 (기대 길이, 실제 길이). 아니면 None."""
    ex0, ey0, ex1, ey1 = exp_box
    if min(ex1 - ex0, ey1 - ey0) >= _ASPECT_MIN_SIDE:
        return None
    horizontal = (ex1 - ex0) >= (ey1 - ey0)
    ax0, ay0, ax1, ay1 = act_box
    exp_len = (ex1 - ex0) if horizontal else (ey1 - ey0)
    act_len = (ax1 - ax0) if horizontal else (ay1 - ay0)
    return max(exp_len, 1e-3), act_len


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
            # ⚠️ 선형 자모(ㅣ·ㅡ)는 배율을 **넓이로 재면 안 된다** — 기대 넓이가 0에
            # 가까워 손떨림 1%에도 배율이 수십 배로 튄다. 받침 없는 '시·기·이·으'는
            # 성분이 둘뿐이라 그 값이 곧 전체 배율이 되어, 멀쩡한 초성과 모음이 둘 다
            # '너무 작음'으로 빨개졌다(실측 20/20). 아래 판정과 같은 잣대(긴 축 길이)를
            # 넓이 배율로 환산해 쓴다.
            line = _line_lengths(expected[block_idx][1], act_box)
            if line:
                ratios.append((line[1] / line[0]) ** 2)
            else:
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
        line = _line_lengths(exp_box, act_box)
        degenerate = line is not None
        if line:
            aspect_dev = 0.0
            exp_len = line[0]
            act_len = line[1] / math.sqrt(scale)
            # 허용치는 **넓이 기준 숫자**라 길이에 그대로 쓰면 두 배로 헐거워진다
            # (±45% 넓이 = 한 변 ±20%). 길이에는 제곱근으로 환산해서 쓴다.
            tol_len = math.sqrt(1.0 + tol_area) - 1.0
            area_dev = min(1.0, abs(act_len - exp_len) / exp_len / tol_len)
            # 아래 사유 문구가 act_area/exp_area로 크고 작음을 가르므로 같이 맞춘다.
            act_area, exp_area = act_len, exp_len
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
                          corner_result: Optional[Dict] = None,
                          size_failed: bool = False,
                          position_failed: bool = False) -> Optional[List[Dict]]:
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
    count_per_block = (stroke_order_result or {}).get("count_per_block") or {}
    dir_per_block = (direction_result or {}).get("per_block") or {}
    tilt_per_block = (tilt_result or {}).get("per_block") or {}
    corner_per_block = (corner_result or {}).get("per_block") or {}

    boxes: List[Dict] = []
    for comp in balance_result["components"]:
        b = comp["block"]
        # 사유는 축 단위로 묶는다 — 화면이 같은 이름으로 읽을 수 있도록(설계 6절).
        order_reasons: List[str] = []
        if b in count_per_block:
            drawn, expected = count_per_block[b]
            order_reasons.append(f"획 수 {drawn}개 / 표준 {expected}개")
        elif order_per_block.get(b) and not count_per_block:
            # 어느 성분이든 획 수가 다르면 그 뒤 짝이 밀려 멀쩡한 성분에도 '순서 틀림'이
            # 따라붙는다('닥'의 ㄷ을 한 획에 쓰면 ㅏ·ㄱ이 빨강). 글자 축과 같은 규칙으로
            # 획 수가 다른 글자에서는 순서 어긋남을 싣지 않는다.
            order_reasons.append(f"{-(-order_per_block[b] // 2)}획 순서 틀림")
        if dir_per_block.get(b):
            order_reasons.append(f"{dir_per_block[b]}획 반대로 그음")
        shape_reasons: List[str] = []
        if tilt_per_block.get(b):
            shape_reasons.append(f"{tilt_per_block[b]}획 기울어짐")
        if corner_per_block.get(b):
            shape_reasons.append(f"모서리 {corner_per_block[b]}곳 둥글림")
        balance_reasons = (["·".join(comp.get("balance_reasons") or [])]
                           if comp["balance_failed"] else [])
        # 크기·위치는 글자 전체 항목이라 그 글자의 **모든 성분**에 걸린다.
        # 성분 탓으로 오해되지 않도록 "글자 전체"라고 못박는다.
        layout_reasons: List[str] = []
        if size_failed:
            layout_reasons.append("크기(글자 전체)")
        if position_failed:
            layout_reasons.append("위치(글자 전체)")
        reasons = [axis_label(axis, rs) for axis, rs in (
            (AXIS_ORDER, order_reasons), (AXIS_SHAPE, shape_reasons),
            (AXIS_BALANCE, balance_reasons), (AXIS_LAYOUT, layout_reasons)) if rs]
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
    char_positions: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    SFR-005C 종합 분석 — 네 축(획순 · 모양 · 짜임새 · 배치).

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

    char_positions : 문장 연습에서 화면에 보여준 글자별 칸 {x, y, width, height}.
                  글자 수와 맞을 때만 쓴다(배치 축의 자간·위치 기준).

    Returns
    -------
    List[Dict] — char_id별 {axes, overall_score, scorable, unscorable_reason, failed_items,
                 component_boxes, stroke_order_result, direction_result, tilt_result,
                 corner_result, balance_result, char_rotation_deg, spacing_deviation,
                 size_deviation, size_fill_ratio, position_result, speed_profile,
                 correction_flags, corrections, character_match}

    axes = {축: {"score": 100|70|40|None, "reasons": [...]}} — None은 미측정이다.
    문장에서 채점을 거부한 글자는 overall_score 0, 낱자·한 글자는 None(세션 채점 불가).
    """
    if not char_groups:
        return []

    # 글자 크기는 **테두리의 긴 변**으로 잰다. 높이만 보면 '으·그·스'처럼 원래 납작한
    # 글자가 표준대로 써도 "너무 작음"이 된다(실측: 문장 속 '으'가 매번 -20).
    sizes  = [max(g["bounding_box"]["width"], g["bounding_box"]["height"]) for g in char_groups]
    widths = [g["bounding_box"]["width"] for g in char_groups]
    median_size = sorted(sizes)[len(sizes) // 2]
    mean_w   = sum(widths) / len(widths)
    multi_char = len(char_groups) > 1
    # 글자 칸은 글자 수와 맞을 때만 쓴다 — 어긋난 칸으로 재면 뒤 글자가 전부 밀린다.
    positions = (char_positions
                 if char_positions and len(char_positions) == len(char_groups) else None)

    guide_area = None
    if guide_box:
        guide_area = (guide_box.get("width", 0.0) or 0.0) * (guide_box.get("height", 0.0) or 0.0)
        if guide_area <= 0:
            guide_area = None

    results: List[Dict] = []
    for i, group in enumerate(char_groups):
        bb = group["bounding_box"]
        correction_flags: List[str] = []
        target_char = target_text[i] if (target_text and i < len(target_text)) else None

        # ── 목표 글자를 쓴 게 맞는가 (설계 5절) ──────────────────────────
        # 아니면 점수를 매기지 않는다 — 엉뚱한 글씨에 점수를 주면 잘 썼다는 신호가 된다.
        # 문장에서는 **그 글자만 0점**으로 넣고 나머지는 정상 채점한다(그 글자만 빼고
        # 평균을 내면 점수가 오르던 문제가 0점으로 넣으면 생기지 않는다). 낱자·한 글자는
        # 글자가 하나뿐이라 세션 채점 불가(None)다.
        assessment = assess_character_match(group["strokes"], target_char) if target_char else None
        if assessment and not assessment["scorable"]:
            reason = assessment["reason"]
            detail = {"too_many_strokes": "획이 너무 많음",
                      "missing": "쓰지 않음"}.get(reason, "목표 글자와 다름")
            label = f"다시 써 주세요({detail})"
            # 사유를 플래그로도 남긴다 — DB에 unscorable_reason 컬럼이 없어서, 거부된 기록을
            # 나중에 봐도 왜 거부됐는지 알 길이 없었다(2026-09-21). 잉크 어긋남 값도 같이 —
            # 문턱값을 조정할 때 실제 분포를 봐야 한다.
            correction_flags += ["unscorable", f"unscorable:{reason}"]
            if assessment.get("ink_gap") is not None:
                correction_flags.append(f"ink_gap:{assessment['ink_gap']}")
            results.append({
                "char_id": group["char_id"],
                "stroke_order_result": None, "direction_result": None, "tilt_result": None,
                "corner_result": None, "balance_result": None, "char_rotation_deg": None,
                # 문장은 어느 글자가 문제인지 보여야 하므로 글자 박스를 친다.
                # 낱자·한 글자는 화면에 글자가 하나뿐이라 문구로 충분하다.
                "component_boxes": ([{
                    "block": 0, "jamo": target_char, "role": "글자",
                    "box": {"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["height"]},
                    "ok": False, "failed_items": [label],
                }] if multi_char else None),
                "spacing_deviation": None, "size_deviation": None, "size_fill_ratio": None,
                "position_result": None,
                "axes": {axis: {"score": None, "reasons": []} for axis in ALL_AXES},
                "speed_profile": {"mean_speed_px_per_ms":
                                  _stroke_speed_stats(group["strokes"])["mean_speed_px_per_ms"]},
                "overall_score": 0 if multi_char else None,
                "scorable": False,
                "unscorable_reason": reason,
                "failed_items": [label],
                "correction_flags": correction_flags,
                "character_match": assessment,
                "corrections": [label],
            })
            continue

        # ── 크기 (배치 축, 문장에서만) ──────────────────────────────────
        # 정본은 **표준 자형 대비 크기 배율**(절대 기준)이다. 가이드 박스와 목표 글자를
        # 둘 다 알아야 잰다. 없으면 세션 안 글자들의 긴 변 중앙값 대비로 폴백한다.
        # ★ 크기는 **문장(글자 2개 이상)에서만** 잰다(사용자 결정 2026-09-01) — 글자
        # 하나만 쓸 때 "얼마나 크게 썼나"는 임의값이다.
        # size_reason: None=미측정 / ""=통과 / 그 외=걸린 사유.
        size_fill_ratio = None
        size_reason: Optional[str] = None
        if multi_char and guide_area and target_char:
            ref_fill = template_ink_fill(target_char)
            if ref_fill:
                actual_fill = (bb["width"] * bb["height"]) / guide_area
                size_fill_ratio = round(actual_fill / ref_fill, 3)
                size_reason = ("너무 작음" if size_fill_ratio < SIZE_REL_MIN_OK
                               else "너무 큼" if size_fill_ratio > SIZE_REL_MAX_OK else "")

        # 상대 편차는 가이드가 없을 때의 폴백이자, 글자끼리 크기가 고른지를 보는 값.
        size_deviation_pct = None
        if multi_char:
            size = max(bb["width"], bb["height"])
            size_ratio = (size / median_size) if median_size > 0 else 1.0
            size_deviation_pct = round((size_ratio - 1.0) * 100.0, 1)
            if size_reason is None:
                size_reason = ("너무 큼" if size_ratio > SIZE_LARGE_THRESH
                               else "너무 작음" if size_ratio < SIZE_SMALL_THRESH else "")
        size_failed = bool(size_reason)
        if size_reason:
            correction_flags.append("size_small" if "작음" in size_reason else "size_large")

        # ── 자간 (배치 축, 이전 글자와의 간격) ───────────────────────────
        # 글자가 하나뿐인 연습에서는 비교할 옆 글자가 없다(None = 미측정).
        spacing_reason: Optional[str] = None
        spacing_deviation_px = None
        if i > 0:
            prev_bb = char_groups[i - 1]["bounding_box"]
            guide_pitch = _guide_pitch(positions, i)
            if guide_pitch:
                # 화면에 글자 자리를 보여준 연습은 **그 자리가 곧 표준 자간**이다.
                # '평균 글자폭의 40%'라는 자유 필기 기준을 그대로 쓰면, 회색 글씨 위에
                # 정확히 따라 쓴 글씨가 "자간이 좁다"가 된다(가이드 글자끼리는 거의
                # 붙어 있다). 글자 중심 사이 거리를 가이드의 그것과 견준다 — 잉크
                # 테두리는 글자 모양마다 달라 간격으로 재면 '이'와 '한'이 다르게 나온다.
                pitch, cell_w = guide_pitch
                actual = ((bb["x"] + bb["width"] / 2.0)
                          - (prev_bb["x"] + prev_bb["width"] / 2.0))
                spacing_deviation_px = round(actual - pitch, 1)
                dev_ratio = (actual - pitch) / cell_w
                # 허용 폭은 자유 필기와 같게 둔다(기준에서 -25% / +80%).
                too_narrow = dev_ratio < SPACING_MIN_RATIO - SPACING_EXPECTED_RATIO
                too_wide = dev_ratio > SPACING_MAX_RATIO - SPACING_EXPECTED_RATIO
            else:
                gap = bb["x"] - (prev_bb["x"] + prev_bb["width"])
                expected_gap = mean_w * SPACING_EXPECTED_RATIO
                spacing_deviation_px = round(gap - expected_gap, 1)
                gap_ratio = gap / mean_w if mean_w > 0 else 0.0
                too_narrow = gap_ratio < SPACING_MIN_RATIO
                too_wide = gap_ratio > SPACING_MAX_RATIO
            spacing_reason = ("앞 글자와 너무 좁음" if too_narrow
                              else "앞 글자와 너무 넓음" if too_wide else "")
            if too_narrow:
                correction_flags.append("spacing_too_narrow")
            elif too_wide:
                correction_flags.append("spacing_too_wide")

        # ── 획순 · 모양 · 짜임새의 세부 측정 (target_text가 있을 때만) ────
        # 전부 목표 글자를 알아야 잴 수 있다. 모르면 None으로 두고 축도 미측정이 된다.
        stroke_order_result = None
        direction_result = None
        tilt_result = None
        corner_result = None
        balance_result = None
        char_rotation_deg = None
        shape_failed: Optional[bool] = None
        # 표준을 모르는 글자(한글이 아님)는 획순·모양·짜임새를 잴 수 없다 — 미측정으로 둔다.
        if target_char and _layout_for_char(target_char):
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

            # 낱자는 획 단위 기울기만으로는 구멍이 난다 — 글자 전체 기울기를 더 본다.
            char_rotation_deg = estimate_char_rotation(group["strokes"], target_char)
            if char_rotation_deg is not None and abs(char_rotation_deg) > CHAR_ROT_MAX_DEG:
                correction_flags.append("char_rotation_error")

            corner_result = analyze_corner_sharpness(group["strokes"], bb, target_char)
            if corner_result and corner_result["error_count"] > 0:
                correction_flags.append("corner_rounded")

            balance_result = analyze_component_balance(group["strokes"], bb, target_char)
            if balance_result and balance_result["corrections"]:
                correction_flags.append("component_balance_error")

            # 낱자의 모양 — 음절은 짜임새가 성분 단위로 보므로 여기서는 재지 않는다.
            shape_failed = jamo_shape_failed(group["strokes"], target_char)
            if shape_failed:
                correction_flags.append("shape_off")

        # ── 위치 (배치 축, 문장에서만) ──────────────────────────────────
        # 프론트가 화면에 그려준 글자 칸을 보내준다. 그 칸을 벗어나 쓰면 잡는다.
        position_score = None
        position_failed: Optional[bool] = None
        if multi_char and positions:
            position_score, off = _position_check(bb, positions[i])
            if position_score is not None:
                position_failed = off
                if off:
                    correction_flags.append("position_off")

        # ── 축 점수 · 글자 점수 · 사유 (설계 3·4절) ────────────────────
        axes = build_axes(
            stroke_order_result=stroke_order_result, direction_result=direction_result,
            tilt_result=tilt_result, char_rotation_deg=char_rotation_deg,
            corner_result=corner_result, shape_failed=shape_failed,
            balance_result=balance_result, size_reason=size_reason,
            spacing_reason=spacing_reason, position_failed=position_failed)
        overall_score = overall_from_axes(axes)
        failed_items = [axis_label(axis, a["reasons"]) for axis, a in axes.items() if a["reasons"]]

        # ── 화면에 그릴 박스 (설계 6절) ─────────────────────────────────
        # 자모음: 없음 / 한 글자: 성분 박스(어느 성분인지가 핵심) / 문장: 글자 박스.
        if multi_char:
            component_boxes = [{
                "block": 0, "jamo": target_char or "", "role": "글자",
                "box": {"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["height"]},
                "ok": not failed_items, "failed_items": failed_items,
            }]
        elif target_char:
            component_boxes = build_component_boxes(
                group["strokes"], bb, target_char,
                stroke_order_result, direction_result, tilt_result,
                balance_result, corner_result=corner_result,
                size_failed=size_failed, position_failed=bool(position_failed))
        else:
            component_boxes = None

        # ── 속도 (채점 미반영, 기록만) ───────────────────────────────
        motion_stats = _stroke_speed_stats(group["strokes"])

        results.append({
            "char_id": group["char_id"],
            "stroke_order_result": stroke_order_result,
            "direction_result": direction_result,
            "tilt_result": tilt_result,
            "balance_result": balance_result,
            "component_boxes": component_boxes,
            "corner_result": corner_result,
            "char_rotation_deg": char_rotation_deg,
            "spacing_deviation": spacing_deviation_px,
            "size_deviation": size_deviation_pct,
            "size_fill_ratio": size_fill_ratio,
            "position_result": ({"score": position_score, "off": position_failed}
                                if position_score is not None else None),
            "axes": axes,
            "scorable": True,
            "unscorable_reason": None,
            "failed_items": failed_items,
            "character_match": assessment,
            "speed_profile": {"mean_speed_px_per_ms": motion_stats["mean_speed_px_per_ms"]},
            "overall_score": overall_score,
            "correction_flags": correction_flags,
        })

    return results
