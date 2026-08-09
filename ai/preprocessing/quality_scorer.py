import cv2
import numpy as np


class QualityScorer:
    """
    이미지 품질 점수를 0~100 범위로 산출한다.
    40점 미만이면 재촬영을 요청해야 한다. (REQ-003I-4)
    """

    THRESHOLD_RETAKE = 40

    # 선명도 점수가 최대(100)가 되는 Laplacian 분산 기준값
    # 실제 폰 카메라 고해상도 사진(3024x4032) 기준:
    #   선명 ≈ 15~30 / 보통 ≈ 5~15 / 흐림 < 3
    _SHARPNESS_MAX = 20.0
    # 대비 점수가 최대(100)가 되는 표준편차 기준값
    _CONTRAST_MAX = 80.0

    def score(self, gray: np.ndarray) -> dict:
        """
        Parameters
        ----------
        gray : np.ndarray
            Grayscale 이미지 (dtype=uint8)

        Returns
        -------
        dict
            {
              "total": int,          # 종합 점수 0~100
              "sharpness": float,    # 선명도 기여 점수
              "contrast": float,     # 대비 기여 점수
              "bimodality": float,   # 이진화 가능성 기여 점수
            }
        """
        sharpness = self._sharpness_score(gray)
        contrast = self._contrast_score(gray)
        bimodality = self._bimodality_score(gray)

        # 가중 평균: 선명도 40%, 대비 30%, 이진화 가능성 30%
        total = sharpness * 0.4 + contrast * 0.3 + bimodality * 0.3
        total = int(round(min(total, 100.0)))

        return {
            "total": total,
            "sharpness": round(sharpness, 1),
            "contrast": round(contrast, 1),
            "bimodality": round(bimodality, 1),
        }

    def is_acceptable(self, score_result: dict) -> bool:
        return score_result["total"] >= self.THRESHOLD_RETAKE

    # ------------------------------------------------------------------
    # 내부 지표 계산
    # ------------------------------------------------------------------

    def _sharpness_score(self, gray: np.ndarray) -> float:
        """Laplacian 분산값으로 선명도를 측정한다."""
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        return min(lap_var / self._SHARPNESS_MAX * 100.0, 100.0)

    def _contrast_score(self, gray: np.ndarray) -> float:
        """픽셀 표준편차로 명암 대비를 측정한다."""
        std = float(gray.std())
        return min(std / self._CONTRAST_MAX * 100.0, 100.0)

    def _bimodality_score(self, gray: np.ndarray) -> float:
        """
        히스토그램이 두 봉우리(배경/획)로 나뉘는 정도를 측정한다.
        Otsu 임계값 전후 픽셀 비율이 균형 잡혀 있을수록 높은 점수.
        """
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        white_ratio = np.count_nonzero(binary) / binary.size
        # 흑/백 비율이 20%~80% 사이일 때 최적 (손글씨 특성상 흰 배경 우세)
        balance = 1.0 - abs(white_ratio - 0.8) / 0.8
        return max(balance * 100.0, 0.0)
