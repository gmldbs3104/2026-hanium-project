"""
SFR-005I: 손글씨 평가 — handwriting_evaluation.md 지표 1~6 + 명료도

입력: craft_detect_chars() 결과 (char_id, bounding_box, angle, angle_reliable,
      confidence) + (선택) 전처리 binary 이미지 — 획 굵기 측정에만 사용
출력: SizeAngleResult — per-char 분석 + 지표별 등급/점수 + 종합 점수 + 피드백

평가 지표 (ai/handwriting_evaluation.md 기준, 2026-07-19 전면 구현)
------------------------------------------------------------------
1. 글자 높이 균일성   — 높이 CV        (<10% 우수 / 10~20 보통 / ≥20 불량)
2. 기울기 일관성      — slant σ        (<3° 우수 / 3~7 보통 / ≥7 불량)
3. 자간 균등성        — 행 내 인접 박스 간격 CV (<15% / 15~30 / ≥30)
4. 행간 균등성        — 행 기준선 간격 CV       (<10% / 10~20 / ≥20)
5. 기준선 이탈도      — 행 회귀선 잔차 σ ÷ 평균 글자 높이 (<5% / 5~15 / ≥15)
6. 획 굵기 균일성     — distance transform 릿지 폭 CV (<10% / 10~25 / ≥25)
7. (제외 확정) 자소 내부 비율 — 이미지 모드 목적과 불일치
+ 명료도(clarity)     — 탐지 이상(병합 의심 과폭·기울기 이상치·저신뢰) 글자 감점

설계 노트
--------
- 기울기: craft_detect_chars()의 세로획 slant(angle, angle_reliable)를 재사용.
  reliable 글자만 모아 중앙값 ±TILT_OUTLIER_DEG 밖 이상치를 제외(필자의 slant는
  습관적으로 일정하다는 전제)한 뒤 문서 단위 평균·편차를 낸다. 개별 글자 지적
  문구는 내지 않는다.
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
    "tilt_consistency":        (3.0, 7.0),     # σ °
    "spacing_uniformity":      (15.0, 30.0),   # CV %
    "line_spacing_uniformity": (10.0, 20.0),   # CV %
    "baseline_deviation":      (5.0, 15.0),    # 잔차σ/평균높이 %
    "stroke_width_uniformity": (10.0, 25.0),   # CV %
}

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
    "stroke_width_uniformity": 1,
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
    angle_flag: str       # "normal" | "tilted_cw" | "tilted_ccw" | "unmeasured"
    clarity_flag: str     # "clear" | "merged_suspect" | "tilt_outlier" | "low_confidence"


@dataclass
class SizeAngleResult:
    chars: List[CharAnalysis]
    size_uniformity_score: float    # 0~100 (지표 1)
    mean_angle: float               # degrees (이상치 제외 후 평균)
    angle_std: float                # degrees (이상치 제외 후 편차)
    tilt_consistency_score: float   # 0~100 (지표 2)
    overall_tilt: str               # "straight" | "leaning_right" | "leaning_left"
    line_alignment_score: float     # 0~100 (지표 5 — 회귀선 잔차 기반)
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
            return SizeAngleResult(
                chars=[], size_uniformity_score=100.0, mean_angle=0.0,
                angle_std=0.0, tilt_consistency_score=100.0,
                overall_tilt="straight", line_alignment_score=100.0,
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

        # ── per-char 크기 플래그 + 지표 1 (명료 글자만 집계) ─────────
        char_analyses = self._per_char(chars, rows, clarity)
        heights = np.array(
            [c["bounding_box"]["height"] for c in chars
             if c["char_id"] in clear_ids], dtype=np.float32)
        if len(heights) < 3:   # 명료 글자가 너무 적으면 전체로 계산
            heights = np.array([c["bounding_box"]["height"] for c in chars],
                               dtype=np.float32)
        cv = float(np.std(heights) / np.mean(heights) * 100) if np.mean(heights) > 0 else 0.0
        metrics["height_uniformity"] = self._metric(cv, "height_uniformity", "%")

        # ── 지표 2: 기울기 (이상치 조정 포함) ────────────────────────
        tilt = self._tilt(chars, clear_ids)
        metrics["tilt_consistency"] = tilt["metric"]

        # ── 지표 3: 자간 ─────────────────────────────────────────────
        metrics["spacing_uniformity"] = self._spacing(rows, clear_ids)

        # ── 지표 4·5: 행간 / 기준선(회귀선) ──────────────────────────
        baselines, metrics["baseline_deviation"] = self._baseline(rows, clear_ids)
        metrics["line_spacing_uniformity"] = self._line_spacing(baselines)

        # ── 지표 6: 획 굵기 (binary 필요) ────────────────────────────
        metrics["stroke_width_uniformity"] = self._stroke_width(binary_image)

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
        issues += self._issues_generic(
            metrics["stroke_width_uniformity"], "획 굵기가 고르지 않습니다",
            "획 굵기를 조금 더 일정하게 써보세요", "굵기 CV")
        # 규범 이탈 경고도 issues에 노출(자간·행간). 기울기 규범은 위 tilt issues와
        # 중복되므로 구조화된 norm_deviations에만 담는다.
        for axis in ("spacing", "line_spacing"):
            msg = norm_deviations[axis].get("message")
            if msg:
                issues.append(msg)

        return SizeAngleResult(
            chars=char_analyses,
            size_uniformity_score=metrics["height_uniformity"]["score"],
            mean_angle=tilt["mean"], angle_std=tilt["std"],
            tilt_consistency_score=tilt["metric"].get("score", 100.0),
            overall_tilt=tilt["overall"],
            line_alignment_score=metrics["baseline_deviation"].get("score", 100.0),
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

    def _per_char(self, chars: List[Dict], rows: List[List[Dict]],
                  clarity: Dict) -> List[CharAnalysis]:
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
                if not c.get("angle_reliable", True):
                    angle_flag = "unmeasured"
                elif angle > ANGLE_FLAG_DEG:
                    angle_flag = "tilted_cw"
                elif angle < -ANGLE_FLAG_DEG:
                    angle_flag = "tilted_ccw"
                else:
                    angle_flag = "normal"
                out[c["char_id"]] = CharAnalysis(
                    char_id=c["char_id"], size_ratio=round(ratio, 3),
                    angle=round(angle, 2), size_flag=size_flag,
                    angle_flag=angle_flag,
                    clarity_flag=clarity.get(c["char_id"], "clear"))
        return [out[c["char_id"]] for c in chars]

    def _tilt(self, chars: List[Dict], clear_ids: set) -> Dict:
        reliable = np.array(
            [float(c.get("angle", 0.0)) for c in chars
             if c.get("angle_reliable", True)], dtype=np.float32)
        if len(reliable) < TILT_MIN_RELIABLE:
            return {"mean": 0.0, "std": 0.0, "overall": "straight", "issues": [],
                    "metric": {"skipped": "세로획이 있는 글자가 부족해 기울기 평가 생략"}}
        med = float(np.median(reliable))
        inliers = reliable[np.abs(reliable - med) <= TILT_OUTLIER_DEG]
        n_out = len(reliable) - len(inliers)
        mean_a, std_a = float(np.mean(inliers)), float(np.std(inliers))
        overall = ("leaning_right" if mean_a > ANGLE_WARN_DEG else
                   "leaning_left" if mean_a < -ANGLE_WARN_DEG else "straight")
        issues = []
        if abs(mean_a) > ANGLE_FLAG_DEG:
            d = "오른쪽" if mean_a > 0 else "왼쪽"
            issues.append(f"글씨 전체가 {d}으로 {abs(mean_a):.1f}° 기울어져 있습니다")
        elif abs(mean_a) > ANGLE_WARN_DEG:
            d = "오른쪽" if mean_a > 0 else "왼쪽"
            issues.append(f"글씨가 전체적으로 {d}으로 약간({abs(mean_a):.1f}°) 기울어져 있습니다")
        good, fair = BANDS["tilt_consistency"]
        if std_a >= fair:
            issues.append(f"글자들의 기울기가 들쭉날쭉합니다 (편차 {std_a:.1f}°, 7° 이상은 불량)")
        elif std_a >= good:
            issues.append(f"기울기를 조금 더 일정하게 써보세요 (편차 {std_a:.1f}°)")
        metric = self._metric(std_a, "tilt_consistency", "°",
                              n_outlier=n_out, n_unmeasured=len(chars) - len(reliable))
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
        """행별 회귀선 적합 → (행 기준선 y 목록, 지표5 metric)."""
        ratios, baselines = [], []
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
            else:
                baselines.append(float(np.mean(ys)))
        if not ratios:
            return baselines, {"skipped": "행별 글자 수가 부족해 기준선 평가 생략"}
        ratio = float(np.mean(ratios))
        return baselines, self._metric(ratio, "baseline_deviation", "%")

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

        ① 기울기: 세로획 평균 slant의 절대값이 수직(0°)에서 TILT_NORM_DEG 초과 이탈.
        ② 자간: 충분히 긴 글에서 띄어쓰기(어간, 넓은 gap) 군집이 완전히 소실(붙여 씀).
        ③ 행간: 인접 행 baseline 간격 / 평균 글자 높이 < LINE_NORM_MIN_RATIO(줄 겹침).

        각 축: {"violated": bool, "evaluated": bool, "value"?, "message"?}.
        게이트 미충족(짧은 텍스트 등)이면 evaluated=False, violated=False.
        """
        # ── ① 기울기 규범 (세로획 수직 이탈) ──
        if "skipped" in tilt["metric"]:
            tilt_norm = {"violated": False, "evaluated": False,
                         "reason": "세로획이 있는 글자가 부족"}
        else:
            mean_a = tilt["mean"]
            violated = abs(mean_a) > TILT_NORM_DEG
            tilt_norm = {"violated": violated, "evaluated": True,
                         "value": round(abs(mean_a), 1)}
            if violated:
                d = "오른쪽" if mean_a > 0 else "왼쪽"
                tilt_norm["message"] = (
                    f"글씨가 전체적으로 {d}으로 {abs(mean_a):.0f}° 기울어 "
                    f"곧은 형식에서 벗어납니다")

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

    def _stroke_width(self, binary: Optional[np.ndarray]) -> Dict:
        if binary is None:
            return {"skipped": "binary 이미지 미제공으로 획 굵기 평가 생략"}
        import cv2
        dt = cv2.distanceTransform((binary > 0).astype(np.uint8), cv2.DIST_L2, 5)
        # 릿지(획 중심선) 근사: 3×3 이웃 최대값과 같은 지점의 distance 값 × 2 = 획 폭
        ridge = (dt >= cv2.dilate(dt, np.ones((3, 3), np.uint8)) - 1e-6) & (dt >= 0.8)
        widths = dt[ridge] * 2.0
        if len(widths) < 50:
            return {"skipped": "획 픽셀이 부족해 획 굵기 평가 생략"}
        cv_val = float(np.std(widths) / np.mean(widths) * 100)
        return self._metric(cv_val, "stroke_width_uniformity", "%",
                            mean_width_px=round(float(np.mean(widths)), 1))

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
                "clarity_flag": c.clarity_flag,
            }
            for c in result.chars
        ],
    }
