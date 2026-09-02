"""
SFR-005I: 손글씨 평가 — handwriting_evaluation.md 지표 1~6 + 명료도

입력: craft_detect_chars() 결과 (char_id, bounding_box, angle, angle_reliable,
      confidence). binary_image 인자는 계약 유지를 위해 남기나 현재 미사용
      (2026-07-27 T4: 획 굵기 지표 제거로 이진 이미지 소비자 없음).
출력: SizeAngleResult — per-char 분석 + 지표별 등급/점수 + 종합 점수 + 피드백

평가 지표 (ai/handwriting_evaluation.md 기준, 2026-07-27 T4 재편)
------------------------------------------------------------------
1. 글자 높이 균일성   — 높이 CV        (<10% 우수 / 10~20 보통 / ≥20 불량)
2. 문장 기울기        — 행별 중심선 회귀 기울기의 |평균 각도|(수평 이탈) (<3° / 3~7 / ≥7)
3. 자간 균등성        — 행 내 인접 박스 간격 CV (<15% / 15~30 / ≥30)
4. 행간 균등성        — 행 기준선 간격 CV       (<10% / 10~20 / ≥20)
5. 기준선 이탈도      — 행 회귀선 잔차 σ ÷ 평균 글자 높이 (<5% / 5~15 / ≥15)
(제거) 획 굵기 균일성 · 글자별 slant 일관성 — 2026-07-27 T4에서 제외(문장 기울기로 대체)
(제외 확정) 자소 내부 비율 — 이미지 모드 목적과 불일치
+ 명료도(clarity)     — 탐지 이상(병합 의심 과폭·기울기 이상치·저신뢰) 글자 감점

설계 노트
--------
- 문장 기울기(2026-07-27 T4): 개별 글자 slant가 아니라 **행별 글자 중심선의 회귀 기울기**
  (전처리 이미지 좌표 그대로)로 "줄이 수평인가 / 올라가며·내려가며 쓰는가"를 본다. 수평(0°)
  에서 벗어난 |평균 각도|로 점수화(수평 이탈 감점 — 사용자 결정). 개별 글자 지적 문구는 안 낸다.
  (craft의 per-char angle은 char 출력 메타·명료도 이상치 판정에만 남기고 채점엔 미사용.)
- 자간: 띄어쓰기 간격(행 중앙 높이 × WORD_GAP_RATIO 초과)은 제외하고 글자 사이
  간격만 CV 계산. 겹침(음수 간격)은 0으로 클립.
- 명료도: 탐지가 제대로 안 된 글자는 흘림·잘못 이어 씀 등 "못 쓴 글자"로 보고
  감점하되(팀 결정 2026-07-19), 통계 지표에서는 제외해 나머지 글자를 오염시키지
  않는다. 글자가 너무 작은 이미지(행 중앙 높이 < CLARITY_MIN_H)는 탐지 실패가
  모델 한계일 수 있어 명료도 감점을 생략한다.
- 측정 불가한 지표(행 1개뿐인 행간 등)는 skipped로 표기하고 종합 점수에서 제외.
"""
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# ── 글자별 크기 판정 (행 내 중앙값 기준 비율) ──────────────────────────
SIZE_LARGE_THRESH = 1.5   # 50% 초과 크면 large
SIZE_SMALL_THRESH = 0.65  # 35% 이상 작으면 small

# ── 기울기 (craft_detect_chars()의 세로획 slant 기준) ─────────────────
ANGLE_WARN_DEG = 3.0      # 전체 평균이 이 값 초과면 "약간 기울어짐"
ANGLE_FLAG_DEG = 7.0      # 이 값 초과면 "명확히 기울어짐"
TILT_MIN_RELIABLE = 3     # slant 신뢰 글자가 이보다 적으면 기울기 평가 생략
TILT_OUTLIER_DEG = 10.0   # 중앙값에서 이 이상 벗어난 측정값은 이상치로 제외

# ── 지표별 등급 경계 (handwriting_evaluation.md) ──────────────────────
#    (우수 상한, 보통 상한) — 값이 작을수록 좋다
BANDS = {
    "height_uniformity":       (10.0, 20.0),   # CV %
    "tilt_consistency":        (3.0, 7.0),     # 글자 기울기 σ ° (글자끼리 얼마나 고른가)
    "spacing_uniformity":      (15.0, 30.0),   # CV %
    "line_spacing_uniformity": (10.0, 20.0),   # CV %
    "baseline_deviation":      (5.0, 15.0),    # 잔차σ/평균높이 %
}

# ── 글자별 '미흡' 판정 기준 (2026-09-01 신설) ─────────────────────────
# 이미지 모드 바운딩 박스를 초록/빨강 2색으로 칠하기 위한 값. 세 항목만 글자별로
# 판정된다 — 크기·기울기는 **다른 글자들의 평균에서 얼마나 벗어났나**, 줄 정렬은
# **자기 행의 기준선에서 얼마나 벗어났나**. 자간·행간은 글자 하나에 귀속되지 않아
# 박스 색에 영향을 주지 않는다(사용자 결정).
ANGLE_UNIFORM_TOL_DEG = 7.0     # 평균 기울기에서 이 이상 벗어난 글자 = 기울기 미흡
BASELINE_CHAR_TOL_RATIO = 0.25  # 행 기준선에서 (행 중앙 높이 × 이 값) 이상 벗어나면 미흡

# ── 글자 기울기의 **절대** 기울어짐 (2026-09-02 신설, 사용자 요청) ──────────
# '기울기 균일성'은 글자들이 서로 고른가만 본다. 그래서 **전부 똑같이 많이 기울여
# 쓰면 만점**이 나온다 — 고르기는 고르니까. 하지만 그건 "바르게 쓴 글씨"가 아니다.
# 그래서 기울기의 **중앙값 자체가 수직에서 얼마나 벗어났나**를 따로 본다.
#
# 값 근거: NORM_STROKE_RESEARCH.md ①의 문헌 실험(세로획 기준) — 0~4°는 곧게 쓴
# 글씨로 인식, 5~10°는 뚜렷이 기울어진 글씨, 12°부터 과도. "너무 기울여 쓴다"는
# 단순한 '눈에 띔'보다 강한 지적이므로 뚜렷이 기울어진 대역의 위쪽(10°)을 쓴다.
# ⚠️ 점수에는 반영하지 않고 **문구로만** 알린다. 박스도 치지 않는다(사용자 결정) —
# 글자 하나의 잘못이 아니라 글씨체 전체의 습관이라 특정 글자를 짚을 수 없다.
CHAR_SLANT_NORM_DEG = 10.0

# ── 자간/행간/명료도 파라미터 ─────────────────────────────────────────
WORD_GAP_RATIO = 0.55     # 간격 > 행 중앙 높이 × 이 값 → 띄어쓰기로 보고 자간에서 제외
SPACING_MIN_GAPS = 4      # 자간 CV에 필요한 최소 간격 수
LINESPACE_MIN_ROWS = 3    # 행간 CV에 필요한 최소 행 수
CLARITY_MIN_H = 16.0      # 행 중앙 높이가 이보다 작으면 명료도 감점 생략 (모델 한계 보호)
CLARITY_WIDE_RATIO = 1.6  # 폭 > 행 중앙 높이 × 이 값 → 병합 의심(잘못 이어 씀)
CLARITY_MIN_CONF = 0.35   # confidence가 이보다 낮으면 불명료 의심

# ── 절대 규범 축 임계값 (1.3, 근거: NORM_STROKE_RESEARCH.md 3.3 문헌 조사) ──
#    자기 일관성(종합점수)과 별개 축. 점수 미반영·경고만. 실사용 데이터로 튜닝.
TILT_NORM_DEG = 7.0          # |세로획 평균 slant|가 이 값 초과 → 수직(0°) 이탈 경고
LINE_NORM_MIN_RATIO = 1.0    # 인접 행 baseline 간격 / 평균 글자 높이 하한(미만=겹침)
SPACING_NORM_MIN_CHARS = 15  # 이 미만이면 띄어쓰기 규범 판정 생략(짧은 단어 촬영 보호)


def _grade(value: float, good: float, fair: float) -> str:
    if value < good:
        return "우수"
    if value < fair:
        return "보통"
    return "불량"


def _band_score(value: float, good: float, fair: float) -> float:
    """등급 경계 기준 점수화: 0→100, 우수경계→80, 보통경계→40, 보통경계×2→0."""
    if value <= 0:
        return 100.0
    if value < good:
        return 100.0 - 20.0 * (value / good)
    if value < fair:
        return 80.0 - 40.0 * (value - good) / (fair - good)
    return max(0.0, 40.0 * (1.0 - (value - fair) / fair))


# ── 종합점수 교육적 가중 (정렬·균일 우선 3:2:1, clarity 제외) ──────────
#    2026-07-20 결정. 초기값이며 실사용 데이터로 조정 가능.
WEIGHTS = {
    "height_uniformity":       3,
    "baseline_deviation":      3,
    "line_spacing_uniformity": 3,
    "tilt_consistency":        2,
    "spacing_uniformity":      2,
}


def _weighted_total(metrics: Dict) -> float:
    """측정된 지표(score 보유)만 가중 평균. skipped·clarity는 제외."""
    num = den = 0.0
    for key, w in WEIGHTS.items():
        m = metrics.get(key)
        if m and "score" in m:
            num += m["score"] * w
            den += w
    return round(num / den, 1) if den else 100.0


def _total_grade(score: float) -> str:
    """종합점수(높을수록 좋음) 등급 — _band_score 앵커(80/40)와 정합."""
    if score >= 80.0:
        return "우수"
    if score >= 40.0:
        return "보통"
    return "불량"


@dataclass
class CharAnalysis:
    char_id: str
    size_ratio: float    # char_height / 행_median_height  (1.0 = 정상)
    angle: float          # craft_detect_chars()의 세로획 slant (unmeasured면 0.0)
    size_flag: str        # "normal" | "large" | "small"
    # ⚠️ 2026-09-01부터 **평균 대비 상대 판정**이다. 종전에는 수직(0°)에서 7°를 넘으면
    # 무조건 기울었다고 봤는데, 그러면 글씨체가 원래 비스듬한 사람은 아무리 고르게 써도
    # 전부 빨개진다. 항목 이름이 '기울기 **균일성**'이므로 기준은 **다른 글자들의 평균**이다.
    angle_flag: str       # "normal" | "tilted_cw" | "tilted_ccw" | "unmeasured"
    # 자기 행의 기준선(회귀선)에서 위/아래로 벗어났나 (2026-09-01 신설)
    baseline_flag: str    # "normal" | "above" | "below" | "unmeasured"
    clarity_flag: str     # "clear" | "merged_suspect" | "tilt_outlier" | "low_confidence"

    @property
    def failed_items(self) -> List[str]:
        """이 글자가 걸린 항목 — 하나라도 있으면 박스가 빨강이 된다.

        ★ 종합 점수로 색을 정하지 않는다. 항목을 따로 판정하고 OR로 합친다 —
        캔버스 모드와 같은 규칙이다(가중 평균을 쓰면 한 항목을 크게 틀려도 다른
        항목이 끌어올려 초록이 나온다).
        """
        out: List[str] = []
        if self.size_flag == "large":
            out.append("크기(너무 큼)")
        elif self.size_flag == "small":
            out.append("크기(너무 작음)")
        if self.angle_flag == "tilted_cw":
            out.append("기울기(오른쪽으로 기욺)")
        elif self.angle_flag == "tilted_ccw":
            out.append("기울기(왼쪽으로 기욺)")
        if self.baseline_flag == "above":
            out.append("줄 정렬(위로 벗어남)")
        elif self.baseline_flag == "below":
            out.append("줄 정렬(아래로 벗어남)")
        return out

    @property
    def ok(self) -> bool:
        return not self.failed_items


@dataclass
class SizeAngleResult:
    chars: List[CharAnalysis]
    # ⚠️ 지표 점수는 측정 불가면 None이다(만점 아님). 종전에는 skipped일 때 100.0으로
    # 폴백해서, 재지도 않은 지표로 "잘하고 있다"는 칭찬이 나가고 대시보드 평균까지
    # 오염됐다(DATA_FLOW §4-1). 소비자는 None을 "미측정"으로 다루고 집계에서 제외할 것.
    size_uniformity_score: Optional[float]    # 0~100 (지표 1)
    mean_angle: float               # degrees (이상치 제외 후 평균)
    angle_std: float                # degrees (이상치 제외 후 편차)
    # 지표 2 = 글자 기울기 **균일성**(σ). 잴 수 있는 글자가 3자 미만이면 None.
    tilt_consistency_score: Optional[float]
    # 글자 기울기의 **중앙값**(도, 양수=오른쪽으로 기욺). 균일성과 별개 축 —
    # 전부 똑같이 많이 기울여 쓰면 균일성은 만점이지만 이 값이 크다.
    # 잴 수 있는 글자가 3자 미만이면 None(미측정). 점수 미반영·문구 전용.
    mean_char_slant: Optional[float]
    # 글줄이 올라가며/내려가며 쓰였나 — 점수가 아니라 줄 정렬 문구의 방향으로 쓴다.
    overall_tilt: str               # "straight" | "falling" | "rising"
    line_alignment_score: Optional[float]     # 0~100 (지표 5) — 행별 글자 수 부족이면 None
    total_score: float              # 교육적 가중(3:2:1) 평균, clarity 제외 (skipped 제외)
    total_grade: str                # 종합점수 등급 (우수/보통/불량)
    metrics: Dict = field(default_factory=dict)  # 지표별 {value, grade, score, ...}
    issues: List[str] = field(default_factory=list)
    clarity_warnings: List[str] = field(default_factory=list)  # 명료도 경고 (점수 미반영)
    norm_deviations: Dict = field(default_factory=dict)  # 절대 규범 축 (점수 미반영, 경고만)


class SizeAngleAnalyzer:

    def analyze(self, chars: List[Dict],
                binary_image: Optional[np.ndarray] = None) -> SizeAngleResult:
        if not chars:
            # 글자가 하나도 없으면 아무 지표도 못 잰 것이다 → 전부 None.
            # (total_score만은 기존 계약이 int라 100.0을 유지한다. 이 경로는 탐지 0개일
            #  때만 닿으며, 그 경우 프론트가 먼저 재촬영을 안내한다.)
            return SizeAngleResult(
                chars=[], size_uniformity_score=None, mean_angle=0.0,
                angle_std=0.0, tilt_consistency_score=None,
                mean_char_slant=None,
                overall_tilt="straight", line_alignment_score=None,
                total_score=100.0, total_grade="우수", metrics={}, issues=[],
                clarity_warnings=[],
                norm_deviations={
                    "tilt":         {"violated": False, "evaluated": False},
                    "spacing":      {"violated": False, "evaluated": False},
                    "line_spacing": {"violated": False, "evaluated": False},
                },
            )

        rows = self._group_by_row(chars)
        rows.sort(key=lambda r: np.mean(
            [c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2 for c in r]))
        for r in rows:
            r.sort(key=lambda c: c["bounding_box"]["x"])

        metrics: Dict = {}
        issues: List[str] = []

        # ── 명료도 플래그 (통계 오염 방지를 위해 먼저 판정) ──────────
        clarity = self._clarity_flags(chars, rows)
        clear_ids = {cid for cid, f in clarity.items() if f == "clear"}

        # ── per-char 플래그 + 지표 1 (명료 글자만 집계) ──────────────
        # 기준선 이탈은 행 회귀선이 있어야 정해지므로 _baseline을 먼저 부른다.
        baselines, baseline_metric, baseline_flags = self._baseline(rows, clear_ids)
        char_analyses = self._per_char(chars, rows, clarity, baseline_flags)
        heights = np.array(
            [c["bounding_box"]["height"] for c in chars
             if c["char_id"] in clear_ids], dtype=np.float32)
        if len(heights) < 3:   # 명료 글자가 너무 적으면 전체로 계산
            heights = np.array([c["bounding_box"]["height"] for c in chars],
                               dtype=np.float32)
        cv = float(np.std(heights) / np.mean(heights) * 100) if np.mean(heights) > 0 else 0.0
        metrics["height_uniformity"] = self._metric(cv, "height_uniformity", "%")

        # ── 지표 2: 글자 기울기 균일성 ───────────────────────────────
        # ⚠️ 2026-09-01에 **재는 대상이 바뀌었다**(사용자 결정). 종전에는 "글줄이
        # 올라가며/내려가며 쓰이는가"(문서 전체에 값 1개)였는데, 그 값으로는 글자마다
        # 색을 칠할 수 없어 화면에서 어느 글자가 문제인지 짚어 줄 수 없었다.
        # 이제 **글자들끼리 기울기가 고른가**(각도 σ)를 본다 — 항목 이름 그대로다.
        # 줄이 올라가나 내려가나는 아래 _sentence_tilt가 계속 재서, '줄 정렬' 문구의
        # 방향("오른쪽으로 기울어졌습니다")으로 쓰인다.
        metrics["tilt_consistency"] = self._tilt_uniformity(chars, clarity)

        # 줄 방향 — 점수 항목이 아니라 줄 정렬 문구의 방향과 규범 경고에 쓴다.
        tilt = self._sentence_tilt(rows, clear_ids)

        # ── 지표 3: 자간 ─────────────────────────────────────────────
        metrics["spacing_uniformity"] = self._spacing(rows, clear_ids)

        # ── 지표 4·5: 행간 / 줄 정렬 ─────────────────────────────────
        # ⚠️ 줄 정렬은 **두 가지를 같이** 본다(사용자 결정 2026-09-01).
        #   ① 그 줄이 수평인가        — 기울어져 쓰였나 (tilt)
        #   ② 글자가 그 줄에 앉았나   — 회귀선 잔차 (baseline)
        # 잔차만 보면 **비스듬히 반듯하게 쓴 글**이 만점이 된다 — 회귀선이 기울기를
        # 통째로 흡수하기 때문이다(2026-09-01 실측: 5.7° 내려가는 글이 줄 정렬 100점).
        # 둘 중 **나쁜 쪽**을 항목 점수로 삼는다 — 하나만 어긋나도 줄은 안 맞은 것이다.
        metrics["baseline_deviation"] = self._line_alignment(baseline_metric, tilt["metric"])
        metrics["line_spacing_uniformity"] = self._line_spacing(baselines)

        # ── 명료도: 경고만 (점수 미반영, 2026-07-20 결정) ────────────
        # clarity_flag는 위 지표들의 통계 오염 방지 게이트로만 쓰고, 종합점수엔
        # 반영하지 않는다(모델 탐지 한계를 사용자 필체 탓으로 돌리는 것 방지).
        # "__gated__" 메타키(bool)는 집계에서 제외.
        n_flag = sum(1 for k, f in clarity.items()
                     if k != "__gated__" and f != "clear")
        gated = clarity.get("__gated__", False)
        clarity_warnings: List[str] = []
        if not gated and n_flag > 0:
            clarity_warnings.append(
                f"또렷하게 구분되지 않는 글자가 {n_flag}자 있습니다 "
                f"(흘려 쓰거나 옆 글자와 이어 쓴 것으로 보임)")

        # ── 종합 점수 (교육적 가중 3:2:1, clarity 제외, skipped 제외) ──
        total = _weighted_total(metrics)

        # ── 절대 규범 축 (1.3) — 종합점수와 별개, 경고만 ─────────────
        norm_deviations = self._norm_deviations(rows, tilt, baselines, clear_ids)

        # ── 피드백 문구 ──────────────────────────────────────────────
        issues += self._issues_size(metrics["height_uniformity"], char_analyses)
        issues += tilt["issues"]
        issues += self._issues_generic(
            metrics["spacing_uniformity"], "자간이 고르지 않습니다",
            "자간을 조금 더 일정하게 써보세요", "간격 CV")
        issues += self._issues_generic(
            metrics["line_spacing_uniformity"], "줄 간격이 고르지 않습니다",
            "줄 간격을 조금 더 일정하게 맞춰보세요", "행간 CV")
        issues += self._issues_generic(
            metrics["baseline_deviation"], "글자들이 기준선에서 많이 벗어납니다",
            "기준선을 조금 더 맞춰 써보세요", "이탈도")
        # 규범 이탈 경고도 issues에 노출(자간·행간). 기울기 규범은 위 tilt issues와
        # 중복되므로 구조화된 norm_deviations에만 담는다.
        for axis in ("spacing", "line_spacing"):
            msg = norm_deviations[axis].get("message")
            if msg:
                issues.append(msg)

        return SizeAngleResult(
            chars=char_analyses,
            # 측정 불가(skipped)면 None — 만점으로 덮지 않는다(DATA_FLOW §4-1).
            size_uniformity_score=metrics["height_uniformity"].get("score"),
            mean_angle=tilt["mean"], angle_std=tilt["std"],
            # ⚠️ 이제 '글줄의 수평 이탈'이 아니라 **글자 기울기 균일성**이다(위 지표 2).
            # 줄이 올라가나 내려가나는 overall_tilt/mean_angle에 그대로 남아 있다.
            tilt_consistency_score=metrics["tilt_consistency"].get("score"),
            # per-char 기울기 판정의 기준값과 **같은 값**을 싣는다 — 화면 문구와
            # 빨간 박스가 서로 다른 기준을 말하지 않도록.
            mean_char_slant=(None if (_ref := self._reference_angle(chars)) is None
                             else round(_ref, 2)),
            overall_tilt=tilt["overall"],
            line_alignment_score=metrics["baseline_deviation"].get("score"),
            total_score=total, total_grade=_total_grade(total),
            metrics=metrics, issues=issues, clarity_warnings=clarity_warnings,
            norm_deviations=norm_deviations,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _metric(value: float, key: str, unit: str, **extra) -> Dict:
        good, fair = BANDS[key]
        return {"value": round(value, 1), "unit": unit,
                "grade": _grade(value, good, fair),
                "score": round(_band_score(value, good, fair), 1), **extra}

    def _clarity_flags(self, chars: List[Dict], rows: List[List[Dict]]) -> Dict:
        """글자별 명료도 판정. 탐지 이상 신호 = 못 쓴 글자(팀 결정)."""
        flags: Dict = {}
        med_h_all = float(np.median(
            [c["bounding_box"]["height"] for c in chars]))
        if med_h_all < CLARITY_MIN_H:
            # 글자가 너무 작으면 탐지 실패가 필체 탓인지 모델 한계인지 구분 불가
            flags = {c["char_id"]: "clear" for c in chars}
            flags["__gated__"] = True
            return flags
        # 기울기 이상치 (습관 slant에서 이탈)
        rel = [(c["char_id"], float(c.get("angle", 0.0))) for c in chars
               if c.get("angle_reliable", True)]
        tilt_out = set()
        if len(rel) >= TILT_MIN_RELIABLE:
            med = float(np.median([a for _, a in rel]))
            tilt_out = {cid for cid, a in rel if abs(a - med) > TILT_OUTLIER_DEG}
        for row in rows:
            row_h = float(np.median([c["bounding_box"]["height"] for c in row]))
            for c in row:
                cid = c["char_id"]
                if c["bounding_box"]["width"] > row_h * CLARITY_WIDE_RATIO:
                    flags[cid] = "merged_suspect"
                elif cid in tilt_out:
                    flags[cid] = "tilt_outlier"
                elif float(c.get("confidence", 1.0)) < CLARITY_MIN_CONF:
                    flags[cid] = "low_confidence"
                else:
                    flags[cid] = "clear"
        flags["__gated__"] = False
        return flags

    def _reference_angle(self, chars: List[Dict]) -> Optional[float]:
        """글자 기울기의 **기준값** — 신뢰 가능한 각도들의 중앙값.

        평균이 아니라 중앙값을 쓰는 이유: 한 글자가 크게 튀면 평균이 그쪽으로 끌려가
        **멀쩡한 글자들이 되레 '평균에서 벗어났다'고 빨개진다.** 중앙값은 정상 글자
        쪽에 남아, 튄 글자만 편차로 드러난다(캔버스 성분 비율에서 쓴 것과 같은 이유).
        """
        vals = [float(c.get("angle", 0.0)) for c in chars
                if c.get("angle_reliable", True)]
        if len(vals) < TILT_MIN_RELIABLE:
            return None
        return float(np.median(vals))

    def _per_char(self, chars: List[Dict], rows: List[List[Dict]],
                  clarity: Dict,
                  baseline_flags: Optional[Dict[str, str]] = None) -> List[CharAnalysis]:
        baseline_flags = baseline_flags or {}
        ref_angle = self._reference_angle(chars)
        out = {}
        for row in rows:
            row_h = float(np.median([c["bounding_box"]["height"] for c in row]))
            for c in row:
                ratio = c["bounding_box"]["height"] / row_h if row_h > 0 else 1.0
                if ratio > SIZE_LARGE_THRESH:
                    size_flag = "large"
                elif ratio < SIZE_SMALL_THRESH:
                    size_flag = "small"
                else:
                    size_flag = "normal"
                angle = float(c.get("angle", 0.0))
                # 기준은 수직(0°)이 아니라 **다른 글자들의 기울기**다 — 항목이
                # '기울기 균일성'이기 때문. 글씨체가 원래 비스듬해도 고르게만 쓰면 통과한다.
                if not c.get("angle_reliable", True) or ref_angle is None:
                    angle_flag = "unmeasured"
                elif angle - ref_angle > ANGLE_UNIFORM_TOL_DEG:
                    angle_flag = "tilted_cw"
                elif angle - ref_angle < -ANGLE_UNIFORM_TOL_DEG:
                    angle_flag = "tilted_ccw"
                else:
                    angle_flag = "normal"
                out[c["char_id"]] = CharAnalysis(
                    char_id=c["char_id"], size_ratio=round(ratio, 3),
                    angle=round(angle, 2), size_flag=size_flag,
                    angle_flag=angle_flag,
                    baseline_flag=baseline_flags.get(c["char_id"], "unmeasured"),
                    clarity_flag=clarity.get(c["char_id"], "clear"))
        return [out[c["char_id"]] for c in chars]

    @staticmethod
    def _line_alignment(baseline_metric: Dict, tilt_metric: Dict) -> Dict:
        """줄 정렬 = (줄이 수평인가) 와 (글자가 줄에 앉았나) 중 **나쁜 쪽**.

        둘 중 하나만 측정됐으면 그것을 쓰고, 둘 다 못 쟀으면 skipped를 유지한다 —
        안 잰 지표로 감점하지 않기 위함(DATA_FLOW §4-1). `driver`에 어느 쪽이
        점수를 결정했는지 남겨, 나중에 문구를 세분화할 때 쓸 수 있게 한다.
        """
        scored = [(m, key) for m, key in ((baseline_metric, "baseline"), (tilt_metric, "tilt"))
                  if m and "score" in m]
        if not scored:
            return baseline_metric
        worst, driver = min(scored, key=lambda t: t[0]["score"])
        out = dict(worst)
        out["driver"] = driver
        return out

    def _tilt_uniformity(self, chars: List[Dict], clarity: Dict) -> Dict:
        """지표 2 — **글자들끼리 기울기가 고른가** (2026-09-01 신설).

        수직(0°)에서 얼마나 벗어났나가 아니라 **서로 얼마나 다른가**(표준편차)를 본다.
        글씨체가 원래 비스듬한 사람도 고르게만 쓰면 만점이다. 수직 규범 이탈은
        점수가 아니라 norm_deviations의 경고로만 나간다(2026-07-20 결정 유지).
        """
        # ⚠️ 여기서 이상치(크게 기운 글자)를 빼면 안 된다. 그 글자야말로 '기울기가
        # 고르지 않다'는 증거인데, 빼고 나면 **박스는 빨간데 점수는 100점**이 된다
        # (2026-09-01 실측: 한 글자만 16° 기울였더니 σ=0, 점수 100).
        #
        # 특히 clarity의 "tilt_outlier"로 거르면 안 된다 — 그 플래그 자체가 **각도로**
        # 정해지므로, 기울기 지표가 정작 기운 글자를 영영 못 보는 순환이 된다.
        # 걸러야 할 것은 **탐지가 의심스러운 글자**(병합 의심·저신뢰)뿐이다.
        _DETECTION_SUSPECT = {"merged_suspect", "low_confidence"}
        vals = [float(c.get("angle", 0.0)) for c in chars
                if c.get("angle_reliable", True)
                and clarity.get(c["char_id"], "clear") not in _DETECTION_SUSPECT]
        if len(vals) < TILT_MIN_RELIABLE:
            return {"skipped": f"기울기를 잴 수 있는 글자가 {TILT_MIN_RELIABLE}자 미만"}
        return self._metric(float(np.std(vals)), "tilt_consistency", "°")

    def _sentence_tilt(self, rows: List[List[Dict]], clear_ids: set) -> Dict:
        """문장 기울기 — 행별 글자 중심선의 회귀 기울기(전처리 좌표 그대로).

        개별 글자 slant가 아니라 "줄이 수평인가 / 올라가며·내려가며 쓰는가"(필기 습관)를
        본다(2026-07-27 T4, deskew 이전이 아니라 전처리 이미지 좌표에서 측정 — 사용자 결정).
        점수는 수평(0°)에서 벗어난 |평균 각도|로 매긴다(수평 이탈 감점 — 사용자 결정).
        부호: 이미지 좌표는 y가 아래로 증가 → 양수=하강(내려감), 음수=상승(올라감).
        """
        angles = []
        for row in rows:
            pts = [(c["bounding_box"]["x"] + c["bounding_box"]["width"] / 2.0,
                    c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2.0)
                   for c in row if c["char_id"] in clear_ids]
            if len(pts) < 3:
                pts = [(c["bounding_box"]["x"] + c["bounding_box"]["width"] / 2.0,
                        c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2.0)
                       for c in row]
            if len(pts) < 3:
                continue
            xs = np.array([p[0] for p in pts], dtype=np.float32)
            ys = np.array([p[1] for p in pts], dtype=np.float32)
            if float(np.ptp(xs)) < 1.0:      # 세로로만 늘어선 행은 기울기 정의 불가
                continue
            slope = float(np.polyfit(xs, ys, 1)[0])
            angles.append(float(np.degrees(np.arctan(slope))))
        if not angles:
            return {"mean": 0.0, "std": 0.0, "overall": "straight", "issues": [],
                    "metric": {"skipped": "기울기를 잴 수 있는 행(3글자 이상)이 부족"}}
        mean_a = float(np.mean(angles))
        std_a = float(np.std(angles))
        dev = abs(mean_a)
        overall = ("falling" if mean_a > ANGLE_WARN_DEG else
                   "rising" if mean_a < -ANGLE_WARN_DEG else "straight")
        issues = []
        if dev > ANGLE_FLAG_DEG:
            d = "내려가며" if mean_a > 0 else "올라가며"
            issues.append(f"글씨 줄이 전체적으로 {d} {dev:.1f}° 기울어 수평에서 벗어납니다")
        elif dev > ANGLE_WARN_DEG:
            d = "내려가며" if mean_a > 0 else "올라가며"
            issues.append(f"글씨 줄이 약간 {d}({dev:.1f}°) 기울어 있습니다")
        metric = self._metric(dev, "tilt_consistency", "°", n_rows=len(angles))
        return {"mean": round(mean_a, 2), "std": round(std_a, 2),
                "overall": overall, "issues": issues, "metric": metric}

    def _spacing(self, rows: List[List[Dict]], clear_ids: set) -> Dict:
        """자간 균등성 — 인접 글자 중심 간 거리(pitch)의 CV.

        handwriting_evaluation.md는 '박스 사이 거리'라고 쓰여 있으나, 붙여 쓴
        손글씨는 모서리 간격 평균이 0에 수렴해 CV가 무의미하게 폭주한다
        (실측: test3_crop 151%). 중심 간 거리는 항상 양수라 안정적이며 같은
        등급 경계(15/30%)를 적용해도 체감과 일치 — 문서에 각주로 기록함.
        """
        pitches = []
        for row in rows:
            row_h = float(np.median([c["bounding_box"]["height"] for c in row]))
            word_gap = row_h * WORD_GAP_RATIO
            for a, b in zip(row, row[1:]):
                if a["char_id"] not in clear_ids or b["char_id"] not in clear_ids:
                    continue   # 병합 의심 박스가 만드는 가짜 간격 제외
                edge_gap = b["bounding_box"]["x"] - (
                    a["bounding_box"]["x"] + a["bounding_box"]["width"])
                if edge_gap > word_gap:
                    continue   # 띄어쓰기 경계는 자간 평가에서 제외
                pitch = (b["bounding_box"]["x"] + b["bounding_box"]["width"] / 2) - (
                    a["bounding_box"]["x"] + a["bounding_box"]["width"] / 2)
                if pitch > 0:
                    pitches.append(pitch)
        if len(pitches) < SPACING_MIN_GAPS:
            return {"skipped": "측정 가능한 글자 간격이 부족해 자간 평가 생략"}
        pitches = np.array(pitches, dtype=np.float32)
        cv = float(np.std(pitches) / np.mean(pitches) * 100)
        return self._metric(cv, "spacing_uniformity", "%", n_gaps=len(pitches))

    def _baseline(self, rows: List[List[Dict]], clear_ids: set):
        """행별 회귀선 적합 → (행 기준선 y 목록, 지표5 metric, 글자별 이탈 플래그).

        글자별 플래그는 2026-09-01에 추가됐다 — 화면에서 **기준선을 벗어난 글자만**
        빨간 박스로 짚어 주기 위해서다(사용자 결정). 기준선은 행마다 따로 잡으므로
        줄이 기울어져 있어도 "그 줄 안에서 튀는 글자"를 골라낸다.
        """
        ratios, baselines = [], []
        flags: Dict[str, str] = {}
        for row in rows:
            pts = [(c["bounding_box"]["x"] + c["bounding_box"]["width"] / 2,
                    c["bounding_box"]["y"] + c["bounding_box"]["height"])
                   for c in row if c["char_id"] in clear_ids]
            if len(pts) < 2:
                pts = [(c["bounding_box"]["x"] + c["bounding_box"]["width"] / 2,
                        c["bounding_box"]["y"] + c["bounding_box"]["height"])
                       for c in row]
            xs = np.array([p[0] for p in pts], dtype=np.float32)
            ys = np.array([p[1] for p in pts], dtype=np.float32)
            row_h = float(np.median([c["bounding_box"]["height"] for c in row]))
            if len(pts) >= 3:
                coef = np.polyfit(xs, ys, 1)          # 회귀선 (기울어진 행도 허용)
                resid = ys - np.polyval(coef, xs)
                if row_h > 0:
                    ratios.append(float(np.std(resid)) / row_h * 100)
                mid_x = float(np.mean(xs))
                baselines.append(float(np.polyval(coef, mid_x)))
                # 이 행의 기준선에서 얼마나 벗어났나 — 행 높이에 대한 비율로 본다.
                # y는 아래로 증가하므로 잔차가 양수면 기준선보다 아래로 처진 글자다.
                #
                # ⚠️ 잔차를 **중앙값으로 다시 맞춘다.** 회귀선은 최소제곱이라 크게 튄
                # 글자 하나가 선을 통째로 끌어당기고, 그러면 **멀쩡한 이웃 글자들이
                # 되레 '줄에서 벗어났다'고 빨개진다**(2026-09-01 실측: 한 글자만 키를
                # 1.75배로 키웠더니 옆 글자까지 빨강). 중앙값은 정상 글자 쪽에 남으므로
                # 튄 글자만 편차로 드러난다 — 캔버스 성분 비율에서 쓴 것과 같은 보정이다.
                tol = row_h * BASELINE_CHAR_TOL_RATIO
                all_resid = {
                    c["char_id"]: float(
                        c["bounding_box"]["y"] + c["bounding_box"]["height"]
                        - np.polyval(coef, c["bounding_box"]["x"]
                                     + c["bounding_box"]["width"] / 2))
                    for c in row
                }
                center = float(np.median(list(all_resid.values())))
                for cid, raw in all_resid.items():
                    r = raw - center
                    if tol <= 0:
                        flags[cid] = "unmeasured"
                    elif r > tol:
                        flags[cid] = "below"
                    elif r < -tol:
                        flags[cid] = "above"
                    else:
                        flags[cid] = "normal"
            else:
                baselines.append(float(np.mean(ys)))
                # 글자가 2개 이하인 행은 기준선이 정의되지 않는다 — 안 잰 것으로 둔다.
                for c in row:
                    flags[c["char_id"]] = "unmeasured"
        if not ratios:
            return baselines, {"skipped": "행별 글자 수가 부족해 기준선 평가 생략"}, flags
        ratio = float(np.mean(ratios))
        return baselines, self._metric(ratio, "baseline_deviation", "%"), flags

    def _line_spacing(self, baselines: List[float]) -> Dict:
        if len(baselines) < LINESPACE_MIN_ROWS:
            return {"skipped": "행이 부족해 행간 평가 생략 (3행 이상 필요)"}
        gaps = np.diff(sorted(baselines))
        mean = float(np.mean(gaps))
        if mean <= 0:
            return {"skipped": "행 간격 측정 실패"}
        cv = float(np.std(gaps) / mean * 100)
        return self._metric(cv, "line_spacing_uniformity", "%", n_rows=len(baselines))

    def _norm_deviations(self, rows: List[List[Dict]], tilt: Dict,
                         baselines: List[float], clear_ids: set) -> Dict:
        """절대 규범 축 — 자기 일관성과 별개. **점수 미반영, 경고만.**

        ① 기울기: 문장(행) 평균 기울기 각도의 절대값이 수평(0°)에서 TILT_NORM_DEG 초과 이탈.
        ② 자간: 충분히 긴 글에서 띄어쓰기(어간, 넓은 gap) 군집이 완전히 소실(붙여 씀).
        ③ 행간: 인접 행 baseline 간격 / 평균 글자 높이 < LINE_NORM_MIN_RATIO(줄 겹침).

        각 축: {"violated": bool, "evaluated": bool, "value"?, "message"?}.
        게이트 미충족(짧은 텍스트 등)이면 evaluated=False, violated=False.
        """
        # ── ① 기울기 규범 (세로획 수직 이탈) ──
        if "skipped" in tilt["metric"]:
            tilt_norm = {"violated": False, "evaluated": False,
                         "reason": "기울기를 잴 수 있는 행(3글자 이상)이 부족"}
        else:
            mean_a = tilt["mean"]
            violated = abs(mean_a) > TILT_NORM_DEG
            tilt_norm = {"violated": violated, "evaluated": True,
                         "value": round(abs(mean_a), 1)}
            if violated:
                d = "내려가며" if mean_a > 0 else "올라가며"
                tilt_norm["message"] = (
                    f"글씨 줄이 전체적으로 {d} {abs(mean_a):.0f}° 기울어 "
                    f"수평 규범에서 벗어납니다")

        # ── ② 자간 규범 (띄어쓰기 뭉개짐 — 넓은 gap 군집 소실) ──
        n_clear = n_pairs = n_word = 0
        for row in rows:
            row_h = float(np.median([c["bounding_box"]["height"] for c in row]))
            word_gap = row_h * WORD_GAP_RATIO
            n_clear += sum(1 for c in row if c["char_id"] in clear_ids)
            for a, b in zip(row, row[1:]):
                if a["char_id"] not in clear_ids or b["char_id"] not in clear_ids:
                    continue
                n_pairs += 1
                edge_gap = b["bounding_box"]["x"] - (
                    a["bounding_box"]["x"] + a["bounding_box"]["width"])
                if edge_gap > word_gap:
                    n_word += 1
        if n_clear < SPACING_NORM_MIN_CHARS or n_pairs < SPACING_MIN_GAPS:
            spacing_norm = {"violated": False, "evaluated": False,
                            "reason": "글자·간격 수가 부족(짧은 단어 촬영 등)"}
        else:
            violated = (n_word == 0)
            spacing_norm = {"violated": violated, "evaluated": True,
                            "value": n_word}
            if violated:
                spacing_norm["message"] = (
                    "단어 사이 띄어쓰기가 거의 없어 글이 뭉쳐 보입니다")

        # ── ③ 행간 규범 (줄 겹침) ──
        if len(baselines) < LINESPACE_MIN_ROWS:
            line_norm = {"violated": False, "evaluated": False,
                         "reason": "행이 부족(3행 이상 필요)"}
        else:
            clear_h = [c["bounding_box"]["height"] for row in rows for c in row
                       if c["char_id"] in clear_ids]
            if len(clear_h) < 3:
                clear_h = [c["bounding_box"]["height"] for row in rows for c in row]
            mean_h = float(np.mean(clear_h)) if clear_h else 0.0
            gaps = np.diff(sorted(baselines))
            min_ratio = float(np.min(gaps) / mean_h) if mean_h > 0 else 999.0
            violated = min_ratio < LINE_NORM_MIN_RATIO
            line_norm = {"violated": violated, "evaluated": True,
                         "value": round(min_ratio, 2)}
            if violated:
                line_norm["message"] = (
                    "줄 간격이 좁아 윗줄과 아랫줄이 겹쳐 보입니다")

        return {"tilt": tilt_norm, "spacing": spacing_norm,
                "line_spacing": line_norm}

    # ------------------------------------------------------------------

    def _issues_size(self, metric: Dict, chars: List[CharAnalysis]) -> List[str]:
        issues = []
        if "score" in metric:
            if metric["grade"] == "불량":
                issues.append(f"글자 크기가 고르지 않습니다 (높이 CV {metric['value']}%, 20% 이상은 불량)")
            elif metric["grade"] == "보통":
                issues.append(f"글자 크기를 조금 더 균일하게 써보세요 (높이 CV {metric['value']}%)")
        large = [c.char_id for c in chars if c.size_flag == "large"]
        small = [c.char_id for c in chars if c.size_flag == "small"]
        if large:
            issues.append(f"크게 쓴 글자: {', '.join(large)}")
        if small:
            issues.append(f"작게 쓴 글자: {', '.join(small)}")
        return issues

    @staticmethod
    def _issues_generic(metric: Dict, bad_msg: str, fair_msg: str, label: str) -> List[str]:
        if "score" not in metric:
            return []
        if metric["grade"] == "불량":
            return [f"{bad_msg} ({label} {metric['value']}{metric['unit']})"]
        if metric["grade"] == "보통":
            return [f"{fair_msg} ({label} {metric['value']}{metric['unit']})"]
        return []

    def _group_by_row(self, chars: List[Dict]) -> List[List[Dict]]:
        if not chars:
            return []
        avg_h = np.mean([c["bounding_box"]["height"] for c in chars])
        tol = avg_h * 0.6
        sorted_chars = sorted(chars, key=lambda c: c["bounding_box"]["y"])

        rows: List[List[Dict]] = []
        for c in sorted_chars:
            cy = c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2.0
            placed = False
            for row in rows:
                row_cy = np.mean([
                    r["bounding_box"]["y"] + r["bounding_box"]["height"] / 2.0
                    for r in row
                ])
                if abs(cy - row_cy) < tol:
                    row.append(c)
                    placed = True
                    break
            if not placed:
                rows.append([c])
        return rows


# ------------------------------------------------------------------
# SFR-005I 인터페이스 함수 (AI_MODEL_INTERFACE.md 섹션 4)
# ------------------------------------------------------------------

def analyze_size_angle(chars: List[Dict],
                       binary_image: Optional[np.ndarray] = None) -> Dict:
    """
    AI_MODEL_INTERFACE.md SFR-005I 규격 함수.

    Parameters
    ----------
    chars : craft_detect_chars() 반환값 그대로
    binary_image : (선택) 전처리 binary — 지표 6(획 굵기)에만 사용, 없으면 생략

    Returns
    -------
    Dict — SizeAngleResult 직렬화 (기존 필드 유지 + metrics/total_score 추가)
    """
    result = SizeAngleAnalyzer().analyze(chars, binary_image)
    return {
        "size_uniformity_score":  result.size_uniformity_score,
        "mean_angle":             result.mean_angle,
        "angle_std":              result.angle_std,
        "tilt_consistency_score": result.tilt_consistency_score,
        "mean_char_slant":        result.mean_char_slant,
        "overall_tilt":           result.overall_tilt,
        "line_alignment_score":   result.line_alignment_score,
        "total_score":            result.total_score,
        "total_grade":            result.total_grade,
        "metrics":                result.metrics,
        "issues":                 result.issues,
        "clarity_warnings":       result.clarity_warnings,
        "norm_deviations":        result.norm_deviations,
        "chars": [
            {
                "char_id":      c.char_id,
                "size_ratio":   c.size_ratio,
                "angle":        c.angle,
                "size_flag":    c.size_flag,
                "angle_flag":   c.angle_flag,
                "baseline_flag": c.baseline_flag,
                "clarity_flag": c.clarity_flag,
                # 박스 색은 서버가 이미 정해서 내려준다 — 앱이 점수로 다시
                # 판정하면 항목별 OR 규칙이 깨진다(캔버스와 동일).
                "ok":           c.ok,
                "failed_items": c.failed_items,
            }
            for c in result.chars
        ],
    }
