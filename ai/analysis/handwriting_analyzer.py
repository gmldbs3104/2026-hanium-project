"""
SFR-005I: 크기 균일성 / 기울기 / 기준선 정렬 분석

입력: craft_detect_chars() 결과 (char_id, bounding_box, angle, confidence)
출력: SizeAngleResult — per-char 분석 + 전체 통계 + 피드백 이슈 목록

AI_MODEL_INTERFACE.md 섹션 4(analyze_size_angle) 스펙 준수 + requirement.md
SFR-005I가 요구하는 행 정렬(line_alignment_score) 추가.

설계 노트
--------
각 글자의 기울기는 craft_detect_chars()가 이미 requirement.md 스펙대로
(각 문자 bbox의 잉크 픽셀에 cv2.minAreaRect를 적용해) 계산해 `angle` 필드로
제공한다. 이 모듈은 그 값을 그대로 재사용하며, 별도로 이미지를 다시 잘라
기울기를 재계산하지 않는다 — 탐지 단계 결과와 분석 단계 결과가 서로 다른
기준으로 각도를 매길 위험을 없애기 위함. 따라서 이 모듈은 binary_image 없이
chars 리스트만으로 동작한다.
"""
import numpy as np
from dataclasses import dataclass
from typing import List, Dict

# 크기 판정 임계값 (행 내 중앙값 기준 비율)
SIZE_LARGE_THRESH = 1.5   # 50% 초과 크면 large
SIZE_SMALL_THRESH = 0.65  # 35% 이상 작으면 small

# 기울기 판정 임계값 (craft_detect_chars()가 제공하는 minAreaRect 각도 기준)
ANGLE_WARN_DEG = 3.0   # 경미
ANGLE_FLAG_DEG = 7.0   # 명확

# CV(변동계수) 0% → 100점, 30%+ → 0점
SIZE_SCORE_MAX_CV = 0.30

# 기준선(baseline) 판정 — 바닥 y좌표의 std / 행 중앙 높이, 20% → 0점
BASELINE_STD_MAX = 0.20


@dataclass
class CharAnalysis:
    char_id: str
    size_ratio: float    # char_height / 행_median_height  (1.0 = 정상)
    angle: float          # craft_detect_chars()가 제공한 minAreaRect 각도 그대로 사용
    size_flag: str        # "normal" | "large" | "small"
    angle_flag: str       # "normal" | "tilted_cw" | "tilted_ccw"


@dataclass
class SizeAngleResult:
    chars: List[CharAnalysis]
    size_uniformity_score: float    # 0 ~ 100
    mean_angle: float               # degrees
    angle_std: float                # degrees
    overall_tilt: str               # "straight" | "leaning_right" | "leaning_left"
    line_alignment_score: float     # 0 ~ 100 (행 내 기준선 정렬도)
    issues: List[str]               # SFR-007 피드백 재료


class SizeAngleAnalyzer:

    def analyze(self, chars: List[Dict]) -> SizeAngleResult:
        if not chars:
            return SizeAngleResult(
                chars=[], size_uniformity_score=100.0,
                mean_angle=0.0, angle_std=0.0, overall_tilt="straight",
                line_alignment_score=100.0, issues=[],
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
                if angle > ANGLE_FLAG_DEG:
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

        all_angles = np.array([c.get("angle", 0.0) for c in chars], dtype=np.float32)
        mean_angle = float(np.mean(all_angles))
        angle_std  = float(np.std(all_angles))

        if mean_angle > ANGLE_WARN_DEG:
            overall_tilt = "leaning_right"
        elif mean_angle < -ANGLE_WARN_DEG:
            overall_tilt = "leaning_left"
        else:
            overall_tilt = "straight"

        line_alignment_score = float(np.mean(row_baseline_scores)) if row_baseline_scores else 100.0

        issues = self._generate_issues(
            char_analyses, size_uniformity_score, mean_angle, angle_std, line_alignment_score,
        )

        return SizeAngleResult(
            chars=char_analyses,
            size_uniformity_score=round(size_uniformity_score, 1),
            mean_angle=round(mean_angle, 2),
            angle_std=round(angle_std, 2),
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

        # 전체 기울기
        if abs(mean_angle) > ANGLE_FLAG_DEG:
            direction = "오른쪽" if mean_angle > 0 else "왼쪽"
            issues.append(f"글자 전체가 {direction}으로 {abs(mean_angle):.1f}° 기울어져 있습니다")
        elif abs(mean_angle) > ANGLE_WARN_DEG:
            direction = "오른쪽" if mean_angle > 0 else "왼쪽"
            issues.append(f"글자가 {direction}으로 약간({abs(mean_angle):.1f}°) 기울어져 있습니다")

        if angle_std > 8.0:
            issues.append(f"글자마다 기울기 방향이 다릅니다 (편차 {angle_std:.1f}°)")

        tilted_cw  = [c.char_id for c in chars if c.angle_flag == "tilted_cw"]
        tilted_ccw = [c.char_id for c in chars if c.angle_flag == "tilted_ccw"]
        if tilted_cw:
            issues.append(f"오른쪽으로 기운 글자: {', '.join(tilted_cw)}")
        if tilted_ccw:
            issues.append(f"왼쪽으로 기운 글자: {', '.join(tilted_ccw)}")

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
        "size_uniformity_score": result.size_uniformity_score,
        "mean_angle":            result.mean_angle,
        "angle_std":             result.angle_std,
        "overall_tilt":          result.overall_tilt,
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
