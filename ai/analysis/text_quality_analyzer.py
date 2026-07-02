"""
SFR-005I: 전체 글 품질 분석

측정 항목:
  - 글자 높이 균일성  (행별 CV)
  - 글자 너비 균일성  (행별 CV)
  - 기준선 정렬       (행 내 바닥선 편차)
  - 행 기울기         (수평 여부)
  - 단어 간격 적절성
"""
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

CV_MAX            = 0.30   # CV 30% → 0점
BASELINE_STD_MAX  = 0.20   # baseline_std / median_h 20% → 0점
TILT_MAX_DEG      = 5.0    # 5° → 0점
WORD_GAP_MIN      = 0.3    # char_width 배수 이하 → 너무 좁음
WORD_GAP_MAX      = 3.5    # char_width 배수 이상 → 너무 넓음


@dataclass
class RowQuality:
    row_idx: int
    char_ids: List[str]
    height_cv: float
    width_cv: float
    baseline_std_ratio: float   # std(bottom_y) / median_height
    tilt_deg: float             # degrees (양수=오른쪽 끝이 아래)
    height_score: float         # 0~100
    width_score: float
    baseline_score: float
    tilt_score: float
    draw_baseline: Tuple[float, float, float, float]  # (x0, y0, x1, y1) for overlay


@dataclass
class TextQualityResult:
    rows: List[RowQuality]
    word_spacing_score: float
    overall_height_score: float
    overall_width_score: float
    overall_baseline_score: float
    overall_tilt_deg: float
    issues: List[str]


class TextQualityAnalyzer:

    def analyze(
        self,
        chars: List[Dict],
        words: List[List[Dict]] = None,
    ) -> TextQualityResult:
        if not chars:
            return TextQualityResult(
                rows=[], word_spacing_score=100.0,
                overall_height_score=100.0, overall_width_score=100.0,
                overall_baseline_score=100.0, overall_tilt_deg=0.0,
                issues=[],
            )

        rows = self._group_by_row(chars)
        row_qualities = [self._analyze_row(i, row) for i, row in enumerate(rows)]

        n = sum(len(rq.char_ids) for rq in row_qualities) or 1
        overall_h  = sum(rq.height_score    * len(rq.char_ids) for rq in row_qualities) / n
        overall_w  = sum(rq.width_score     * len(rq.char_ids) for rq in row_qualities) / n
        overall_b  = sum(rq.baseline_score  * len(rq.char_ids) for rq in row_qualities) / n
        overall_t  = sum(rq.tilt_deg        * len(rq.char_ids) for rq in row_qualities) / n

        word_score = self._word_spacing_score(words, chars) if words else 100.0

        issues = self._generate_issues(
            row_qualities, word_score, overall_h, overall_w, overall_b,
        )

        return TextQualityResult(
            rows=row_qualities,
            word_spacing_score=round(word_score, 1),
            overall_height_score=round(overall_h, 1),
            overall_width_score=round(overall_w, 1),
            overall_baseline_score=round(overall_b, 1),
            overall_tilt_deg=round(overall_t, 2),
            issues=issues,
        )

    # ------------------------------------------------------------------

    def _group_by_row(self, chars: List[Dict]) -> List[List[Dict]]:
        avg_h = np.mean([c["bounding_box"]["height"] for c in chars])
        tol   = avg_h * 0.6
        sorted_c = sorted(chars, key=lambda c: c["bounding_box"]["y"])
        rows: List[List[Dict]] = []
        for c in sorted_c:
            cy = c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2.0
            placed = False
            for row in rows:
                row_cy = np.mean([r["bounding_box"]["y"] + r["bounding_box"]["height"] / 2.0
                                  for r in row])
                if abs(cy - row_cy) < tol:
                    row.append(c); placed = True; break
            if not placed:
                rows.append([c])
        for row in rows:
            row.sort(key=lambda c: c["bounding_box"]["x"])
        return rows

    def _analyze_row(self, row_idx: int, row: List[Dict]) -> RowQuality:
        heights   = [c["bounding_box"]["height"] for c in row]
        widths    = [c["bounding_box"]["width"]  for c in row]
        bottom_ys = [c["bounding_box"]["y"] + c["bounding_box"]["height"] for c in row]
        center_ys = [c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2.0 for c in row]
        center_xs = [c["bounding_box"]["x"] + c["bounding_box"]["width"]  / 2.0 for c in row]

        h_arr = np.array(heights, dtype=float)
        w_arr = np.array(widths,  dtype=float)
        median_h = float(np.median(h_arr))

        height_cv = float(np.std(h_arr) / np.mean(h_arr)) if np.mean(h_arr) > 0 else 0.0
        width_cv  = float(np.std(w_arr) / np.mean(w_arr)) if np.mean(w_arr) > 0 else 0.0
        height_score = max(0.0, 100.0 * (1.0 - height_cv / CV_MAX))
        width_score  = max(0.0, 100.0 * (1.0 - width_cv  / CV_MAX))

        # 기준선: 바닥 y 편차 / median_height
        if len(bottom_ys) > 1:
            baseline_std_ratio = float(np.std(bottom_ys) / median_h) if median_h > 0 else 0.0
        else:
            baseline_std_ratio = 0.0
        baseline_score = max(0.0, 100.0 * (1.0 - baseline_std_ratio / BASELINE_STD_MAX))

        # 행 기울기: center_y ~ center_x 선형 회귀
        if len(center_xs) >= 2:
            A = np.column_stack([center_xs, np.ones(len(center_xs))])
            sol = np.linalg.lstsq(A, center_ys, rcond=None)
            slope, intercept = float(sol[0][0]), float(sol[0][1])
            tilt_deg = float(np.degrees(np.arctan(slope)))
            x_left  = float(min(c["bounding_box"]["x"] for c in row))
            x_right = float(max(c["bounding_box"]["x"] + c["bounding_box"]["width"] for c in row))
            y_left  = slope * x_left  + intercept
            y_right = slope * x_right + intercept
        else:
            tilt_deg = 0.0
            x_left  = float(row[0]["bounding_box"]["x"])
            x_right = float(row[0]["bounding_box"]["x"] + row[0]["bounding_box"]["width"])
            y_left  = center_ys[0]
            y_right = center_ys[0]

        tilt_score = max(0.0, 100.0 * (1.0 - abs(tilt_deg) / TILT_MAX_DEG))

        return RowQuality(
            row_idx=row_idx,
            char_ids=[c["char_id"] for c in row],
            height_cv=round(height_cv, 3),
            width_cv=round(width_cv, 3),
            baseline_std_ratio=round(baseline_std_ratio, 3),
            tilt_deg=round(tilt_deg, 2),
            height_score=round(height_score, 1),
            width_score=round(width_score, 1),
            baseline_score=round(baseline_score, 1),
            tilt_score=round(tilt_score, 1),
            draw_baseline=(x_left, y_left, x_right, y_right),
        )

    def _word_spacing_score(
        self,
        words: List[List[Dict]],
        chars: List[Dict],
    ) -> float:
        if not words or len(words) < 2:
            return 100.0

        avg_char_w = float(np.mean([c["bounding_box"]["width"] for c in chars]))
        rows = self._group_by_row(chars)
        scores: List[float] = []

        for row in rows:
            row_ids = {c["char_id"] for c in row}
            row_words = [w for w in words if any(c["char_id"] in row_ids for c in w)]
            row_words.sort(key=lambda w: min(c["bounding_box"]["x"] for c in w))

            for i in range(len(row_words) - 1):
                end_x  = max(c["bounding_box"]["x"] + c["bounding_box"]["width"]
                             for c in row_words[i])
                start_x = min(c["bounding_box"]["x"] for c in row_words[i + 1])
                gap_ratio = (start_x - end_x) / avg_char_w if avg_char_w > 0 else 1.0

                if WORD_GAP_MIN <= gap_ratio <= WORD_GAP_MAX:
                    scores.append(100.0)
                elif gap_ratio > WORD_GAP_MAX:
                    scores.append(max(0.0, 100.0 - (gap_ratio - WORD_GAP_MAX) * 25.0))
                else:
                    scores.append(max(0.0, gap_ratio / WORD_GAP_MIN * 100.0))

        return float(np.mean(scores)) if scores else 100.0

    def _generate_issues(
        self,
        rows: List[RowQuality],
        word_score: float,
        h_score: float,
        w_score: float,
        b_score: float,
    ) -> List[str]:
        issues: List[str] = []

        if h_score < 60:
            issues.append(f"Character height is inconsistent (uniformity {h_score:.0f}/100)")
        elif h_score < 80:
            issues.append(f"Try to write more uniform character heights (uniformity {h_score:.0f}/100)")

        if w_score < 60:
            issues.append(f"Character width is inconsistent (uniformity {w_score:.0f}/100)")
        elif w_score < 80:
            issues.append(f"Try to write more uniform character widths (uniformity {w_score:.0f}/100)")

        if b_score < 60:
            issues.append(f"Characters are not aligned on the baseline (baseline {b_score:.0f}/100)")
        elif b_score < 80:
            issues.append(f"Try to align characters on the baseline better (baseline {b_score:.0f}/100)")

        for rq in rows:
            if abs(rq.tilt_deg) > TILT_MAX_DEG:
                direction = "downward" if rq.tilt_deg > 0 else "upward"
                issues.append(
                    f"Row {rq.row_idx + 1} tilts {direction} toward the right "
                    f"({rq.tilt_deg:+.1f}deg)"
                )

        if word_score < 60:
            issues.append(f"Word spacing is too wide or too narrow (spacing {word_score:.0f}/100)")
        elif word_score < 80:
            issues.append(f"Try to adjust word spacing (spacing {word_score:.0f}/100)")

        return issues


# ------------------------------------------------------------------
# SFR-005I 인터페이스 함수
# ------------------------------------------------------------------

def analyze_text_quality(
    binary_image_list: List[List[int]],
    image_width: int,
    image_height: int,
    chars: List[Dict],
    words: List[List[Dict]] = None,
) -> Dict:
    """
    AI_MODEL_INTERFACE.md SFR-005I 규격 함수 (전체 글 품질 버전).

    Returns
    -------
    Dict — TextQualityResult 직렬화
    """
    result = TextQualityAnalyzer().analyze(chars, words)
    return {
        "overall_height_score":   result.overall_height_score,
        "overall_width_score":    result.overall_width_score,
        "overall_baseline_score": result.overall_baseline_score,
        "overall_tilt_deg":       result.overall_tilt_deg,
        "word_spacing_score":     result.word_spacing_score,
        "issues":                 result.issues,
        "rows": [
            {
                "row_idx":              rq.row_idx,
                "char_ids":             rq.char_ids,
                "height_score":         rq.height_score,
                "width_score":          rq.width_score,
                "baseline_score":       rq.baseline_score,
                "tilt_score":           rq.tilt_score,
                "height_cv":            rq.height_cv,
                "width_cv":             rq.width_cv,
                "baseline_std_ratio":   rq.baseline_std_ratio,
                "tilt_deg":             rq.tilt_deg,
            }
            for rq in result.rows
        ],
    }
