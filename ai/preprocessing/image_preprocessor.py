import base64
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .quality_scorer import QualityScorer

# 장축이 이 값보다 작은 아주 작은 입력만 업스케일 (작은 글자 탐지·GT 라벨 가독성 확보).
# 다운스케일 상한은 두지 않는다 — 손글씨 충실도를 위해 원본 해상도를 유지한다
# (A 방향, 2026-07 A/B/C 실측: close 버그 수정 후 풀해상도 탐지가 축소본과 동률).
OUTPUT_MIN_SIDE = 800

# Hough 기울기 보정 허용 범위 (실제 검출창은 _detect_skew_angle 내부의 ±6°)
MAX_SKEW_ANGLE = 45.0

# 파일 크기 상한 10MB (REQ-003I-2)
MAX_FILE_BYTES = 10 * 1024 * 1024

# 극단 종횡비 재촬영 임계 — 장축/단축이 이 값을 넘으면 리사이즈가 단축을 뭉개 글자가
# 붕괴한다(전처리로 복구 불가). 3.0은 초광각 표본(test9 4.99, test10 4.04)만 걸러내고
# 정상 표본(test3_crop 2.23, test_line2 1.96)은 통과시킨다.
EXTREME_ASPECT_RATIO = 3.0

# 재구성된 잉크 강도(밝을수록 진한 획)를 하드 이진으로 자르는 임계
INK_BINARIZE_THRESH = 40

# 측지 팽창 재구성 최대 반복 (보통 조기 수렴)
RECON_MAX_ITERS = 150

# 품질 점수 40점 미만이면 재촬영 요청 (REQ-003I-4)
RETAKE_POOR_QUALITY = "더 밝은 곳에서 선명하게 다시 찍어주세요."
# 극단 종횡비면 재촬영 요청
RETAKE_EXTREME_ASPECT = "종이 전체가 정면·수평에 담기도록 다시 찍어주세요."

_K3 = np.ones((3, 3), np.uint8)
_K2 = np.ones((2, 2), np.uint8)


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
        1. 디코드(BGR) — 한글 경로 안전(imdecode)
        2. 품질 점수 산출 — 40점 미만이면 retake (표준 그레이+블러 기준, 캘리브레이션 유지)
        3. 극단 종횡비 검사 → 초과 시 retake
        4. 채널 max 그레이 → 측지 재구성 이진화 (비침·괘선 원천 제거)
        5. Hough deskew (긴 수평 직선 기준, 기존 방식 유지)
        6. 리사이즈 (원본 해상도 유지, 아주 작은 입력만 OUTPUT_MIN_SIDE로 업스케일)
        7. 하드 이진화 + 소형 노이즈 제거 → binary_image(stroke=255)
    """

    def __init__(self):
        self._scorer = QualityScorer()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def preprocess_from_base64(self, b64_string: str, apply_resize: bool = True) -> PreprocessResult:
        raw_bytes = base64.b64decode(b64_string)
        return self.preprocess_from_bytes(raw_bytes, apply_resize=apply_resize)

    def preprocess_from_bytes(self, raw_bytes: bytes, apply_resize: bool = True) -> PreprocessResult:
        if len(raw_bytes) > MAX_FILE_BYTES:
            raise ValueError(f"이미지 파일이 10MB를 초과합니다 ({len(raw_bytes) / 1e6:.1f}MB)")
        bgr = self._decode_bytes(raw_bytes)
        return self._run_pipeline(bgr, apply_resize=apply_resize)

    def preprocess_from_file(self, file_path: str, apply_resize: bool = True) -> PreprocessResult:
        """cv2.imread()는 Windows 한글 경로 미지원 → 바이트로 직접 로드"""
        with open(file_path, "rb") as f:
            raw = f.read()
        return self.preprocess_from_bytes(raw, apply_resize=apply_resize)

    # ------------------------------------------------------------------
    # 파이프라인 실행
    # ------------------------------------------------------------------

    def _run_pipeline(self, bgr: np.ndarray, apply_resize: bool = True) -> PreprocessResult:
        applied: list[str] = []
        h, w = bgr.shape[:2]

        # Step 2: 품질 점수 (표준 그레이+블러 — 기존 재촬영 캘리브레이션 유지)
        quality = self._scorer.score(self._gaussian_blur(self._to_grayscale(bgr)))
        reasons: list[str] = []
        if not self._scorer.is_acceptable(quality):
            reasons.append(RETAKE_POOR_QUALITY)

        # Step 3: 극단 종횡비 검사
        aspect = max(h, w) / max(min(h, w), 1)
        if aspect > EXTREME_ASPECT_RATIO:
            reasons.append(RETAKE_EXTREME_ASPECT)

        # Step 4: 채널 max 그레이 → 측지 재구성 (밝은 잉크/검은 배경)
        gray_cmax = bgr.max(axis=2).astype(np.uint8)
        applied.append("channel_max_gray")
        ink, recon_method = self._reconstruct_ink(gray_cmax)
        applied.append(recon_method)

        # Step 5: 하드 이진화 — 획이 선명한 풀 해상도에서 자른다.
        # 그레이 잉크를 리사이즈한 뒤 자르면 INTER_AREA 희석으로 가는 획이 임계 밑으로
        # 사라진다(실측: 리사이즈 후 자르면 60,694px → 1,188px로 붕괴). 먼저 이진화한다.
        binary = (ink >= INK_BINARIZE_THRESH).astype(np.uint8) * 255

        # Step 6: Hough deskew (기존 방식 유지)
        skew_angle = self._detect_skew_angle(binary)
        if abs(skew_angle) < 0.5:
            skew_angle = 0.0
        elif abs(skew_angle) <= MAX_SKEW_ANGLE:
            binary = self._rotate_image(binary, -skew_angle)
            applied.append(f"deskew({skew_angle:+.1f}deg)")
        # |skew|>45°는 안전상 회전하지 않고 각도만 보고 (기존 동작 유지)

        # Step 7: 리사이즈(업스케일만, 원본 해상도 유지) + 소형 노이즈 제거
        if apply_resize:
            binary = self._resize(binary)
            applied.append(f"resize({binary.shape[1]}x{binary.shape[0]})")
        binary = self._remove_small_blobs(binary)

        oh, ow = binary.shape[:2]
        return PreprocessResult(
            binary_image=binary,
            quality_score=quality,
            skew_angle=skew_angle,
            applied_filters=applied,
            original_size=(w, h),
            output_size=(ow, oh),
            retake_required=bool(reasons),
            retake_reason=" ".join(reasons),
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

    def _reconstruct_ink(self, gray: np.ndarray) -> tuple[np.ndarray, str]:
        """채널 max 그레이 → 측지 팽창 재구성으로 앞면 잉크만 남긴다.

        adaptiveThreshold는 국소 대비만 봐서 뒷장 비침·잔여 괘선을 진짜 획과 같은
        검정으로 승격시킨다. 여기서는 (1) 조명 정규화로 배경을 고르게 만들고, (2) 확실한
        진한 획만 seed로 삼아 mask 안에서 팽창-재구성한다 — seed와 공간적으로 떨어진
        비침은 seed가 닿지 못해 재구성되지 않으므로 원천 제거된다.

        반환: (ink, method). ink는 밝을수록 진한 획(stroke bright, bg=0), uint8.
              method는 "geodesic_reconstruction" 또는 폴백 "linear_stretch".
        """
        H, W = gray.shape[:2]
        # 사실상 잉크가 없는(빈 종이) 방어
        if not np.any(gray < 250):
            return np.zeros((H, W), np.uint8), "geodesic_reconstruction"

        # (b) 조명 정규화 (division)
        sigma = max(H, W) / 55.0
        bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
        norm = cv2.divide(gray, bg, scale=255)
        ink = (255 - norm).astype(np.uint8)

        # (c) 잉크 후보량 기반 적응형 seed/mask 임계
        cand_frac = max(float((norm < 200).mean()), 0.005)
        seed_pct = 100 - cand_frac * 100 * 0.30           # 후보 중 최암 30%
        mask_pct = 100 - min(cand_frac * 100 * 1.60, 45)  # 후보 전체 + 여유
        hi_t = np.percentile(ink, seed_pct)
        lo_t = np.percentile(ink, mask_pct)
        seed = np.where(ink >= hi_t, ink, 0).astype(np.uint8)
        mask = np.where(ink >= lo_t, ink, 0).astype(np.uint8)
        seed = cv2.min(cv2.dilate(seed, _K3), mask)

        # (d) 측지 팽창 재구성 (비침·잔여 괘선 제거)
        cur, prev = seed, None
        for _ in range(RECON_MAX_ITERS):
            cur = cv2.min(cv2.dilate(cur, _K3), mask)
            if prev is not None and np.array_equal(cur, prev):
                break
            prev = cur.copy()

        # 획 강도 정규화 (연한 펜/연필 보정)
        nz = cur[cur > 0]
        if nz.size:
            scale = 230.0 / max(float(np.percentile(nz, 85)), 1.0)
            cur = np.clip(cur.astype(np.float32) * scale, 0, 255).astype(np.uint8)
        fg = 255 - cur  # 검은 잉크 / 흰 배경

        # (e) 보존율 게이트 (coverage 기반, craft_preprocess (1) 방식):
        # 확실한 잉크(norm<110) 근처가 출력에 얼마나 남았는지(coverage)로 재구성 품질을
        # 판정한다. coverage≥0.97, 또는 coverage≥0.92면서 옅은대역(norm 110~190)을
        # 대량 제거(fer≥0.30 = 비침 제거 증거)면 재구성 채택. 아니면 선형 스트레치 폴백.
        # percentile 방식보다 "seed에서 떨어진 연한 획을 놓친 재구성"을 잘 감지해 stretch로
        # 복구한다(실측: 연한 손글씨 되살림, 재현율 동률). 비침 이미지는 fer가 높아 recon 유지.
        strong = norm < 110
        near = cv2.dilate((fg < 160).astype(np.uint8), _K3) > 0
        cov0 = float(near[strong].mean()) if strong.any() else 1.0
        faint = (norm >= 110) & (norm < 190)
        fer = float((~near)[faint].mean()) if faint.any() else 0.0
        method = "geodesic_reconstruction"
        if not (cov0 >= 0.97 or (cov0 >= 0.92 and fer >= 0.30)):
            method = "linear_stretch"                      # 폴백: 안전한 선형 스트레치
            lo = 90.0
            fg = (np.clip((norm.astype(np.float32) - lo) / (205.0 - lo), 0, 1) * 255).astype(np.uint8)

        # (f) 획 연결 — 잉크 전경을 close한다. fg는 검은 잉크/흰 배경이므로 fg에 직접
        #     CLOSE를 걸면 '밝은 배경'이 닫혀 가는 획이 깎여 끊긴다(실측: 획 43% 소실).
        #     잉크를 반전해 close한 뒤 되돌려 획을 잇는다.
        fg = 255 - cv2.morphologyEx(255 - fg, cv2.MORPH_CLOSE, _K2)
        return (255 - fg).astype(np.uint8), method

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
        return cv2.warpAffine(image, matrix, (new_w, new_h),
                              flags=cv2.INTER_NEAREST, borderValue=0)

    def _resize(self, binary: np.ndarray) -> np.ndarray:
        """업스케일 전용 (하드 이진 대상). 손글씨 충실도를 위해 다운스케일은 하지 않는다.

        원본 해상도를 그대로 유지하되, 장축이 OUTPUT_MIN_SIDE보다 작은 아주 작은
        입력만 탐지·라벨 가독성을 위해 끌어올린다(INTER_NEAREST로 이진 유지).

        다운스케일 제거 근거: 축소-재이진화는 원본 획을 두껍게/거칠게 만들어 사용자의
        실제 글씨와 달라진다. close 버그 수정 후 풀해상도 탐지 성능이 축소본과 동률이라
        충실도 손해 없이 원본 해상도를 유지한다(2026-07 A/B/C 실측)."""
        h, w = binary.shape[:2]
        long_side = max(h, w)
        if long_side < OUTPUT_MIN_SIDE:
            scale = OUTPUT_MIN_SIDE / long_side
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            return cv2.resize(binary, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
        return binary

    def _remove_small_blobs(self, binary: np.ndarray) -> np.ndarray:
        """출력 크기 대비 초소형 연결요소(점 노이즈)를 제거한다."""
        h, w = binary.shape[:2]
        min_area = max(20, int(h * w * 3e-6))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        if n <= 1:
            return binary
        small = np.where(stats[:, cv2.CC_STAT_AREA] < min_area)[0]
        small = small[small != 0]
        if len(small) == 0:
            return binary
        cleaned = binary.copy()
        cleaned[np.isin(labels, small)] = 0
        return cleaned
