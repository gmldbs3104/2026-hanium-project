import cv2
import numpy as np


RETAKE_CORNERS_NOT_FOUND = "종이 전체가 프레임 안에 들어오게 찍어주세요."
RETAKE_PAPER_TOO_CLOSE   = "조금 더 멀리서 찍어주세요. 종이 가장자리가 잘렸습니다."
RETAKE_POOR_QUALITY      = "더 밝은 곳에서 선명하게 다시 찍어주세요."


class PerspectiveCorrectionError(Exception):
    """원근 보정 실패 → 재촬영 필요. message에 사용자 안내 문구 포함."""
    pass


class PerspectiveCorrector:
    """
    종이 4개 꼭짓점을 탐지하고 정방향으로 원근 보정한다.

    탐지 전략 (순서대로 시도):
      1. 밝은 영역(종이) 직접 탐지: CLAHE → Otsu → 닫기 → 최대 컨투어 → 볼록 껍질
      2. Heavy Blur + Canny
      3. Otsu + 닫기 + 볼록 껍질 (기존 방식)

    각 전략은 _is_valid_quad 검사를 통과한 경우에만 결과를 반환한다.
    """

    # 탐지용 다운샘플 너비 (높을수록 정밀하지만 느림)
    DETECT_WIDTH   = 800
    # 종이는 이미지 면적의 최소 이 비율을 차지해야 함
    MIN_AREA_RATIO = 0.10
    # 꼭짓점이 이미지 가장자리 이 비율 이내이면 "잘린" 것으로 판정
    # 0.0 = 꼭짓점이 이미지 밖으로 나간 경우에만 거부 (근접만으로는 거부 안 함)
    EDGE_MARGIN    = 0.0
    # 종이 가로/세로 비율 허용 범위 (width/height)
    MIN_ASPECT     = 0.35   # 세로로 긴 경우
    MAX_ASPECT     = 2.80   # 가로로 긴 경우
    # 사각형 내부 밝기 하한 (0~255) — 종이(흰색)는 밝아야 한다
    MIN_INNER_BRIGHTNESS = 110

    def correct(self, gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Returns
        -------
        (warped_gray, corners)  corners shape=(4,2), 순서: TL TR BR BL

        Raises
        ------
        PerspectiveCorrectionError
        """
        corners = self._find_and_validate_corners(gray)
        warped = self._warp(gray, corners)
        return warped, corners

    # ------------------------------------------------------------------
    # 탐지 + 유효성 검사
    # ------------------------------------------------------------------

    def _find_and_validate_corners(self, gray: np.ndarray) -> np.ndarray:
        h, w = gray.shape[:2]
        scale = self.DETECT_WIDTH / w
        small = cv2.resize(gray, (self.DETECT_WIDTH, int(h * scale)))

        corners_small = self._detect(small)
        if corners_small is None:
            raise PerspectiveCorrectionError(RETAKE_CORNERS_NOT_FOUND)

        corners_orig = corners_small / scale

        margin_px = min(h, w) * self.EDGE_MARGIN
        if self._is_cut_off(corners_orig, w, h, margin_px):
            raise PerspectiveCorrectionError(RETAKE_PAPER_TOO_CLOSE)

        return corners_orig

    def _is_cut_off(self, corners: np.ndarray, w: int, h: int, margin: float) -> bool:
        for x, y in corners:
            if x < margin or y < margin or x > w - margin or y > h - margin:
                return True
        return False

    # ------------------------------------------------------------------
    # 탐지 전략 (순서대로 시도)
    # ------------------------------------------------------------------

    def _detect(self, small: np.ndarray) -> np.ndarray | None:
        # 전략 1: 밝은 영역(종이) 직접 탐지 — 가장 신뢰도 높음
        result = self._try_bright_region(small)
        if result is not None:
            return result

        # 전략 2: Heavy Blur + Canny
        result = self._try_heavy_blur(small)
        if result is not None:
            return result

        # 전략 3: Otsu + 닫기 (기존 방식)
        return self._try_otsu_hull(small)

    def _try_bright_region(self, small: np.ndarray) -> np.ndarray | None:
        """
        CLAHE → Otsu 이진화 → 형태학적 닫기 → 가장 큰 밝은 영역 → 볼록 껍질 근사.

        종이(흰색)와 배경(책상 등 어두운 색)의 밝기 차이를 이용한다.
        """
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(small)

        _, bright = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 종이 내부 글자를 채워 하나의 덩어리로 만들기
        k = max(25, int(small.shape[1] * 0.06))
        k = k if k % 2 == 1 else k + 1
        kernel = np.ones((k, k), np.uint8)
        closed = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        min_area = self.MIN_AREA_RATIO * small.shape[0] * small.shape[1]
        valid = [c for c in contours if cv2.contourArea(c) >= min_area]
        if not valid:
            return None

        largest = max(valid, key=cv2.contourArea)
        hull = cv2.convexHull(largest)
        peri = cv2.arcLength(hull, True)

        for eps in [0.02, 0.03, 0.04, 0.05, 0.07, 0.10]:
            approx = cv2.approxPolyDP(hull, eps * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                if self._is_valid_quad(pts, small):
                    return self._order_points(pts)
        return None

    def _try_heavy_blur(self, small: np.ndarray) -> np.ndarray | None:
        ksize = self._odd(int(small.shape[1] * 0.06))
        heavy = cv2.GaussianBlur(small, (ksize, ksize), 0)
        edges = cv2.Canny(heavy, 10, 50)
        dilated = cv2.dilate(edges, np.ones((7, 7), np.uint8), iterations=3)
        return self._find_quad(dilated, small)

    def _try_otsu_hull(self, small: np.ndarray) -> np.ndarray | None:
        _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.ones((15, 15), np.uint8)
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < self.MIN_AREA_RATIO * small.shape[0] * small.shape[1]:
            return None

        hull = cv2.convexHull(largest)
        peri = cv2.arcLength(hull, True)
        for eps in [0.02, 0.03, 0.04, 0.05, 0.08]:
            approx = cv2.approxPolyDP(hull, eps * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                if self._is_valid_quad(pts, small):
                    return self._order_points(pts)
        return None

    # ------------------------------------------------------------------
    # 공통 유틸
    # ------------------------------------------------------------------

    def _find_quad(self, edge_map: np.ndarray, small: np.ndarray) -> np.ndarray | None:
        contours, _ = cv2.findContours(edge_map, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        min_area = self.MIN_AREA_RATIO * small.shape[0] * small.shape[1]

        for eps_ratio in [0.02, 0.03, 0.04, 0.05, 0.08]:
            for c in contours[:15]:
                if cv2.contourArea(c) < min_area:
                    break
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, eps_ratio * peri, True)
                if len(approx) == 4:
                    pts = approx.reshape(4, 2).astype(np.float32)
                    if self._is_valid_quad(pts, small):
                        return self._order_points(pts)
        return None

    def _is_valid_quad(self, pts: np.ndarray, small: np.ndarray) -> bool:
        """
        검출된 사각형이 종이처럼 보이는지 검사한다.

        조건:
          1. 충분한 면적
          2. 적절한 가로/세로 비율 (MIN_ASPECT ~ MAX_ASPECT)
          3. 사각형 내부의 평균 밝기가 MIN_INNER_BRIGHTNESS 이상 (종이는 밝다)
        """
        h, w = small.shape[:2]
        area = cv2.contourArea(pts.astype(np.int32))
        if area < self.MIN_AREA_RATIO * h * w:
            return False

        ordered = self._order_points(pts)
        tl, tr, br, bl = ordered
        width  = max(float(np.linalg.norm(tr - tl)), float(np.linalg.norm(br - bl)))
        height = max(float(np.linalg.norm(bl - tl)), float(np.linalg.norm(br - tr)))
        if height < 1.0:
            return False
        aspect = width / height
        if aspect < self.MIN_ASPECT or aspect > self.MAX_ASPECT:
            return False

        # 내부 밝기 검사: 마스크를 그려 내부 픽셀 중앙값
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [pts.astype(np.int32)], 255)
        inner_pixels = small[mask > 0]
        if inner_pixels.size == 0:
            return False
        if float(np.median(inner_pixels)) < self.MIN_INNER_BRIGHTNESS:
            return False

        return True

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        """
        4개 꼭짓점을 TL → TR → BR → BL 순서로 정렬한다.

        합(x+y): TL=최소, BR=최대
        차(y-x): TR=최소(큰x,작은y), BL=최대(작은x,큰y)
        """
        rect = np.zeros((4, 2), dtype=np.float32)
        s    = pts.sum(axis=1)
        diff = np.diff(pts, axis=1).flatten()   # diff[i] = y_i - x_i
        rect[0] = pts[np.argmin(s)]     # TL
        rect[1] = pts[np.argmin(diff)]  # TR
        rect[2] = pts[np.argmax(s)]     # BR
        rect[3] = pts[np.argmax(diff)]  # BL
        return rect

    def _odd(self, n: int) -> int:
        return n if n % 2 == 1 else n + 1

    # ------------------------------------------------------------------
    # 원근 변환
    # ------------------------------------------------------------------

    def _warp(self, image: np.ndarray, corners: np.ndarray) -> np.ndarray:
        tl, tr, br, bl = corners
        max_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
        max_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))

        dst = np.array([
            [0,         0        ],
            [max_w - 1, 0        ],
            [max_w - 1, max_h - 1],
            [0,         max_h - 1],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(corners, dst)
        return cv2.warpPerspective(image, M, (max_w, max_h))
