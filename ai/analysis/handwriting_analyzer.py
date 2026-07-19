"""
SFR-005I: 크기 균일성 / 기울기 / 기준선 정렬 분석

입력: craft_detect_chars() 결과 (char_id, bounding_box, angle, confidence)
출력: SizeAngleResult — per-char 분석 + 전체 통계 + 피드백 이슈 목록

AI_MODEL_INTERFACE.md 섹션 4(analyze_size_angle) 스펙 준수 + requirement.md
SFR-005I가 요구하는 행 정렬(line_alignment_score) 추가.

설계 노트
--------
각 글자의 기울기는 craft_detect_chars()가 세로획 slant 방식으로 계산해
`angle`(+`angle_reliable`) 필드로 제공한다 (과거 minAreaRect 방식은 둥근/대각
글자에서 곧은 글씨도 ±30~45°로 튀어 2026-07-19 교체 — craft_detector.py
docstring 참고). 이 모듈은 그 값을 그대로 재사용하며, 별도로 이미지를 다시
잘라 기울기를 재계산하지 않는다. 따라서 binary_image 없이 chars 리스트만으로
동작한다.

기울기 평가는 문서 단위다: 필자의 slant는 글 전체에서 대체로 일정하므로,
angle_reliable=True인 글자들만 모아 (1) 전체 평균 기울기(방향·정도),
(2) 일관성 점수(tilt_consistency_score, 표준편차 기반)를 산출하고 개별 글자
지적 문구는 내지 않는다. 신뢰 글자가 TILT_MIN_RELIABLE 미만이면 평가 생략.
"""
import numpy as np
from dataclasses import dataclass
from typing import List, Dict

# 크기 판정 임계값 (행 내 중앙값 기준 비율)
SIZE_LARGE_THRESH = 1.5   # 50% 초과 크면 large
SIZE_SMALL_THRESH = 0.65  # 35% 이상 작으면 small

# 기울기 판정 임계값 (craft_detect_chars()가 제공하는 세로획 slant 기준)
ANGLE_WARN_DEG = 3.0   # 경미
ANGLE_FLAG_DEG = 7.0   # 명확

# 문서 단위 기울기 평가 (2026-07-19 개편 — 개별 글자 지적 대신 전체 평가)
TILT_MIN_RELIABLE = 3        # slant 신뢰 글자가 이보다 적으면 기울기 평가 생략
TILT_STD_MAX = 12.0          # slant 표준편차 0° → 100점, 12°+ → 0점 (일관성 점수)
# 이상치 조정: 필자의 slant는 습관적으로 일정하므로, 전체 중앙값에서 이 이상
# 벗어난 측정값은 (흘림·측정 노이즈로 보고) 통계에서 제외한다.
TILT_OUTLIER_DEG = 10.0
# 기울기 일관성 등급 경계 (handwriting_evaluation.md 지표 2: σ<3 우수 / 3~7 보통 / ≥7 불량)
TILT_STD_GOOD = 3.0
TILT_STD_FAIR = 7.0

# CV(변동계수) 0% → 100점, 30%+ → 0점
SIZE_SCORE_MAX_CV = 0.30

# 기준선(baseline) 판정 — 바닥 y좌표의 std / 행 중앙 높이, 20% → 0점
BASELINE_STD_MAX = 0.20


@dataclass
class CharAnalysis:
    char_id: str
    size_ratio: float    # char_height / 행_median_height  (1.0 = 정상)
    angle: float          # craft_detect_chars()가 제공한 세로획 slant (unmeasured면 0.0)
    size_flag: str        # "normal" | "large" | "small"
    angle_flag: str       # "normal" | "tilted_cw" | "tilted_ccw" | "unmeasured"


@dataclass
class SizeAngleResult:
    chars: List[CharAnalysis]
    size_uniformity_score: float    # 0 ~ 100
    mean_angle: float               # degrees (slant 신뢰 글자들의 평균)
    angle_std: float                # degrees (slant 신뢰 글자들의 표준편차)
    tilt_consistency_score: float   # 0 ~ 100 (기울기 일관성 — 문서 단위 평가)
    overall_tilt: str               # "straight" | "leaning_right" | "leaning_left"
    line_alignment_score: float     # 0 ~ 100 (행 내 기준선 정렬도)
    issues: List[str]               # SFR-007 피드백 재료


class SizeAngleAnalyzer:

    def analyze(self, chars: List[Dict]) -> SizeAngleResult:
        if not chars:
            return SizeAngleResult(
                chars=[], size_uniformity_score=100.0,
                mean_angle=0.0, angle_std=0.0, tilt_consistency_score=100.0,
                overall_tilt="straight", line_alignment_score=100.0, issues=[],
            )

        rows = self._group_by_row(chars)

        char_analyses: List[CharAnalysis] = []
        row_baseline_scores: List[float] = []

        for row in rows:
            heights = [c["bounding_box"]["height"] for c in row]
            row_median_h = float(np.median(heights))

            for c in row:
                bb = c["bounding_box"]
                size_ratio = (bb["height"] / row_median_h) if row_median_h > 0 else 1.0
                if size_ratio > SIZE_LARGE_THRESH:
                    size_flag = "large"
                elif size_ratio < SIZE_SMALL_THRESH:
                    size_flag = "small"
                else:
                    size_flag = "normal"

                angle = float(c.get("angle", 0.0))
                if not c.get("angle_reliable", True):
                    angle_flag = "unmeasured"   # 세로획 없음 — 기울기 평가에서 제외
                elif angle > ANGLE_FLAG_DEG:
                    angle_flag = "tilted_cw"
                elif angle < -ANGLE_FLAG_DEG:
                    angle_flag = "tilted_ccw"
                else:
                    angle_flag = "normal"

                char_analyses.append(CharAnalysis(
                    char_id=c["char_id"],
                    size_ratio=round(size_ratio, 3),
                    angle=round(angle, 2),
                    size_flag=size_flag,
                    angle_flag=angle_flag,
                ))

            # 기준선 정렬: 행 내 글자들의 바닥(y + height) 좌표 편차
            if len(row) > 1 and row_median_h > 0:
                bottoms = [c["bounding_box"]["y"] + c["bounding_box"]["height"] for c in row]
                baseline_std_ratio = float(np.std(bottoms) / row_median_h)
                row_score = max(0.0, 100.0 * (1.0 - baseline_std_ratio / BASELINE_STD_MAX))
                row_baseline_scores.append(row_score)

        all_heights = np.array([c["bounding_box"]["height"] for c in chars], dtype=np.float32)
        size_cv = float(np.std(all_heights) / np.mean(all_heights)) if np.mean(all_heights) > 0 else 0.0
        size_uniformity_score = float(max(0.0, 100.0 * (1.0 - size_cv / SIZE_SCORE_MAX_CV)))

        # ── 문서 단위 기울기 평가 (slant 신뢰 글자만 집계) ──────────────
        # 사람 손글씨는 필자 고유의 slant가 전체적으로 일정하므로, 개별 글자
        # 지적 대신 (1) 전체 평균 기울기 방향·정도, (2) 일관성 점수를 낸다.
        reliable = np.array([c.get("angle", 0.0) for c in chars
                             if c.get("angle_reliable", True)], dtype=np.float32)
        n_reliable = len(reliable)
        n_outlier = 0
        if n_reliable >= TILT_MIN_RELIABLE:
            # 이상치 조정: 개별 측정값(A)을 전체 중앙값(C)과 비교해, 습관적
            # slant에서 동떨어진 값은 흘림/측정 노이즈로 보고 통계에서 제외.
            med = float(np.median(reliable))
            inliers = reliable[np.abs(reliable - med) <= TILT_OUTLIER_DEG]
            n_outlier = n_reliable - len(inliers)
            mean_angle = float(np.mean(inliers))
            angle_std  = float(np.std(inliers))
            tilt_consistency_score = float(
                max(0.0, 100.0 * (1.0 - angle_std / TILT_STD_MAX)))
        else:
            # 세로획이 있는 글자가 너무 적으면 기울기 평가 자체를 생략
            mean_angle, angle_std = 0.0, 0.0
            tilt_consistency_score = 100.0

        if mean_angle > ANGLE_WARN_DEG:
            overall_tilt = "leaning_right"
        elif mean_angle < -ANGLE_WARN_DEG:
            overall_tilt = "leaning_left"
        else:
            overall_tilt = "straight"

        line_alignment_score = float(np.mean(row_baseline_scores)) if row_baseline_scores else 100.0

        issues = self._generate_issues(
            char_analyses, size_uniformity_score, mean_angle, angle_std,
            tilt_consistency_score, n_reliable, n_outlier, line_alignment_score,
        )

        return SizeAngleResult(
            chars=char_analyses,
            size_uniformity_score=round(size_uniformity_score, 1),
            mean_angle=round(mean_angle, 2),
            angle_std=round(angle_std, 2),
            tilt_consistency_score=round(tilt_consistency_score, 1),
            overall_tilt=overall_tilt,
            line_alignment_score=round(line_alignment_score, 1),
            issues=issues,
        )

    # ------------------------------------------------------------------

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

    def _generate_issues(
        self,
        chars: List[CharAnalysis],
        size_score: float,
        mean_angle: float,
        angle_std: float,
        tilt_consistency_score: float,
        n_reliable: int,
        n_outlier: int,
        line_alignment_score: float,
    ) -> List[str]:
        issues: List[str] = []

        # 크기 균일성
        if size_score < 60:
            issues.append(f"글자 크기가 고르지 않습니다 (균일성 {size_score:.0f}/100)")
        elif size_score < 80:
            issues.append(f"글자 크기를 조금 더 균일하게 써보세요 (균일성 {size_score:.0f}/100)")

        large_ids = [c.char_id for c in chars if c.size_flag == "large"]
        small_ids = [c.char_id for c in chars if c.size_flag == "small"]
        if large_ids:
            issues.append(f"크게 쓴 글자: {', '.join(large_ids)}")
        if small_ids:
            issues.append(f"작게 쓴 글자: {', '.join(small_ids)}")

        # 전체 기울기 — 문서 단위 평가만 제공 (개별 글자 나열은 slant 측정
        # 노이즈에 민감하고, 서비스 목적도 "글 전체 평가"이므로 제거함)
        if n_reliable >= TILT_MIN_RELIABLE:
            if abs(mean_angle) > ANGLE_FLAG_DEG:
                direction = "오른쪽" if mean_angle > 0 else "왼쪽"
                issues.append(
                    f"글씨 전체가 {direction}으로 {abs(mean_angle):.1f}° 기울어져 있습니다")
            elif abs(mean_angle) > ANGLE_WARN_DEG:
                direction = "오른쪽" if mean_angle > 0 else "왼쪽"
                issues.append(
                    f"글씨가 전체적으로 {direction}으로 약간({abs(mean_angle):.1f}°) 기울어져 있습니다")

            # 일관성 등급은 handwriting_evaluation.md 지표 2의 σ 경계를 따른다
            if angle_std >= TILT_STD_FAIR:
                issues.append(
                    f"글자들의 기울기가 들쭉날쭉합니다 (편차 {angle_std:.1f}°, 7° 이상은 불량)")
            elif angle_std >= TILT_STD_GOOD:
                issues.append(
                    f"기울기를 조금 더 일정하게 써보세요 (편차 {angle_std:.1f}°)")

            if n_outlier > 0:
                issues.append(
                    f"기울기가 유난히 다른 {n_outlier}자는 흘려 쓴 것으로 보고 통계에서 제외했습니다")

        # 기준선 정렬
        if line_alignment_score < 60:
            issues.append(f"글자들이 기준선에 잘 맞춰져 있지 않습니다 (정렬 {line_alignment_score:.0f}/100)")
        elif line_alignment_score < 80:
            issues.append(f"기준선을 조금 더 맞춰 써보세요 (정렬 {line_alignment_score:.0f}/100)")

        return issues


# ------------------------------------------------------------------
# SFR-005I 인터페이스 함수 (AI_MODEL_INTERFACE.md 섹션 4 + line_alignment_score 추가)
# ------------------------------------------------------------------

def analyze_size_angle(chars: List[Dict]) -> Dict:
    """
    AI_MODEL_INTERFACE.md SFR-005I 규격 함수.

    Parameters
    ----------
    chars : craft_detect_chars() 반환값 그대로
            [{char_id, bounding_box:{x,y,width,height}, angle, confidence}, ...]

    Returns
    -------
    Dict — SizeAngleResult를 dict로 직렬화
    """
    result = SizeAngleAnalyzer().analyze(chars)
    return {
        "size_uniformity_score":  result.size_uniformity_score,
        "mean_angle":             result.mean_angle,
        "angle_std":              result.angle_std,
        "tilt_consistency_score": result.tilt_consistency_score,
        "overall_tilt":           result.overall_tilt,
        "line_alignment_score":  result.line_alignment_score,
        "issues":                result.issues,
        "chars": [
            {
                "char_id":    c.char_id,
                "size_ratio": c.size_ratio,
                "angle":      c.angle,
                "size_flag":  c.size_flag,
                "angle_flag": c.angle_flag,
            }
            for c in result.chars
        ],
    }
