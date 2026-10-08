# 캔버스 채점 축 재설계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캔버스 채점을 9개 항목에서 단계별로 더해 가는 네 축(획순·모양·짜임새·배치)으로 바꾸고, 축당 100/70/40 점수, 잉크 기준 채점 거부, 문장의 글자 단위 박스까지 AI·백엔드·앱 세 계층에 반영한다.

**Architecture:** AI(`ai/canvas/canvas_quality_analyzer.py`)의 세부 측정 함수는 그대로 두고 **결과 조립부만** 축 구조로 바꾼다. 백엔드는 `axes`를 그대로 전달하고 축 점수를 새 컬럼 `item_scores`에 저장하며, 피드백 문구 조립을 없앤다. 앱은 이미 서버가 내려주는 박스·사유를 그리므로 글자 이름 표기와 라벨만 손본다.

**Tech Stack:** Python 3.13(`C:\ai_venv`), FastAPI + SQLAlchemy 2 async + Alembic, Flutter(`C:\src\flutter`). 테스트는 `C:\ai_venv\Scripts\python.exe -m pytest ai/tests -q`, `flutter test`.

**Spec:** `docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md`

## Global Constraints

- 축 이름은 문자열 상수 `"획순"`, `"모양"`, `"짜임새"`, `"배치"` 그대로 쓴다(응답·DB·화면 공통). 영어 키를 따로 두지 않는다.
- 축 점수는 `100 / 70 / 40 / None`의 네 값만 있다(스펙 4절).
- 미측정은 `None`이다. 0이나 100으로 채우지 않는다(스펙 3절).
- 임계값 숫자는 바꾸지 않는다(스펙 2절). 상수는 축별로 묶어 `canvas_quality_analyzer.py` 상단 한 곳에 둔다.
- 이미지 모드 코드는 건드리지 않는다(REQ-005I-4).
- 저장소 안 `venv/`는 리눅스용이라 쓰지 않는다. 명령은 전부 `C:\ai_venv\Scripts\python.exe`로 실행한다. 한글 출력은 `PYTHONIOENCODING=utf-8`.
- 작업 트리에 2026-09-30 리뷰 수정분(미커밋 16개 파일)이 섞여 있으므로, 각 Task의 커밋 단계는 **사용자가 커밋을 요청했을 때** 그 Task의 파일만 `git add`해서 수행한다. 요청이 없으면 커밋하지 않고 다음 Task로 간다.

## Review Focus

스펙이 암시하지만 아래 Task의 테스트가 직접 다루지 않던 입력. 각 줄의 테스트를 그 코드를 가진 Task에 넣었다.

1. 목표 글자가 한글이 아닌 칸(예: `A`)에 획을 썼을 때 — 표준이 없으니 획순·모양·짜임새는 미측정이어야 하고, 배치만 채점돼야 한다. (Task 3)
2. 문장에서 **모든** 글자가 거부됐을 때 — 글자 점수가 전부 0이므로 문장 점수도 0이어야지 None이 되면 안 된다. (Task 3)
3. 한 글자 연습에 `guide_box`가 있어도 — 배치 축은 단계상 없으므로 None이어야 한다. (Task 3)
4. `/feedback`에서 글자별 `failed_items`가 비어 있고 점수가 100인 글자 — `feedback_message`는 빈 문자열이고 severity는 `good`이어야 한다. (Task 5)
5. `item_scores` 컬럼이 없는 이전 행(마이그레이션 전 데이터) — 대시보드 축 집계에서 조용히 빠지고 종합 점수는 집계돼야 한다. (Task 6)

---

### Task 1: 축 점수 조립 함수 `build_axes`

세부 측정 결과들을 받아 축별 `{score, reasons}`를 만드는 **순수 함수**를 먼저 만든다. `analyze_canvas_writing`는 Task 3에서 이 함수를 호출한다.

**Files:**
- Modify: `ai/canvas/canvas_quality_analyzer.py` (상수 구역 + 새 함수)
- Test: `ai/tests/test_canvas_axes.py` (새 파일)

**Interfaces:**
- Produces:
  ```python
  AXIS_ORDER = "획순"; AXIS_SHAPE = "모양"; AXIS_BALANCE = "짜임새"; AXIS_LAYOUT = "배치"
  ALL_AXES = (AXIS_ORDER, AXIS_SHAPE, AXIS_BALANCE, AXIS_LAYOUT)
  AXIS_SCORE_PASS, AXIS_SCORE_PARTIAL, AXIS_SCORE_SEVERE = 100, 70, 40

  def axis_score(n_failed: int, measured: bool) -> Optional[int]
  def build_axes(*, stroke_order_result, direction_result, tilt_result, char_rotation_deg,
                 corner_result, shape_failed: Optional[bool], balance_result,
                 size_reason: Optional[str], spacing_reason: Optional[str],
                 position_failed: Optional[bool]) -> Dict[str, Dict]
      # 반환: {축: {"score": int|None, "reasons": [str]}} — 네 축 모두 키가 있다
  def axis_label(axis: str, reasons: List[str]) -> str   # "모양(1획 기울어짐, 모서리 1곳 둥글림)"
  def overall_from_axes(axes: Dict[str, Dict]) -> Optional[int]   # 측정된 축 평균, 없으면 None
  ```
- Consumes: 기존 측정 함수의 반환 형식 — `stroke_order_result`에 Task 3에서 추가될 `order_error_count`와 기존 `stroke_count`/`expected_count`; `direction_result["error_count"]`, `tilt_result["checked"/"error_count"]`, `corner_result["checked"/"error_count"]`, `balance_result["components"][i]["balance_failed"/"balance_reasons"/"role"/"jamo"]`, 상수 `CHAR_ROT_MAX_DEG`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# ai/tests/test_canvas_axes.py
"""축 점수 조립(build_axes) — 세부 판정 건수 → 100/70/40, 미측정은 None."""
from ai.canvas.canvas_quality_analyzer import (
    AXIS_BALANCE, AXIS_LAYOUT, AXIS_ORDER, AXIS_SHAPE, ALL_AXES,
    axis_label, axis_score, build_axes, overall_from_axes,
)


def _axes(**kw):
    base = dict(stroke_order_result=None, direction_result=None, tilt_result=None,
                char_rotation_deg=None, corner_result=None, shape_failed=None,
                balance_result=None, size_reason=None, spacing_reason=None,
                position_failed=None)
    base.update(kw)
    return build_axes(**base)


def test_axis_score_levels():
    assert axis_score(0, measured=True) == 100
    assert axis_score(1, measured=True) == 70
    assert axis_score(2, measured=True) == 40
    assert axis_score(5, measured=True) == 40
    assert axis_score(0, measured=False) is None


def test_nothing_measured_gives_four_none_axes():
    axes = _axes()
    assert set(axes) == set(ALL_AXES)
    assert all(a["score"] is None and a["reasons"] == [] for a in axes.values())
    assert overall_from_axes(axes) is None


def test_order_axis_counts_swap_as_one():
    """두 획이 자리를 바꾼 것(어긋난 자리 2곳)은 1건이다 — 어긋난 자리 수 ÷ 2, 올림."""
    so = {"order_error_count": 2, "stroke_count": 4, "expected_count": 4, "error_count": 2}
    axes = _axes(stroke_order_result=so)
    assert axes[AXIS_ORDER]["score"] == 70
    assert axes[AXIS_ORDER]["reasons"] == ["1획 순서 틀림"]


def test_order_axis_adds_reversed_and_count():
    so = {"order_error_count": 0, "stroke_count": 3, "expected_count": 4, "error_count": 1}
    d = {"checked": 3, "error_count": 1}
    axes = _axes(stroke_order_result=so, direction_result=d)
    assert axes[AXIS_ORDER]["score"] == 40
    assert axes[AXIS_ORDER]["reasons"] == ["1획 반대로 그음", "획 수 3개 / 표준 4개"]


def test_shape_axis_merges_tilt_rotation_corner_shape():
    axes = _axes(tilt_result={"checked": 2, "error_count": 1},
                 char_rotation_deg=20.0, corner_result={"checked": 2, "error_count": 0},
                 shape_failed=False)
    assert axes[AXIS_SHAPE]["score"] == 40
    assert axes[AXIS_SHAPE]["reasons"] == ["1획 기울어짐", "글자 전체가 오른쪽으로 20도 기울어짐"]


def test_shape_axis_measured_but_clean_is_100():
    axes = _axes(tilt_result={"checked": 2, "error_count": 0})
    assert axes[AXIS_SHAPE]["score"] == 100
    assert axes[AXIS_SHAPE]["reasons"] == []


def test_balance_axis_counts_failed_components():
    comps = [{"role": "초성", "jamo": "ㄱ", "balance_failed": False, "balance_reasons": []},
             {"role": "중성", "jamo": "ㅏ", "balance_failed": True, "balance_reasons": ["자리가 벗어남"]},
             {"role": "종성", "jamo": "ㄱ", "balance_failed": True, "balance_reasons": ["너무 큼", "납작함"]}]
    axes = _axes(balance_result={"components": comps})
    assert axes[AXIS_BALANCE]["score"] == 40
    assert axes[AXIS_BALANCE]["reasons"] == ["중성 'ㅏ' 자리가 벗어남", "종성 'ㄱ' 너무 큼·납작함"]


def test_layout_axis_counts_size_spacing_position():
    axes = _axes(size_reason="너무 작음", spacing_reason="", position_failed=False)
    assert axes[AXIS_LAYOUT]["score"] == 70
    assert axes[AXIS_LAYOUT]["reasons"] == ["크기 너무 작음"]
    axes = _axes(size_reason="", spacing_reason="앞 글자와 너무 좁음", position_failed=True)
    assert axes[AXIS_LAYOUT]["score"] == 40
    assert axes[AXIS_LAYOUT]["reasons"] == ["앞 글자와 너무 좁음", "글자 칸에서 벗어남"]


def test_layout_axis_unmeasured_when_nothing_given():
    """한 글자 연습 — 배치 축 자체가 없다. None이어야지 100이면 안 된다."""
    assert _axes(tilt_result={"checked": 1, "error_count": 0})[AXIS_LAYOUT]["score"] is None


def test_overall_is_mean_of_measured_axes():
    axes = _axes(stroke_order_result={"order_error_count": 0, "stroke_count": 2,
                                      "expected_count": 2, "error_count": 0},
                 tilt_result={"checked": 1, "error_count": 1})
    assert axes[AXIS_ORDER]["score"] == 100 and axes[AXIS_SHAPE]["score"] == 70
    assert overall_from_axes(axes) == 85


def test_axis_label_format():
    assert axis_label(AXIS_SHAPE, ["1획 기울어짐", "모서리 1곳 둥글림"]) == "모양(1획 기울어짐, 모서리 1곳 둥글림)"
```

- [ ] **Step 2: 실패 확인**

Run: `cd 2026-hanium-integration && PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests/test_canvas_axes.py -q`
Expected: `ImportError: cannot import name 'AXIS_BALANCE'`

- [ ] **Step 3: 구현**

`canvas_quality_analyzer.py`의 `DEDUCT_SEVERE_MULTIPLIER` 아래, `ALL_ITEMS` 자리에 추가(기존 `ITEM_*`는 Task 3까지 남겨 둔다):

```python
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


def build_axes(*, stroke_order_result, direction_result, tilt_result, char_rotation_deg,
               corner_result, shape_failed, balance_result, size_reason, spacing_reason,
               position_failed) -> Dict[str, Dict]:
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
            reasons.append(f"획 수 {drawn}개 / 표준 {expected}개")
        n = swaps + reversed_n + (1 if count_off else 0)
    axes[AXIS_ORDER] = {"score": axis_score(n, measured), "reasons": reasons}

    # 모양 — 획 기울기 · 글자 기울기 · 모서리 · 표준과 다른 모양. 하나라도 쟀으면 측정.
    reasons, n, measured = [], 0, False
    if tilt_result and tilt_result.get("checked", 0) > 0:
        measured = True
        k = int(tilt_result.get("error_count") or 0)
        if k:
            reasons.append(f"{k}획 기울어짐")
            n += k
    if char_rotation_deg is not None:
        measured = True
        if abs(char_rotation_deg) > CHAR_ROT_MAX_DEG:
            side = "오른쪽" if char_rotation_deg > 0 else "왼쪽"
            reasons.append(f"글자 전체가 {side}으로 {abs(char_rotation_deg):.0f}도 기울어짐")
            n += 1
    if corner_result and corner_result.get("checked", 0) > 0:
        measured = True
        k = int(corner_result.get("error_count") or 0)
        if k:
            reasons.append(f"모서리 {k}곳 둥글림")
            n += k
    if shape_failed is not None:
        measured = True
        if shape_failed:
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
```

- [ ] **Step 4: 통과 확인**

Run: `PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests/test_canvas_axes.py -q`
Expected: `11 passed`

- [ ] **Step 5: 커밋(사용자 요청 시)**

```bash
git add ai/canvas/canvas_quality_analyzer.py ai/tests/test_canvas_axes.py
git commit -m "feat(ai): 캔버스 채점 축 조립 함수 build_axes 추가"
```

---

### Task 2: 채점 거부를 잉크 기준 두 조건으로 축소 + 낱자 모양 판정 분리

**Files:**
- Modify: `ai/canvas/canvas_quality_analyzer.py` — `assess_character_match`, 상수 구역
- Test: `ai/tests/test_canvas_axes.py`에 추가

**Interfaces:**
- Produces:
  ```python
  INK_MISMATCH_MAX = 0.15          # 종전 INK_RESCUE_MAX. 옛 이름은 지운다
  def assess_character_match(strokes, target_char) -> Dict
      # {"n_strokes", "n_expected", "ink_gap": float|None, "scorable": bool,
      #  "reason": None | "missing" | "too_many_strokes" | "ink_mismatch"}
  def jamo_shape_failed(strokes, target_char) -> Optional[bool]
      # 낱자이고 획 수가 표준과 같을 때만 bool. 그 외 None(미측정).
      # 기준: 짝지은 획의 최대 모양 거리 > SHAPE_FAIL_DIST
  ```
- 없애는 것: `WRONG_CHAR_MEAN_DIST`, `WRONG_CHAR_MAX_DIST`, `UNMATCHED_STROKE_PENALTY`, `assess_character_match`의 `mean_distance`/`max_distance`. `WRONG_CHAR_ROT_DEG`·`WRONG_CHAR_SAMPLES`는 `_shape_distance`·`_resample_path`가 쓰므로 남긴다.

- [ ] **Step 1: 실패하는 테스트 추가**

```python
# ai/tests/test_canvas_axes.py 끝에 추가
from ai.canvas.canvas_quality_analyzer import (
    INK_MISMATCH_MAX, SHAPE_FAIL_DIST, _layout_for_char, assess_character_match, jamo_shape_failed,
)
from ai.canvas.synthetic_stroke_generator import _consonant_paths


def _strokes(paths):
    return [{"stroke_id": f"s{i}", "points": [{"x": x, "y": y, "timestamp": i * 100 + k}
                                              for k, (x, y) in enumerate(p)]}
            for i, p in enumerate(paths)]


def _tmpl(ch):
    return [p for _, ps in _layout_for_char(ch) for p in ps]


def _join(paths):
    out = list(paths[0])
    for p in paths[1:]:
        out += list(p[1:]) if p[0] == out[-1] else list(p)
    return out


def test_refusal_reasons_are_only_three():
    assert assess_character_match([], "각")["reason"] == "missing"
    scribble = [[(0.1 + 0.15 * i, 0.2), (0.2 + 0.15 * i, 0.8)] for i in range(5)]
    assert assess_character_match(_strokes(scribble), "ㅣ")["reason"] == "too_many_strokes"
    line = [[(0.2, 0.5), (0.8, 0.5)]]
    a = assess_character_match(_strokes(line), "ㄱ")
    assert a["reason"] == "ink_mismatch" and a["ink_gap"] > INK_MISMATCH_MAX
    assert "mean_distance" not in a and "max_distance" not in a


def test_merged_and_standard_writing_are_not_refused():
    for ch in ("각", "밤", "시", "ㅏ"):
        assert assess_character_match(_strokes(_tmpl(ch)), ch)["scorable"] is True, ch
    for jamo in ("ㄷ", "ㄹ", "ㅁ"):
        a = assess_character_match(_strokes([_join(_consonant_paths(jamo))]), jamo)
        assert a["scorable"] is True, (jamo, a)


def test_jamo_shape_failed_only_when_counts_match():
    assert jamo_shape_failed(_strokes(_tmpl("ㅁ")), "ㅁ") is False
    assert jamo_shape_failed(_strokes([_join(_tmpl("ㅁ"))]), "ㅁ") is None     # 획 수 다름 → 미측정
    assert jamo_shape_failed(_strokes(_tmpl("각")), "각") is None               # 음절 → 미측정
    squashed = [[(0.2, 0.4), (0.2, 0.6)], [(0.2, 0.4), (0.8, 0.4), (0.8, 0.6)], [(0.2, 0.6), (0.8, 0.6)]]
    assert jamo_shape_failed(_strokes(squashed), "ㅁ") is True                 # 세로로 납작한 ㅁ
    assert SHAPE_FAIL_DIST == 0.15
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests/test_canvas_axes.py -q`
Expected: `ImportError: cannot import name 'INK_MISMATCH_MAX'`

- [ ] **Step 3: 구현**

상수 구역에서 `WRONG_CHAR_MEAN_DIST`·`WRONG_CHAR_MAX_DIST`·`UNMATCHED_STROKE_PENALTY`와 "거부 조건 ①②③" 설명을 지우고, `INK_RESCUE_MAX`를 `INK_MISMATCH_MAX`로 바꾼다(주석도 "거부를 풀어준다"가 아니라 "거부의 유일한 모양 기준"으로). `assess_character_match`를 아래로 교체한다.

```python
def assess_character_match(strokes: List[Dict], target_char: str) -> Dict:
    """**목표 글자를 쓴 게 맞는가** — 채점 거부 판정 (2026-10-08 재설계).

    조건은 세 가지뿐이다(설계 5절):
      ① 획이 하나도 없다(건너뜀)            → missing
      ② 획 수가 표준의 2배를 넘는다(낙서)   → too_many_strokes
      ③ 잉크가 표준 자리에 없다             → ink_mismatch
    종전의 "획 모양 거리"와 "획 수 절반 이하"는 뺐다. 전자는 획을 합쳐 쓴 글씨까지 거부해
    잉크 기준으로 다시 풀어줘야 했고, 후자는 그 자체로 정상 글씨를 거부했다. 잉크 기준은
    획 수와 무관하므로 둘을 한 번에 대신한다.
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
    base = {"n_strokes": len(user_paths), "n_expected": n_expected, "ink_gap": None}

    if not user_paths:
        return {**base, "scorable": False, "reason": "missing"}
    if not template_paths:
        return {**base, "scorable": True, "reason": None}     # 표준을 모르는 글자는 거부하지 않는다
    if len(user_paths) > n_expected * COUNT_MISMATCH_RATIO_THRESHOLD:
        return {**base, "scorable": False, "reason": "too_many_strokes"}
    ink_gap = round(_ink_gap(user_paths, template_paths), 3)
    base["ink_gap"] = ink_gap
    if ink_gap > INK_MISMATCH_MAX:
        return {**base, "scorable": False, "reason": "ink_mismatch"}
    return {**base, "scorable": True, "reason": None}


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
    user = [_resample_path(path) for path in _normalize_uniform(user_paths)]
    worst = max((d for d, _, _ in _pair_strokes_by_shape(user, tmpl)), default=0.0)
    return worst > SHAPE_FAIL_DIST
```

- [ ] **Step 4: 통과 확인**

Run: `PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests/test_canvas_axes.py -q`
Expected: `14 passed`. 이 시점에 `ai/tests/test_canvas_item_scoring.py`는 `WRONG_CHAR_MAX_DIST` import 등으로 깨진다 — Task 3에서 통째로 바꾼다.

- [ ] **Step 5: 커밋(사용자 요청 시)**

```bash
git add ai/canvas/canvas_quality_analyzer.py ai/tests/test_canvas_axes.py
git commit -m "feat(ai): 채점 거부를 잉크 기준 두 조건으로 축소, 낱자 모양 판정 분리"
```

---

### Task 3: `analyze_canvas_writing` 결과를 축 구조로 교체

**Files:**
- Modify: `ai/canvas/canvas_quality_analyzer.py` — `analyze_stroke_order_by_position`(`order_error_count` 추가), `build_component_boxes`, `analyze_canvas_writing` 조립부. 제거: `canvas_item_scores`, `overall_from_failures`, `_failure_ratio`, `_stroke_count_reason`, `size_score_from_fill`, `ITEM_*`, `ALL_ITEMS`, `DEDUCT_*`, `SIZE_REL_ZERO_*`, `SIZE_PENALTY_*`, `SPACING_PENALTY_*`, `SPACING_SCORE_MAX_DEV`, `SIZE_SCORE_MAX_CV`, `ORDER_PENALTY_PER_ERROR`
- Replace: `ai/tests/test_canvas_item_scoring.py` → 축 기준으로 전면 재작성
- `ai/tests/test_jamo_layout_contract.py` — 변경 없음(`stroke_order_result["error_count"]` 유지)

**Interfaces:**
- Produces(글자별 결과 dict): 스펙 7.1 그대로. 새 키 `axes`, 바뀐 `failed_items`(축 라벨), `component_boxes`(문장 = 글자 박스 1개), `overall_score`(축 평균; 문장의 거부 글자는 0), `unscorable_reason` ∈ {None, "missing", "too_many_strokes", "ink_mismatch"}. 제거 `item_scores`.
- `stroke_order_result`에 `order_error_count` 추가(기대 순서와 다른 그린 자리 수, 표준 길이 안에서만). `error_count`는 종전과 같게 유지.
- Consumes: Task 1 `build_axes`·`axis_label`·`overall_from_axes`, Task 2 `assess_character_match`·`jamo_shape_failed`.

- [ ] **Step 1: 테스트 파일 교체**

`ai/tests/test_canvas_item_scoring.py`를 아래 내용으로 **덮어쓴다**. 종전 테스트 중 보존 가치가 있는 회귀(표준 필기 만점, 손떨림, 획 합쳐 쓰기, 모서리, 좌표 공간, 자간 가이드 기준, 납작한 글자)를 축 기준으로 옮겼다.

```python
"""캔버스 채점 — 축 구조 (2026-10-08 재설계).

단계마다 측정되는 축이 다르고(자모음: 획순·모양 / 한 글자: +짜임새 / 문장: +배치),
축 점수는 100/70/40, 글자 점수는 측정된 축 평균이다. 설계: docs/superpowers/specs/2026-10-08-*.
"""
import math
import random

from ai.canvas.canvas_quality_analyzer import (
    AXIS_BALANCE, AXIS_LAYOUT, AXIS_ORDER, AXIS_SHAPE, ALL_AXES,
    _layout_for_char, analyze_canvas_writing,
)
from ai.canvas.synthetic_stroke_generator import _consonant_paths, _syllable_layout

GUIDE = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
_PRACTICE_SENTENCES = ("시원한 선풍기", "천 리 길도 한 걸음부터 시작된다는 마음으로")
_PRACTICE_SYLLABLES = sorted(set("각간달밤상" + "".join("".join(s.split()) for s in _PRACTICE_SENTENCES)))


def _paths(char_parts):
    return [(jamo, path) for jamo, paths in char_parts for path in paths]


def _template(target):
    return _paths(_layout_for_char(target))


def _dense(paths, per=8):
    out = []
    for jamo, path in paths:
        pts = []
        for a, b in zip(path, path[1:]):
            for k in range(per):
                u = k / per
                pts.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
        pts.append(path[-1])
        out.append((jamo, pts))
    return out


def _strokes(paths):
    return [{"stroke_id": f"s{i}", "points": [{"x": x, "y": y, "timestamp": i * 100 + k}
                                              for k, (x, y) in enumerate(path)]}
            for i, (_, path) in enumerate(paths)]


def _group(strokes, cid="c0"):
    xs = [p["x"] for s in strokes for p in s["points"]]
    ys = [p["y"] for s in strokes for p in s["points"]]
    return [{"char_id": cid, "strokes": strokes,
             "bounding_box": {"x": min(xs), "y": min(ys),
                              "width": max(xs) - min(xs), "height": max(ys) - min(ys)}}]


def _score(paths, target, guide=GUIDE):
    return analyze_canvas_writing(_group(_strokes(paths)), target, guide_box=guide)[0]


def _scores(r):
    return {k: v["score"] for k, v in r["axes"].items()}


def _scale_about_center(path, factor):
    cx = sum(x for x, _ in path) / len(path)
    cy = sum(y for _, y in path) / len(path)
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in path]


def _rotate(paths, deg):
    pts = [pt for _, path in paths for pt in path]
    cx = (min(x for x, _ in pts) + max(x for x, _ in pts)) / 2.0
    cy = (min(y for _, y in pts) + max(y for _, y in pts)) / 2.0
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(j, [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca)
                 for x, y in p]) for j, p in paths]


def _shake(paths, seed, amount=0.01):
    rng = random.Random(seed)
    return [(j, [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount))
                 for x, y in p]) for j, p in paths]


def _join(paths):
    out = list(paths[0])
    for p in paths[1:]:
        out += list(p[1:]) if p[0] == out[-1] else list(p)
    return out


def _round_corners(path, r):
    if len(path) < 3 or r <= 0:
        return path
    out = [path[0]]
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        t = min(r, 0.49)
        pa = (b[0] + (a[0] - b[0]) * t, b[1] + (a[1] - b[1]) * t)
        pc = (b[0] + (c[0] - b[0]) * t, b[1] + (c[1] - b[1]) * t)
        out.append(pa)
        for u in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875):
            out.append(((1 - u) ** 2 * pa[0] + 2 * (1 - u) * u * b[0] + u * u * pc[0],
                        (1 - u) ** 2 * pa[1] + 2 * (1 - u) * u * b[1] + u * u * pc[1]))
        out.append(pc)
    out.append(path[-1])
    return out


def _sentence(text, cell=100.0, shifts=None, scales=None, drop=()):
    """글자 칸(cell×cell)에 표준 자형을 놓은 문장 → (char_groups, char_positions). drop의 글자는 빈 칸."""
    groups, positions = [], []
    for i, ch in enumerate(text):
        positions.append({"char": ch, "index": i, "x": i * cell, "y": 0.0, "width": cell, "height": cell})
        if i in drop:
            groups.append({"char_id": f"char_{i}", "strokes": [],
                           "bounding_box": {"x": i * cell, "y": 0.0, "width": cell, "height": cell}})
            continue
        dx = (shifts or {}).get(i, 0.0)
        k = (scales or {}).get(i, 1.0)
        paths = [(j, [((0.5 + (x - 0.5) * k) * cell + i * cell + dx, (0.5 + (y - 0.5) * k) * cell)
                      for x, y in p]) for j, p in _dense(_template(ch))]
        strokes = _strokes(paths)
        for s in strokes:
            s["stroke_id"] = f"c{i}_{s['stroke_id']}"
        groups.append(_group(strokes, f"char_{i}")[0])
    return groups, positions


# ── 단계별로 측정되는 축 ────────────────────────────────────────────────────

def test_jamo_measures_order_and_shape_only():
    r = _score(_dense(_template("ㄱ")), "ㄱ")
    s = _scores(r)
    assert set(r["axes"]) == set(ALL_AXES)
    assert s[AXIS_ORDER] == 100 and s[AXIS_SHAPE] == 100
    assert s[AXIS_BALANCE] is None and s[AXIS_LAYOUT] is None
    assert r["overall_score"] == 100 and r["component_boxes"] is None


def test_syllable_adds_balance_but_not_layout():
    s = _scores(_score(_dense(_template("각")), "각"))
    assert s[AXIS_ORDER] == 100 and s[AXIS_SHAPE] == 100 and s[AXIS_BALANCE] == 100
    assert s[AXIS_LAYOUT] is None                      # 한 글자에는 배치 축이 없다 (guide_box 있어도)


def test_sentence_adds_layout():
    groups, positions = _sentence("각간달")
    for r in analyze_canvas_writing(groups, "각간달", char_positions=positions):
        assert _scores(r)[AXIS_LAYOUT] == 100, (r["char_id"], r["axes"][AXIS_LAYOUT])
        assert r["overall_score"] == 100


def test_item_scores_key_is_gone():
    assert "item_scores" not in _score(_dense(_template("각")), "각")


# ── 표준대로 쓰면 만점, 사유 없음 ─────────────────────────────────────────────

def test_template_exact_practice_characters_score_full_marks():
    for ch in _PRACTICE_SYLLABLES + list("ㄱㄴㄷㄹㅁㅏㅑㅓㅕㅗ느그드르스뜨"):
        r = _score(_dense(_template(ch)), ch)
        assert r["scorable"], (ch, r["unscorable_reason"])
        assert r["failed_items"] == [], (ch, r["failed_items"])
        assert r["overall_score"] == 100, ch


def test_line_vowel_syllables_survive_hand_tremor():
    for ch in "시기이으리미그느":
        for seed in range(10):
            r = _score(_shake(_dense(_template(ch)), seed), ch)
            assert r["axes"][AXIS_BALANCE]["reasons"] == [], (ch, seed, r["failed_items"])


# ── 축 점수 100/70/40 ─────────────────────────────────────────────────────

def test_one_swap_costs_partial_on_order_axis_only():
    paths = _template("각")
    paths[0], paths[1] = paths[1], paths[0]
    r = _score(paths, "각")
    s = _scores(r)
    assert s[AXIS_ORDER] == 70 and r["axes"][AXIS_ORDER]["reasons"] == ["1획 순서 틀림"]
    assert s[AXIS_SHAPE] == 100 and s[AXIS_BALANCE] == 100
    assert r["overall_score"] == 90
    assert r["failed_items"] == [f"{AXIS_ORDER}(1획 순서 틀림)"]


def test_reversed_stroke_hits_order_axis_only():
    paths = _template("각")
    jamo, path = paths[0]
    paths[0] = (jamo, list(reversed(path)))
    r = _score(paths, "각")
    assert r["axes"][AXIS_ORDER]["reasons"] == ["1획 반대로 그음"]
    assert _scores(r)[AXIS_SHAPE] == 100 and _scores(r)[AXIS_BALANCE] == 100


def test_two_bad_components_make_balance_severe():
    factors = [2.0, 1.0, 1.0, 0.5]
    paths = [(j, _scale_about_center(p, f)) for (j, p), f in zip(_template("각"), factors)]
    r = _score(paths, "각")
    assert _scores(r)[AXIS_BALANCE] == 40
    assert len(r["axes"][AXIS_BALANCE]["reasons"]) == 2
    assert _scores(r)[AXIS_ORDER] == 100


def test_merged_consonant_is_order_axis_only():
    for jamo in ("ㄷ", "ㄹ", "ㅁ"):
        r = _score(_dense([(jamo, _join(_consonant_paths(jamo)))]), jamo)
        assert r["scorable"] is True, jamo
        assert _scores(r)[AXIS_ORDER] == 70, (jamo, r["axes"][AXIS_ORDER])
        assert r["axes"][AXIS_ORDER]["reasons"] == [f"획 수 1개 / 표준 {len(_consonant_paths(jamo))}개"]
        assert r["axes"][AXIS_SHAPE]["reasons"] == [], (jamo, r["axes"][AXIS_SHAPE])


def test_merging_the_last_strokes_still_counts():
    layout = _syllable_layout("ㅂ", "ㅏ", "ㅁ")
    paths = []
    for i, (jamo, ps) in enumerate(layout):
        if i == len(layout) - 1:
            ps = [ps[0], ps[1] + ps[2][::-1][1:]]
        paths += [(jamo, p) for p in ps]
    r = _score(_dense(paths), "밤")
    assert r["axes"][AXIS_ORDER]["reasons"] == ["획 수 8개 / 표준 9개"]
    boxes = {b["role"]: b for b in r["component_boxes"]}
    assert boxes["종성"]["ok"] is False and boxes["초성"]["ok"] and boxes["중성"]["ok"]


# ── 모양 축 ───────────────────────────────────────────────────────────────

def test_rotated_jamo_is_caught_on_shape_axis():
    for jamo in ("ㄱ", "ㄴ", "ㅁ"):
        r = _score(_dense(_rotate(_template(jamo), 25)), jamo)
        assert _scores(r)[AXIS_SHAPE] < 100, (jamo, r["axes"][AXIS_SHAPE])
        assert any("기울어짐" in x for x in r["axes"][AXIS_SHAPE]["reasons"]), jamo


def test_right_angled_giyeok_is_not_called_rotated():
    r = _score(_dense([("ㄱ", [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8)])]), "ㄱ")
    assert r["axes"][AXIS_SHAPE]["reasons"] == [], r["axes"][AXIS_SHAPE]


def test_tilted_straight_stroke_is_caught_in_a_narrow_character():
    paths = _dense(_template("리"))
    jamo, stroke = paths[-1]
    x0, y0 = stroke[0]
    lean = math.tan(math.radians(25))
    paths[-1] = (jamo, [(x0 + (y - y0) * lean, y) for _, y in stroke])
    r = _score(paths, "리")
    assert any("기울어짐" in x for x in r["axes"][AXIS_SHAPE]["reasons"]), r["axes"][AXIS_SHAPE]


def test_rounded_corners_are_caught_and_angular_pass():
    parts = _dense([(j, _round_corners(p, 0.35)) for j, p in _template("달")])
    r = _score(parts, "달")
    assert any("모서리" in x for x in r["axes"][AXIS_SHAPE]["reasons"]), r["axes"][AXIS_SHAPE]
    assert r["axes"][AXIS_ORDER]["reasons"] == []
    for ch in ("달", "문", "느"):
        assert _score(_dense(_template(ch)), ch)["axes"][AXIS_SHAPE]["reasons"] == [], ch


def test_reversed_stroke_is_not_also_called_rounded():
    paths = _dense(_template("ㄹ"))
    jamo, stroke = paths[0]
    paths[0] = (jamo, stroke[::-1])
    r = _score(paths, "ㄹ")
    assert r["axes"][AXIS_ORDER]["reasons"] == ["1획 반대로 그음"]
    assert r["axes"][AXIS_SHAPE]["reasons"] == []


def test_squashed_jamo_fails_shape():
    squashed = [("ㅁ", [(0.2, 0.4), (0.2, 0.6)]), ("ㅁ", [(0.2, 0.4), (0.8, 0.4), (0.8, 0.6)]),
                ("ㅁ", [(0.2, 0.6), (0.8, 0.6)])]
    r = _score(_dense(squashed), "ㅁ")
    assert "표준 모양과 많이 다름" in r["axes"][AXIS_SHAPE]["reasons"], r["axes"][AXIS_SHAPE]


def test_shape_axis_is_measured_for_curvy_jamo_and_syllables():
    """ㅅ·ㅇ 낱자도 '표준과 다른 모양' 판정이 있어 측정된다. 음절 '소'는 곧은 획이 있어 측정된다."""
    assert _scores(_score(_dense(_template("ㅅ")), "ㅅ"))[AXIS_SHAPE] == 100
    assert _scores(_score(_dense(_template("소")), "소"))[AXIS_SHAPE] == 100


# ── 채점 거부 ───────────────────────────────────────────────────────────────

def test_refused_jamo_has_no_score():
    r = _score([("?", [(0.2, 0.5), (0.8, 0.5)])], "ㄱ")
    assert r["scorable"] is False and r["unscorable_reason"] == "ink_mismatch"
    assert r["overall_score"] is None
    assert all(a["score"] is None for a in r["axes"].values())
    assert r["failed_items"] == ["다시 써 주세요(목표 글자와 다름)"]
    assert "unscorable" in r["correction_flags"] and "unscorable:ink_mismatch" in r["correction_flags"]


def test_refused_character_in_a_sentence_scores_zero_and_others_continue():
    groups, positions = _sentence("각간달")
    groups[1]["strokes"] = _strokes([("?", [(110.0, 50.0), (190.0, 50.0)])])
    results = analyze_canvas_writing(groups, "각간달", char_positions=positions)
    assert results[1]["scorable"] is False
    assert results[1]["overall_score"] == 0
    box = results[1]["component_boxes"][0]
    assert box["role"] == "글자" and box["jamo"] == "간" and box["ok"] is False
    assert box["failed_items"] == ["다시 써 주세요(목표 글자와 다름)"]
    assert results[0]["overall_score"] == 100 and results[2]["overall_score"] == 100


def test_skipped_cell_in_a_sentence_is_missing_and_zero():
    groups, positions = _sentence("각간달", drop=(1,))
    r = analyze_canvas_writing(groups, "각간달", char_positions=positions)[1]
    assert r["unscorable_reason"] == "missing" and r["overall_score"] == 0
    assert r["failed_items"] == ["다시 써 주세요(쓰지 않음)"]


def test_all_characters_refused_sentence_is_zero_not_none():
    groups, positions = _sentence("각간", drop=(0, 1))
    results = analyze_canvas_writing(groups, "각간", char_positions=positions)
    assert [r["overall_score"] for r in results] == [0, 0]


# ── 문장: 글자 박스와 배치 축 ───────────────────────────────────────────────

def test_sentence_boxes_are_one_per_character():
    groups, positions = _sentence("각간달", shifts={2: -40.0})
    results = analyze_canvas_writing(groups, "각간달", char_positions=positions)
    for r, ch in zip(results, "각간달"):
        assert len(r["component_boxes"]) == 1
        box = r["component_boxes"][0]
        assert box["role"] == "글자" and box["jamo"] == ch
        assert box["failed_items"] == r["failed_items"]
    assert results[2]["component_boxes"][0]["ok"] is False
    assert f"{AXIS_LAYOUT}(앞 글자와 너무 좁음)" in results[2]["failed_items"]


def test_spacing_against_the_guide_catches_gaps():
    groups, positions = _sentence("각간달", shifts={0: -45.0, 1: 45.0})
    r = analyze_canvas_writing(groups, "각간달", char_positions=positions)[1]
    assert "앞 글자와 너무 넓음" in r["axes"][AXIS_LAYOUT]["reasons"]


def test_positions_are_ignored_when_their_count_does_not_match():
    groups, positions = _sentence("각간달")
    for r in analyze_canvas_writing(groups, "각간달", char_positions=positions[:2]):
        assert r["position_result"] is None
        assert "글자 칸에서 벗어남" not in r["axes"][AXIS_LAYOUT]["reasons"]


def test_flat_syllable_is_not_called_small_but_a_small_one_is():
    groups, positions = _sentence("한으로")
    r = analyze_canvas_writing(groups, "한으로", char_positions=positions)[1]
    assert "크기 너무 작음" not in r["axes"][AXIS_LAYOUT]["reasons"]
    groups, positions = _sentence("한각로", scales={1: 0.45})
    r = analyze_canvas_writing(groups, "한각로", char_positions=positions)[1]
    assert "크기 너무 작음" in r["axes"][AXIS_LAYOUT]["reasons"]
    assert r["component_boxes"][0]["ok"] is False


def test_non_hangul_target_in_a_sentence_measures_layout_only():
    groups, positions = _sentence("각간달")
    results = analyze_canvas_writing(groups, "각A달", char_positions=positions)
    s = _scores(results[1])
    assert s[AXIS_ORDER] is None and s[AXIS_SHAPE] is None and s[AXIS_BALANCE] is None
    assert s[AXIS_LAYOUT] == 100
    assert results[1]["overall_score"] == 100


# ── 성분 박스(한 글자) 사유는 축 라벨 ────────────────────────────────────────

def test_component_box_reasons_use_axis_names():
    paths = _template("각")
    jamo, path = paths[3]
    paths[3] = (jamo, _scale_about_center(path, 2.0))
    r = _score(paths, "각")
    boxes = {b["role"]: b for b in r["component_boxes"]}
    assert boxes["종성"]["ok"] is False
    assert boxes["종성"]["failed_items"] == [f"{AXIS_BALANCE}(너무 큼)"]
    assert boxes["초성"]["ok"] and boxes["중성"]["ok"]
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests/test_canvas_item_scoring.py -q 2>&1 | tail -3`
Expected: 대부분 FAIL(`KeyError: 'axes'`) 또는 ERROR.

- [ ] **Step 3: `analyze_stroke_order_by_position`에 `order_error_count` 추가**

`missing = max(0, len(canonical) - len(strokes))` 줄 앞에 넣고, `error_count` 계산은 그대로 둔다:

```python
    # 축 채점용: 기대 순서와 다른 **그린 자리** 수(표준 길이 안에서만 — 여분 획은 획 수로 센다).
    order_error_count = sum(1 for i, m in enumerate(matched_indices)
                            if i < len(best_seq) and m != best_seq[i])
```
반환 dict에 `"order_error_count": order_error_count` 추가.

- [ ] **Step 4: `build_component_boxes`를 축 라벨로**

시그니처는 유지하되 사유를 축으로 묶는다. 루프 본문의 `reasons` 조립을 아래로 교체:

```python
    for comp in balance_result["components"]:
        b = comp["block"]
        order_reasons: List[str] = []
        if b in count_per_block:
            drawn, expected = count_per_block[b]
            order_reasons.append(f"획 수 {drawn}개 / 표준 {expected}개")
        elif order_per_block.get(b):
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
        layout_reasons: List[str] = []
        if size_failed:
            layout_reasons.append("크기(글자 전체)")
        if position_failed:
            layout_reasons.append("위치(글자 전체)")
        reasons = [axis_label(axis, rs) for axis, rs in (
            (AXIS_ORDER, order_reasons), (AXIS_SHAPE, shape_reasons),
            (AXIS_BALANCE, balance_reasons), (AXIS_LAYOUT, layout_reasons)) if rs]
        boxes.append({"block": b, "jamo": comp["jamo"], "role": comp["role"], "box": comp["box"],
                      "ok": not reasons, "failed_items": reasons})
```

- [ ] **Step 5: `analyze_canvas_writing` 조립부 교체**

거부 분기(`if assessment and not assessment["scorable"]:`)를 아래로 바꾼다:

```python
        if assessment and not assessment["scorable"]:
            reason = assessment["reason"]
            detail = {"too_many_strokes": "획이 너무 많음", "missing": "쓰지 않음"}.get(reason, "목표 글자와 다름")
            label = f"다시 써 주세요({detail})"
            correction_flags += ["unscorable", f"unscorable:{reason}"]
            if assessment.get("ink_gap") is not None:
                correction_flags.append(f"ink_gap:{assessment['ink_gap']}")
            results.append({
                "char_id": group["char_id"],
                "stroke_order_result": None, "direction_result": None, "tilt_result": None,
                "corner_result": None, "balance_result": None, "char_rotation_deg": None,
                # 문장은 어느 글자가 문제인지 보여야 하므로 글자 박스를 친다. 낱자·한 글자는 문구로 충분.
                "component_boxes": ([{"block": 0, "jamo": target_char, "role": "글자",
                                      "box": {"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["height"]},
                                      "ok": False, "failed_items": [label]}] if multi_char else None),
                "spacing_deviation": None, "size_deviation": None, "size_fill_ratio": None,
                "position_result": None,
                "axes": {axis: {"score": None, "reasons": []} for axis in ALL_AXES},
                "speed_profile": {"mean_speed_px_per_ms": _stroke_speed_stats(group["strokes"])["mean_speed_px_per_ms"]},
                # 문장에서는 그 글자만 0점(설계 5절). 낱자·한 글자는 세션 채점 불가(None).
                "overall_score": 0 if multi_char else None,
                "scorable": False, "unscorable_reason": reason,
                "failed_items": [label],
                "correction_flags": correction_flags,
                "character_match": assessment,
                "corrections": [label],
            })
            continue
```

크기·자간 블록은 측정값 계산은 그대로 두되 플래그 대신 **사유 문자열**을 만든다(`None`=미측정, `""`=통과):

```python
        size_fill_ratio = None
        size_reason: Optional[str] = None
        if multi_char and guide_area and target_char:
            ref_fill = template_ink_fill(target_char)
            if ref_fill:
                actual_fill = (bb["width"] * bb["height"]) / guide_area
                size_fill_ratio = round(actual_fill / ref_fill, 3)
                size_reason = ("너무 작음" if size_fill_ratio < SIZE_REL_MIN_OK
                               else "너무 큼" if size_fill_ratio > SIZE_REL_MAX_OK else "")
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

        spacing_reason: Optional[str] = None
        spacing_deviation_px = None
        if i > 0:
            ...(기존 too_narrow / too_wide 계산 그대로)...
            spacing_reason = ("앞 글자와 너무 좁음" if too_narrow
                              else "앞 글자와 너무 넓음" if too_wide else "")
            if too_narrow:
                correction_flags.append("spacing_too_narrow")
            elif too_wide:
                correction_flags.append("spacing_too_wide")
```

위치 블록: `position_failed`를 `Optional[bool]`로 — 측정했을 때만 bool, 아니면 None.

```python
        position_score = None
        position_failed: Optional[bool] = None
        if multi_char and positions:
            position_score, off = _position_check(bb, positions[i])
            if position_score is not None:
                position_failed = off
                if off:
                    correction_flags.append("position_off")
```

항목 점수·실패 목록 블록(`item = canvas_item_scores(...)`부터 `failed_items = [...]`까지)을 통째로 아래로 교체:

```python
        shape_failed = jamo_shape_failed(group["strokes"], target_char) if target_char else None
        if shape_failed:
            correction_flags.append("shape_off")

        axes = build_axes(
            stroke_order_result=stroke_order_result, direction_result=direction_result,
            tilt_result=tilt_result, char_rotation_deg=char_rotation_deg,
            corner_result=corner_result, shape_failed=shape_failed,
            balance_result=balance_result, size_reason=size_reason,
            spacing_reason=spacing_reason, position_failed=position_failed)
        overall_score = overall_from_axes(axes)
        failed_items = [axis_label(axis, a["reasons"]) for axis, a in axes.items() if a["reasons"]]

        # 박스: 자모음 없음 / 한 글자 성분 박스 / 문장 글자 박스(설계 6절).
        if multi_char:
            component_boxes = [{"block": 0, "jamo": target_char or "", "role": "글자",
                                "box": {"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["height"]},
                                "ok": not failed_items, "failed_items": failed_items}]
        elif target_char:
            component_boxes = build_component_boxes(
                group["strokes"], bb, target_char, stroke_order_result, direction_result,
                tilt_result, balance_result, corner_result=corner_result,
                size_failed=size_failed, position_failed=bool(position_failed))
        else:
            component_boxes = None
```

결과 dict에서 `"item_scores": item` → `"axes": axes`. 기존 `char_rotation_failed`와 `correction_flags.append("char_rotation_error")`는 유지(플래그는 기록용). 모듈 상단 docstring의 "다섯 항목" 설명을 축 설명으로 바꾼다. 제거 대상(`canvas_item_scores`, `overall_from_failures`, `_failure_ratio`, `_stroke_count_reason`, `size_score_from_fill`, `ITEM_*`, `ALL_ITEMS`, `DEDUCT_*`, 점수 계수 상수들)은 `grep`으로 참조가 없어진 것을 확인하고 지운다.

- [ ] **Step 6: 통과 확인 — 캔버스 테스트 전부**

Run: `PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests -q`
Expected: 전부 PASS. `test_jamo_layout_contract.py`의 `stroke_order_result["error_count"]`는 그대로 동작한다.

- [ ] **Step 7: 전수 점검**

11,172자 전체를 표준대로 써서 걸리는 글자가 0인지 확인한다(2026-09-30에 쓴 스크립트 `sweep.py`와 같은 방식 — `scorable`이 False이거나 `failed_items`가 비어 있지 않으면 출력).
Expected: `걸린 글자 0`.

- [ ] **Step 8: 커밋(사용자 요청 시)**

```bash
git add ai/canvas/canvas_quality_analyzer.py ai/tests/test_canvas_item_scoring.py ai/tests/test_canvas_axes.py
git commit -m "feat(ai): 캔버스 채점 결과를 네 축 구조로 교체"
```

---

### Task 4: 백엔드 스키마·DB 컬럼·저장

**Files:**
- Modify: `backend/app/schemas/canvas.py` — `CanvasCharAnalysis`
- Modify: `backend/app/models/correction.py` — `item_scores` 컬럼
- Create: `backend/alembic/versions/a1f3c5e7b9d2_canvas_axis_scores.py`
- Modify: `backend/app/api/v1/routes/handwriting.py` — 저장부
- Modify: `backend/app/services/ai_adapters.py` — `canvas_item_scores`·`CHAR_ROT_MAX_DEG` export 제거, docstring
- Modify: `backend/app/core/config.py:32` — 주석의 `canvas_item_scores()` → `build_axes()`

**Interfaces:**
- Produces: `CanvasCharAnalysis.axes: dict` (`{축: {"score": int|None, "reasons": [str]}}`), `CanvasAnalysisResult.item_scores: JSON` (`{축: int|None}`).
- Consumes: Task 3의 글자별 결과 dict.

- [ ] **Step 1: 스키마**

`CanvasCharAnalysis`에서 `item_scores: dict = {}` 줄을 아래로 교체하고, docstring의 "연습 종류마다 … 항목" 세 줄을 "자모음: 획순·모양 / 한 글자: +짜임새 / 문장: +배치"로 고친다. `unscorable_reason` 주석을 `missing | too_many_strokes | ink_mismatch`로.

```python
    # 채점 축 — {"획순": {"score": 100|70|40|None, "reasons": [...]}, "모양": ..., "짜임새": ..., "배치": ...}
    # 단계마다 측정되는 축이 다르다(자모음: 획순·모양 / 한 글자: +짜임새 / 문장: +배치).
    # None은 미측정이다 — 0이나 100으로 채우지 말 것.
    axes: dict = {}
```

- [ ] **Step 2: 모델과 마이그레이션**

`correction.py`의 `overall_score` 줄 아래에:

```python
    # 축 점수 {"획순": 100, "모양": 70, "짜임새": None, "배치": None} (2026-10-08 재설계).
    # 대시보드가 중간 결과로 다시 계산하지 않고 이 값을 그대로 집계한다 — 모서리처럼
    # 저장 안 되는 중간 결과가 있어 복원이 안 되기 때문이다. 이전 행은 NULL이라 축 집계에서 빠진다.
    item_scores = Column(JSON, nullable=True)
```

`backend/alembic/versions/a1f3c5e7b9d2_canvas_axis_scores.py`:

```python
"""캔버스 축 점수 저장

2026-10-08 채점 축 재설계. 글자마다 축 점수 {"획순","모양","짜임새","배치"}를 저장한다.
대시보드가 저장된 중간 결과로 점수를 다시 계산하던 코드를 없애기 위한 컬럼이다.

Revision ID: a1f3c5e7b9d2
Revises: d3a8f1c62e07
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "a1f3c5e7b9d2"
down_revision = "d3a8f1c62e07"
branch_labels = None
depends_on = None

_TABLE = "canvas_analysis_results"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("item_scores", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "item_scores")
```

Run: `cd backend && C:\ai_venv\Scripts\python.exe -m alembic upgrade head && C:\ai_venv\Scripts\python.exe -m alembic current`
Expected: `a1f3c5e7b9d2 (head)`

- [ ] **Step 3: 저장**

`handwriting.py`의 `CanvasAnalysisResult(...)`에 `overall_score=item["overall_score"],` 다음 줄로:

```python
            item_scores={axis: a["score"] for axis, a in (item.get("axes") or {}).items()},
```

- [ ] **Step 4: 어댑터 정리**

`ai_adapters.py`에서 `canvas_item_scores`와 `CHAR_ROT_MAX_DEG` import·docstring 항목을 지운다(Task 5·6에서 쓰는 곳이 사라진다). `config.py:32`의 주석을 고친다.

- [ ] **Step 5: import 확인**

Run: `cd backend && PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -c "import app.schemas.canvas, app.models.correction, app.services.ai_adapters; print('ok')"`
Expected: `ok`

- [ ] **Step 6: 커밋(사용자 요청 시)**

```bash
git add backend/app/schemas/canvas.py backend/app/models/correction.py backend/alembic/versions/a1f3c5e7b9d2_canvas_axis_scores.py backend/app/api/v1/routes/handwriting.py backend/app/services/ai_adapters.py backend/app/core/config.py
git commit -m "feat(backend): 캔버스 축 점수 응답·저장(item_scores 컬럼)"
```

---

### Task 5: 피드백 생성 — 문구 조립 제거, 사유 전달

**Files:**
- Modify: `backend/app/services/feedback_generator.py` (전면 축소)
- Create: `backend/tests/__init__.py`(빈 파일), `backend/tests/test_feedback_generator.py`

**Interfaces:**
- Produces: `generate_canvas_feedback(analysis_results) -> {"feedback_items": [{"target_id", "feedback_message", "severity"}], "overall_score": int|None, "achievement_message": str}`
  - `feedback_message` = 그 글자 `failed_items`를 `", "`로 이은 문자열(빈 문자열 가능).
  - `severity` = 점수 80↑ good / 50↑ warning / 그 외 error. 점수 None인 글자(낱자·한 글자 거부)는 error.
  - 세션 점수 = `overall_score`가 None이 아닌 글자 평균(반올림). 전부 None이면 None.
  - `achievement_message` = None이면 "목표 글자와 달라 채점하지 않았어요. 다시 써 볼까요?"; 아니면 점수 구간 문구 + 거부 글자가 있으면 " 다시 써야 할 글자가 N자 있어요."
- Consumes: Task 3 결과 dict의 `overall_score`, `failed_items`, `scorable`.

- [ ] **Step 1: 실패하는 테스트**

```python
# backend/tests/test_feedback_generator.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.feedback_generator import generate_canvas_feedback  # noqa: E402


def _char(cid, score, failed=(), scorable=True):
    return {"char_id": cid, "overall_score": score, "failed_items": list(failed), "scorable": scorable}


def test_messages_are_the_failed_items_joined():
    fb = generate_canvas_feedback([
        _char("char_0", 85, ["모양(1획 기울어짐)", "획순(1획 반대로 그음)"]),
        _char("char_1", 100),
    ])
    assert fb["feedback_items"][0]["feedback_message"] == "모양(1획 기울어짐), 획순(1획 반대로 그음)"
    assert fb["feedback_items"][0]["severity"] == "good"
    assert fb["feedback_items"][1]["feedback_message"] == ""
    assert fb["feedback_items"][1]["severity"] == "good"
    assert fb["overall_score"] == 92


def test_refused_character_in_sentence_is_zero_and_counted():
    fb = generate_canvas_feedback([
        _char("char_0", 100),
        _char("char_1", 0, ["다시 써 주세요(목표 글자와 다름)"], scorable=False),
        _char("char_2", 70, ["짜임새(종성 'ㄹ' 너무 큼)"]),
    ])
    assert fb["overall_score"] == 57
    assert fb["feedback_items"][1]["severity"] == "error"
    assert fb["achievement_message"].endswith("다시 써야 할 글자가 1자 있어요.")


def test_refused_single_character_has_no_score():
    fb = generate_canvas_feedback([_char("char_0", None, ["다시 써 주세요(목표 글자와 다름)"], scorable=False)])
    assert fb["overall_score"] is None
    assert fb["achievement_message"] == "목표 글자와 달라 채점하지 않았어요. 다시 써 볼까요?"
    assert fb["feedback_items"][0]["severity"] == "error"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest tests/test_feedback_generator.py -q`
Expected: FAIL(`feedback_message`가 "획순이 정확합니다…" 형태).

- [ ] **Step 3: 구현** — 파일 전체를 아래로 교체

```python
"""SFR-007 캔버스 피드백 — AI가 만든 축별 사유를 그대로 전달한다 (2026-10-08 재설계).

종전에는 여기서 항목마다 문장을 조립했다("획순이 정확합니다", "자간이 12.3px 좁습니다"…).
문구가 AI 사유·백엔드 문장·앱 라벨 세 곳에서 따로 만들어져 서로 어긋났다. 이제 문구는
AI의 failed_items 하나뿐이고, 백엔드는 점수 구간 문구만 붙인다.
"""
from typing import Any, Dict, List, Optional


def _severity_from_score(score: Optional[int]) -> str:
    """점수 → 등급. 점수가 없는 글자(채점 거부)는 error."""
    if score is None or score < 50:
        return "error"
    return "good" if score >= 80 else "warning"


def _achievement_message(overall_score: int) -> str:
    """REQ-007 종합 점수에 따른 성취 메시지. SFR-005C Side Effects: 90점 이상 시 성취 이벤트"""
    if overall_score >= 90:
        return "훌륭해요! 표준 글씨체에 매우 가깝습니다. 🎉"
    elif overall_score >= 70:
        return "좋아요! 조금만 더 연습하면 완벽해질 거예요."
    elif overall_score >= 50:
        return "괜찮아요. 몇 가지 교정이 필요합니다."
    else:
        return "교정이 많이 필요합니다. 천천히 다시 연습해볼까요?"


def generate_canvas_feedback(analysis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """글자별 채점 결과 → 피드백 응답.

    - 글자 문구 = 그 글자의 failed_items를 이은 것(비어 있으면 통과).
    - 세션 점수 = 점수가 있는 글자의 평균. 문장의 거부 글자는 AI가 0점으로 넣어 두므로
      평균을 끌어내린다(설계 5절). 낱자·한 글자의 거부는 점수가 None이라 세션도 None.
    """
    feedback_items = [{
        "target_id": r["char_id"],
        "feedback_message": ", ".join(r.get("failed_items") or []),
        "severity": _severity_from_score(r.get("overall_score")),
    } for r in analysis_results]

    scored = [r["overall_score"] for r in analysis_results if r.get("overall_score") is not None]
    overall_score = round(sum(scored) / len(scored)) if scored else None
    refused = sum(1 for r in analysis_results if not r.get("scorable", True))

    if overall_score is None:
        message = "목표 글자와 달라 채점하지 않았어요. 다시 써 볼까요?"
    else:
        message = _achievement_message(overall_score)
        if refused:
            message += f" 다시 써야 할 글자가 {refused}자 있어요."
    return {"feedback_items": feedback_items, "overall_score": overall_score,
            "achievement_message": message}
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest tests/test_feedback_generator.py -q`
Expected: `3 passed`

- [ ] **Step 5: 커밋(사용자 요청 시)**

```bash
git add backend/app/services/feedback_generator.py backend/tests/__init__.py backend/tests/test_feedback_generator.py
git commit -m "feat(backend): 피드백 문구를 AI 축 사유 그대로 전달"
```

---

### Task 6: 대시보드 — 저장된 축 점수로 집계

**Files:**
- Modify: `backend/app/services/dashboard_service.py`
- Test: `backend/tests/test_dashboard_canvas_sessions.py` (새 파일)

**Interfaces:**
- Produces: `summarize_canvas_sessions(rows_by_session: dict[str, list]) -> list[dict]` — `[{"overall": float, "date": date, "items": {축: float}}]`. `get_dashboard_data`의 캔버스 루프가 이 함수를 쓴다.
- 제거: `_canvas_item_scores`, `_is_unscorable`, `canvas_item_scores` import.
- Consumes: `CanvasAnalysisResult.overall_score`, `.item_scores`, `.created_at`.

- [ ] **Step 1: 실패하는 테스트**

```python
# backend/tests/test_dashboard_canvas_sessions.py
import os
import sys
import types
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.dashboard_service import summarize_canvas_sessions  # noqa: E402


def _row(score, items=None, flags=None):
    return types.SimpleNamespace(overall_score=score, item_scores=items, correction_flags=flags or [],
                                 created_at=datetime(2026, 10, 8, 12, 0))


def test_session_overall_is_mean_including_zero_for_refused_characters():
    out = summarize_canvas_sessions({"s1": [
        _row(100, {"획순": 100, "모양": 100}),
        _row(0, None, ["unscorable"]),
        _row(70, {"획순": 70, "모양": 100}),
    ]})
    assert len(out) == 1
    assert round(out[0]["overall"]) == 57
    assert out[0]["items"] == {"획순": 85.0, "모양": 100.0}


def test_session_with_no_scores_is_skipped():
    assert summarize_canvas_sessions({"s1": [_row(None, None, ["unscorable"])]}) == []


def test_legacy_rows_without_item_scores_count_for_overall_only():
    out = summarize_canvas_sessions({"s1": [_row(80, None), _row(60, None)]})
    assert out[0]["overall"] == 70.0 and out[0]["items"] == {}


def test_none_axis_scores_are_excluded_not_zero():
    out = summarize_canvas_sessions({"s1": [_row(100, {"획순": 100, "짜임새": None})]})
    assert out[0]["items"] == {"획순": 100.0}
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest tests/test_dashboard_canvas_sessions.py -q`
Expected: `ImportError: cannot import name 'summarize_canvas_sessions'`

- [ ] **Step 3: 구현**

`dashboard_service.py`에서 `from app.services.ai_adapters import canvas_item_scores`, `_canvas_item_scores`, `_is_unscorable`를 지우고 아래 함수를 추가한다. `get_dashboard_data`의 캔버스 루프(`c_sessions = []` … `c_sessions.append({...})`)는 `c_sessions = summarize_canvas_sessions(canvas_by_session)` 한 줄로 바꾼다.

```python
def summarize_canvas_sessions(rows_by_session: dict[str, list[CanvasAnalysisResult]]) -> list[dict]:
    """세션별 종합 점수와 축별 평균 (2026-10-08 재설계).

    - 종합 = 점수가 있는 글자의 평균. 문장의 거부 글자는 0점으로 저장돼 평균을 끌어내리고,
      낱자·한 글자의 거부 세션은 전부 None이라 집계에서 빠진다.
    - 축 = 저장된 item_scores의 축별 평균. None(미측정)은 분모에서 빠진다 — 0으로 세면
      "안 잰 축이 최악"이 된다. 컬럼이 없는 이전 행은 축 집계에서 빠진다(종합은 들어간다).
    """
    sessions = []
    for rows in rows_by_session.values():
        scored = [r.overall_score for r in rows if r.overall_score is not None]
        if not scored:
            continue
        item_acc: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            for axis, score in (r.item_scores or {}).items():
                if score is not None:
                    item_acc[axis].append(float(score))
        sessions.append({
            "overall": sum(scored) / len(scored),
            "date": rows[0].created_at.date(),
            "items": {k: sum(v) / len(v) for k, v in item_acc.items()},
        })
    return sessions
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest tests -q`
Expected: `7 passed`

- [ ] **Step 5: 커밋(사용자 요청 시)**

```bash
git add backend/app/services/dashboard_service.py backend/tests/test_dashboard_canvas_sessions.py
git commit -m "feat(backend): 대시보드를 저장된 축 점수로 집계"
```

---

### Task 7: 앱 — `axes` 파싱, 글자 이름 표기

**Files:**
- Modify: `frontend/lib/features/canvas_mode/models/canvas_char_analysis.dart` — `itemScores` → `axes`
- Modify: `frontend/lib/features/canvas_mode/services/canvas_api_service.dart:209` — mock의 `itemScores: const {}` → `axes: const {}`
- Modify: `frontend/lib/features/feedback/screens/feedback_screen.dart` — 우측 패널 줄 형식(글자 박스는 `원 — …`), 성분 탭 문구
- Test: `frontend/test/models/canvas_char_analysis_test.dart` 갱신

**Interfaces:**
- Produces: `CanvasCharAnalysis.axes: Map<String, dynamic>` (`{"획순": {"score": 100, "reasons": [...]}, ...}`), `CanvasCharAnalysis.axisScore(String axis) -> int?`.
- 우측 패널 줄: 성분 박스는 `'${role} "${jamo}" — ${reasons}'`(지금과 같음), 글자 박스(role == '글자')는 `'${jamo} — ${reasons}'`.

- [ ] **Step 1: 실패하는 테스트 추가** (`canvas_char_analysis_test.dart`의 `main()` 안에)

```dart
  group('axes', () {
    test('축 점수를 읽고, 미측정은 null로 둔다', () {
      final a = CanvasCharAnalysis.fromJson({
        'char_id': 'char_0',
        'axes': {
          '획순': {'score': 100, 'reasons': <String>[]},
          '모양': {'score': 70, 'reasons': ['1획 기울어짐']},
          '짜임새': {'score': null, 'reasons': <String>[]},
          '배치': {'score': null, 'reasons': <String>[]},
        },
        'speed_profile': {'mean_speed_px_per_ms': 0.5},
        'overall_score': 85,
        'correction_flags': <String>[],
      });
      expect(a.axisScore('획순'), 100);
      expect(a.axisScore('모양'), 70);
      expect(a.axisScore('짜임새'), isNull);
      expect(a.axisScore('없는축'), isNull);
    });
  });
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && flutter test test/models/canvas_char_analysis_test.dart`
Expected: 컴파일 오류 `The method 'axisScore' isn't defined`.

- [ ] **Step 3: 모델 구현**

`canvas_char_analysis.dart`: `final Map<String, dynamic> itemScores;` →

```dart
  /// 채점 축 — {"획순": {"score": 100|70|40|null, "reasons": [...]}, "모양": ..., "짜임새": ..., "배치": ...}.
  /// 단계마다 측정되는 축이 다르다(자모음: 획순·모양 / 한 글자: +짜임새 / 문장: +배치).
  /// null은 미측정이다 — 0이나 100으로 채우지 말 것.
  final Map<String, dynamic> axes;
```
생성자 `required this.axes`, `fromJson`은 `axes: (json['axes'] as Map<String, dynamic>?) ?? const {}`. 메서드 추가:

```dart
  /// 축 점수. 축이 없거나 미측정이면 null.
  int? axisScore(String axis) =>
      ((axes[axis] as Map<String, dynamic>?)?['score'] as num?)?.toInt();
```
`canvas_api_service.dart:209`의 mock 인자 이름을 `axes`로.

- [ ] **Step 4: 우측 패널 줄 형식**

`feedback_screen.dart`의 `redComponents.map((c) => … Text('${c.role} "${c.jamo}" — ${c.failedItems.join(', ')}' …)` 부분을:

```dart
                      child: Text(
                        c.role == '글자'
                            ? '${c.jamo} — ${c.failedItems.join(', ')}'
                            : '${c.role} "${c.jamo}" — ${c.failedItems.join(', ')}',
```
`_componentMessage(item)`(박스 탭 문구)도 같은 분기로 `'${item.jamo} — 고칠 곳: …'`. `grep -n itemScores`로 남은 참조를 모두 `axes`로 바꾼다.

- [ ] **Step 5: 통과 확인**

Run: `cd frontend && flutter test test/models test/widgets test/utils test/services && dart analyze lib test`
Expected: 모두 통과, `dart analyze`에 `error` 없음(기존 warning 4건은 그대로).

- [ ] **Step 6: 커밋(사용자 요청 시)**

```bash
git add frontend/lib/features/canvas_mode/models/canvas_char_analysis.dart frontend/lib/features/canvas_mode/services/canvas_api_service.dart frontend/lib/features/feedback/screens/feedback_screen.dart frontend/test/models/canvas_char_analysis_test.dart
git commit -m "feat(app): 캔버스 채점 축 표시 — 글자 단위 사유 줄"
```

---

### Task 8: 통합 확인

**Files:** 없음(실행만)

- [ ] **Step 1: AI 전체 테스트** — `PYTHONIOENCODING=utf-8 C:\ai_venv\Scripts\python.exe -m pytest ai/tests -q` → 전부 PASS.
- [ ] **Step 2: 백엔드 테스트·마이그레이션** — `cd backend && C:\ai_venv\Scripts\python.exe -m pytest tests -q && C:\ai_venv\Scripts\python.exe -m alembic current` → PASS, `a1f3c5e7b9d2 (head)`.
- [ ] **Step 3: 서버 스모크** — `cd backend && C:\ai_venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`을 띄우고, `/api/v1/canvas/analyze` → `/group`을 '시원한'으로 호출해 200·글자별 획 수 `[3, 6, 6]`을 확인한다(Firebase 토큰이 없어 `/analyze-detail`은 422가 정상). 끝나면 서버를 내린다.
- [ ] **Step 4: 앱** — `cd frontend && flutter test test/models test/widgets test/utils test/services && dart analyze lib test` → PASS, error 0.
- [ ] **Step 5: 실기기 확인(사용자)** — 자모음 1자, 한 글자 1자, 문장 1개를 써서 우측 패널에 축 이름 사유가 글자별로 나오는지, 문장에서 글자 박스가 문제 글자에만 그려지는지 본다.
