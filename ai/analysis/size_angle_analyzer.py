"""
SFR-005I: 크기 균일성 / 기울기 분석

입력: binary_image (H×W uint8) + craft_detect_chars() 결과
출력: SizeAngleResult — per-char 분석 + 전체 통계 + 피드백 이슈 목록
"""
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict

# 크기 판정 임계값 (행 내 중앙값 기준 비율)
SIZE_LARGE_THRESH = 1.5   # 50% 초과 크면 large
SIZE_SMALL_THRESH = 0.65  # 35% 이상 작으면 small

# 기울기 판정 임계값
ANGLE_WARN_DEG = 3.0   # 경미
ANGLE_FLAG_DEG = 7.0   # 명확

# CV(변동계수) 0% → 100점, 30%+ → 0점
SIZE_SCORE_MAX_CV = 0.30


@dataclass
class CharAnalysis:
    char_id: str
    size_ratio: float    # char_height / 행_median_height  (1.0 = 정상)
    angle: float         # degrees (양수=시계방향, 음수=반시계방향)
    size_flag: str       # "normal" | "large" | "small"
    angle_flag: str      # "normal" | "tilted_cw" | "tilted_ccw"


@dataclass
class SizeAngleResult:
    chars: List[CharAnalysis]
    size_uniformity_score: float   # 0 ~ 100
    mean_angle: float              # degrees
    angle_std: float               # degrees
    overall_tilt: str              # "straight" | "leaning_right" | "leaning_left"
    issues: List[str]              # SFR-007 피드백 재료


class SizeAngleAnalyzer:

    def analyze(
        self,
        binary_image: np.ndarray,
        chars: List[Dict],
    ) -> SizeAngleResult:
        if not chars:
            return SizeAngleResult(
                chars=[], size_uniformity_score=100.0,
                mean_angle=0.0, angle_std=0.0,
                overall_tilt="straight", issues=[],
            )

        rows = self._group_by_row(chars)

        char_analyses: List[CharAnalysis] = []
        all_angles: List[float] = []

        for row in rows:
            row_median_h = float(np.median([c["bounding_box"]["height"] for c in row]))

            for c in row:
                bb = c["bounding_box"]
                x, y = int(bb["x"]), int(bb["y"])
                w, h = int(bb["width"]), int(bb["height"])

                size_ratio = (h / row_median_h) if row_median_h > 0 else 1.0
                if size_ratio > SIZE_LARGE_THRESH:
                    size_flag = "large"
                elif size_ratio < SIZE_SMALL_THRESH:
                    size_flag = "small"
                else:
                    size_flag = "normal"

                img_h, img_w = binary_image.shape[:2]
                x1 = min(x + w, img_w)
                y1 = min(y + h, img_h)
                crop = binary_image[max(0, y):y1, max(0, x):x1]
                angle = self._spine_angle(crop)
                all_angles.append(angle)

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

        all_heights = [c["bounding_box"]["height"] for c in chars]
        h_arr = np.array(all_heights, dtype=np.float32)
        size_cv = float(np.std(h_arr) / np.mean(h_arr)) if np.mean(h_arr) > 0 else 0.0
        size_uniformity_score = float(max(0.0, 100.0 * (1.0 - size_cv / SIZE_SCORE_MAX_CV)))

        a_arr = np.array(all_angles, dtype=np.float32)
        mean_angle = float(np.mean(a_arr))
        angle_std  = float(np.std(a_arr))

        if mean_angle > ANGLE_WARN_DEG:
            overall_tilt = "leaning_right"
        elif mean_angle < -ANGLE_WARN_DEG:
            overall_tilt = "leaning_left"
        else:
            overall_tilt = "straight"

        issues = self._generate_issues(
            char_analyses, size_uniformity_score, mean_angle, angle_std,
        )

        return SizeAngleResult(
            chars=char_analyses,
            size_uniformity_score=round(size_uniformity_score, 1),
            mean_angle=round(mean_angle, 2),
            angle_std=round(angle_std, 2),
            overall_tilt=overall_tilt,
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

    def _spine_angle(self, crop: np.ndarray) -> float:
        """
        글자 크롭 내 각 행의 잉크 수평 중심을 선형 회귀해 기울기 추정.

        slope = dx/dy → 아래로 갈수록 중심이 오른쪽 이동 = 시계방향 기울기(양수)
        """
        if crop.size == 0:
            return 0.0
        h, w = crop.shape[:2]
        if h < 8 or w < 4:
            return 0.0

        centers_x: List[float] = []
        centers_y: List[float] = []
        for row_idx in range(h):
            ink_xs = np.where(crop[row_idx] > 0)[0]
            if len(ink_xs) >= 2:
                centers_x.append(float(ink_xs.mean()))
                centers_y.append(float(row_idx))

        if len(centers_x) < max(4, int(h * 0.25)):
            return 0.0

        xs = np.array(centers_x)
        ys = np.array(centers_y)

        # x = slope * y + intercept 피팅
        A = np.column_stack([ys, np.ones_like(ys)])
        result = np.linalg.lstsq(A, xs, rcond=None)
        slope = float(result[0][0])

        return float(np.degrees(np.arctan(slope)))

    def _generate_issues(
        self,
        chars: List[CharAnalysis],
        size_score: float,
        mean_angle: float,
        angle_std: float,
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
            issues.append(
                f"글자 전체가 {direction}으로 {abs(mean_angle):.1f}° 기울어져 있습니다"
            )
        elif abs(mean_angle) > ANGLE_WARN_DEG:
            direction = "오른쪽" if mean_angle > 0 else "왼쪽"
            issues.append(
                f"글자가 {direction}으로 약간({abs(mean_angle):.1f}°) 기울어져 있습니다"
            )

        # 기울기 일관성
        if angle_std > 8.0:
            issues.append(f"글자마다 기울기 방향이 다릅니다 (편차 {angle_std:.1f}°)")

        tilted_cw  = [c.char_id for c in chars if c.angle_flag == "tilted_cw"]
        tilted_ccw = [c.char_id for c in chars if c.angle_flag == "tilted_ccw"]
        if tilted_cw:
            issues.append(f"오른쪽으로 기운 글자: {', '.join(tilted_cw)}")
        if tilted_ccw:
            issues.append(f"왼쪽으로 기운 글자: {', '.join(tilted_ccw)}")

        return issues


# ------------------------------------------------------------------
# SFR-005I 인터페이스 함수
# ------------------------------------------------------------------

def analyze_size_angle(
    binary_image_list: List[List[int]],
    image_width: int,
    image_height: int,
    chars: List[Dict],
) -> Dict:
    """
    AI_MODEL_INTERFACE.md SFR-005I 규격 함수.

    Parameters
    ----------
    binary_image_list : 2D list (rows × cols), values 0 or 255
    image_width       : 이미지 너비 (px)
    image_height      : 이미지 높이 (px)
    chars             : craft_detect_chars() 반환값

    Returns
    -------
    Dict — SizeAngleResult를 dict로 직렬화
    """
    import cv2
    image = np.array(binary_image_list, dtype=np.uint8)
    if image.shape != (image_height, image_width):
        image = cv2.resize(
            image, (image_width, image_height), interpolation=cv2.INTER_NEAREST
        )

    result = SizeAngleAnalyzer().analyze(image, chars)
    return {
        "size_uniformity_score": result.size_uniformity_score,
        "mean_angle":            result.mean_angle,
        "angle_std":             result.angle_std,
        "overall_tilt":          result.overall_tilt,
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
