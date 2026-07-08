import base64
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .quality_scorer import QualityScorer

# SFR-003I 표준 출력 해상도 — 긴 변 기준 최대값 (비율 유지)
OUTPUT_MAX_SIDE = 1280
# 긴 변이 이 값보다 작으면 업스케일 (CRAFT가 작은 글자를 탐지 못하는 것 방지)
OUTPUT_MIN_SIDE = 800

# Hough 기울기 보정 허용 범위
MAX_SKEW_ANGLE = 45.0

# 파일 크기 상한 10MB (REQ-003I-2)
MAX_FILE_BYTES = 10 * 1024 * 1024

# 품질 점수 40점 미만이면 재촬영 요청
RETAKE_POOR_QUALITY = "더 밝은 곳에서 선명하게 다시 찍어주세요."


@dataclass
class PreprocessResult:
    """전처리 결과 객체"""
    binary_image: np.ndarray
    quality_score: dict
    skew_angle: float
    applied_filters: list[str] = field(default_factory=list)
    original_size: tuple[int, int] = (0, 0)
    output_size: tuple[int, int] = (0, 0)
    retake_required: bool = False
    retake_reason: str = ""

    def is_acceptable(self) -> bool:
        return not self.retake_required


class ImagePreprocessor:
    """
    SFR-003I: 카메라 이미지 입력 및 OpenCV 전처리

    파이프라인:
        1. Grayscale 변환
        2. Gaussian Blur
        3. 품질 점수 산출 — 40점 미만이면 retake_required
        4. Adaptive Thresholding
        5. Hough Deskew (기울기 보정, ±6° 이내)
        6. 해상도 리사이즈 (비율 유지, 긴 변 최대 1280px)
    """

    def __init__(self):
        self._scorer = QualityScorer()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def preprocess_from_base64(self, b64_string: str) -> PreprocessResult:
        raw_bytes = base64.b64decode(b64_string)
        return self.preprocess_from_bytes(raw_bytes)

    def preprocess_from_bytes(self, raw_bytes: bytes) -> PreprocessResult:
        if len(raw_bytes) > MAX_FILE_BYTES:
            raise ValueError(f"이미지 파일이 10MB를 초과합니다 ({len(raw_bytes) / 1e6:.1f}MB)")
        bgr = self._decode_bytes(raw_bytes)
        return self._run_pipeline(bgr)

    def preprocess_from_file(self, file_path: str) -> PreprocessResult:
        """cv2.imread()는 Windows 한글 경로 미지원 → 바이트로 직접 로드"""
        with open(file_path, "rb") as f:
            raw = f.read()
        return self.preprocess_from_bytes(raw)

    # ------------------------------------------------------------------
    # 파이프라인 실행
    # ------------------------------------------------------------------

    def _run_pipeline(self, bgr: np.ndarray) -> PreprocessResult:
        applied = []
        h, w = bgr.shape[:2]

        # Step 1: Grayscale
        gray = self._to_grayscale(bgr)
        applied.append("grayscale")

        # Step 2: Gaussian Blur
        blurred = self._gaussian_blur(gray)
        applied.append("gaussian_blur")

        # Step 3: 품질 점수
        quality = self._scorer.score(blurred)
        retake_required = not self._scorer.is_acceptable(quality)
        retake_reason = RETAKE_POOR_QUALITY if retake_required else ""

        # Step 4: Adaptive Threshold
        binary = self._adaptive_threshold(blurred)
        applied.append("adaptive_threshold")

        # Step 5: Hough Deskew
        binary, skew_angle = self._deskew(binary)
        if abs(skew_angle) > 0.5:
            applied.append(f"deskew({skew_angle:+.1f}deg)")

        # Step 6: 최대 해상도 리사이즈 (비율 유지, 긴 변 ≤ OUTPUT_MAX_SIDE)
        resized = self._resize(binary)
        rh, rw = resized.shape[:2]
        applied.append(f"resize({rw}x{rh})")

        return PreprocessResult(
            binary_image=resized,
            quality_score=quality,
            skew_angle=skew_angle,
            applied_filters=applied,
            original_size=(w, h),
            output_size=(rw, rh),
            retake_required=retake_required,
            retake_reason=retake_reason,
        )

    # ------------------------------------------------------------------
    # 각 단계 구현
    # ------------------------------------------------------------------

    def _decode_bytes(self, raw_bytes: bytes) -> np.ndarray:
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("이미지 디코딩 실패: 지원하지 않는 형식이거나 손상된 파일입니다")
        return bgr

    def _to_grayscale(self, bgr: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    def _gaussian_blur(self, gray: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def _adaptive_threshold(self, gray: np.ndarray) -> np.ndarray:
        return cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15, C=5,
        )

    def _deskew(self, binary: np.ndarray) -> tuple[np.ndarray, float]:
        skew_angle = self._detect_skew_angle(binary)
        if abs(skew_angle) < 0.5:
            return binary, 0.0
        if abs(skew_angle) > MAX_SKEW_ANGLE:
            return binary, skew_angle
        corrected = self._rotate_image(binary, -skew_angle)
        return corrected, skew_angle

    def _detect_skew_angle(self, binary: np.ndarray) -> float:
        h, w = binary.shape[:2]
        edges = cv2.Canny(binary, 50, 150, apertureSize=3)
        min_len = max(100, int(w * 0.15))
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 80,
                                minLineLength=min_len, maxLineGap=10)
        if lines is None:
            return 0.0
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line.flatten()[:4]
            if x2 - x1 == 0:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if -6.0 < angle < 6.0:
                angles.append(angle)
        if len(angles) < 5:
            return 0.0
        return float(np.median(angles))

    def _rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        h, w = image.shape[:2]
        center = (w / 2.0, h / 2.0)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        cos = abs(matrix[0, 0])
        sin = abs(matrix[0, 1])
        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)
        matrix[0, 2] += (new_w / 2.0) - center[0]
        matrix[1, 2] += (new_h / 2.0) - center[1]
        return cv2.warpAffine(image, matrix, (new_w, new_h), borderValue=0)

    def _resize(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        long_side = max(h, w)
        if long_side < OUTPUT_MIN_SIDE:
            scale = OUTPUT_MIN_SIDE / long_side
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
        if long_side > OUTPUT_MAX_SIDE:
            scale = OUTPUT_MAX_SIDE / long_side
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return image
