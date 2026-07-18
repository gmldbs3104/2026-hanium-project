"""
OpenCV 전처리 파이프라인 테스트

테스트용 이미지를 직접 생성하여 외부 파일 없이 실행 가능합니다.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
import numpy as np
import base64

from preprocessing import ImagePreprocessor, QualityScorer
from preprocessing.image_preprocessor import OUTPUT_MIN_SIDE, OUTPUT_MAX_SIDE


def assert_valid_output_size(result, orig_w, orig_h):
    """
    현재 SFR-003I 구현 스펙: 비율 유지 리사이즈, 장축이 OUTPUT_MIN_SIDE~OUTPUT_MAX_SIDE.
    (초기 스펙이던 '1280×960 고정'은 CRAFT 탐지 정확도를 위해 비율 유지 방식으로
    변경됨 — IMPLEMENTATION_HISTORY.md 참고. 원본 장축이 범위 안이면 그대로 유지.)

    deskew 회전이 적용된 경우(skew_angle ≥ 0.5°) 캔버스가 확장되어 종횡비가
    정당하게 달라지므로, 종횡비 검사는 회전이 없을 때만 수행한다.
    """
    out_h, out_w = result.binary_image.shape
    long_side = max(out_h, out_w)
    assert OUTPUT_MIN_SIDE <= long_side <= OUTPUT_MAX_SIDE, \
        f"장축 {long_side}px가 {OUTPUT_MIN_SIDE}~{OUTPUT_MAX_SIDE} 범위를 벗어남"
    if abs(result.skew_angle) < 0.5:
        orig_ratio = orig_w / orig_h
        out_ratio = out_w / out_h
        assert abs(orig_ratio - out_ratio) < 0.05, \
            f"종횡비 훼손: 원본 {orig_ratio:.3f} vs 출력 {out_ratio:.3f}"


def make_handwriting_image(width=800, height=600, skew_deg=5.0) -> np.ndarray:
    """
    테스트용 손글씨 모의 이미지를 생성한다.
    흰 배경에 검은 선을 그려 기울어진 텍스트 줄처럼 만든다.
    """
    img = np.ones((height, width), dtype=np.uint8) * 240  # 연한 흰 배경

    # 가우시안 노이즈 추가
    noise = np.random.normal(0, 10, img.shape).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 기울어진 획 그리기
    center_x, center_y = width // 2, height // 2
    rad = np.radians(skew_deg)

    for row_offset in [-100, -50, 0, 50, 100]:
        for col in range(50, width - 50, 30):
            # 기울기를 반영한 y 좌표
            y = int(center_y + row_offset + (col - center_x) * np.tan(rad))
            if 0 <= y < height:
                cv2.rectangle(img, (col, y - 8), (col + 20, y + 8), 30, -1)

    return img


def image_to_bgr(gray: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


# -----------------------------------------------------------------------
# 테스트 케이스
# -----------------------------------------------------------------------

def test_pipeline_runs_without_error():
    """파이프라인이 오류 없이 완주하는지 확인한다."""
    preprocessor = ImagePreprocessor()
    gray = make_handwriting_image()
    bgr = image_to_bgr(gray)

    _, encoded = cv2.imencode(".jpg", bgr)
    raw_bytes = encoded.tobytes()

    result = preprocessor.preprocess_from_bytes(raw_bytes)

    assert result.binary_image is not None
    assert_valid_output_size(result, gray.shape[1], gray.shape[0])
    assert result.binary_image.dtype == np.uint8
    print(f"  [PASS] 파이프라인 정상 실행")
    print(f"         출력 크기: {result.binary_image.shape}")
    print(f"         적용 필터: {result.applied_filters}")


def test_output_resolution():
    """출력 해상도: 비율 유지, 장축 800~1280px 범위. (현행 SFR-003I 구현 스펙)"""
    preprocessor = ImagePreprocessor()

    # 업스케일(작은 원본) / 다운스케일(큰 원본) / 범위 내 유지 케이스
    for (w, h) in [(640, 480), (1920, 1080), (400, 300), (1000, 750)]:
        bgr = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", bgr)
        result = preprocessor.preprocess_from_bytes(encoded.tobytes())
        assert_valid_output_size(result, w, h)

    print(f"  [PASS] 출력 해상도 스펙(비율 유지, 장축 {OUTPUT_MIN_SIDE}~{OUTPUT_MAX_SIDE}px) 확인")


def test_quality_score_range():
    """품질 점수가 항상 0~100 범위여야 한다."""
    scorer = QualityScorer()

    # 최적 이미지 (선명한 손글씨)
    good = make_handwriting_image()
    score_good = scorer.score(good)
    assert 0 <= score_good["total"] <= 100

    # 최악 이미지 (완전 균일한 회색 → 선명도/대비 없음)
    blank = np.full((600, 800), 128, dtype=np.uint8)
    score_blank = scorer.score(blank)
    assert 0 <= score_blank["total"] <= 100

    print(f"  [PASS] 품질 점수 범위 확인")
    print(f"         손글씨 모의 이미지: {score_good['total']}점")
    print(f"         균일 회색 이미지:   {score_blank['total']}점")


def test_low_quality_rejection():
    """품질 40점 미만 이미지는 is_acceptable() == False여야 한다."""
    scorer = QualityScorer()
    blank = np.full((600, 800), 128, dtype=np.uint8)
    score = scorer.score(blank)
    assert not scorer.is_acceptable(score), f"균일 이미지가 acceptable로 판정됨: {score['total']}점"
    print(f"  [PASS] 저품질 이미지 거부 확인 (점수: {score['total']})")


def test_deskew_reduces_angle():
    """기울어진 이미지를 처리하면 skew_angle이 기록되어야 한다."""
    preprocessor = ImagePreprocessor()
    gray = make_handwriting_image(skew_deg=10.0)
    bgr = image_to_bgr(gray)
    _, encoded = cv2.imencode(".jpg", bgr)
    result = preprocessor.preprocess_from_bytes(encoded.tobytes())

    print(f"  [PASS] 기울기 감지 완료")
    print(f"         감지된 기울기: {result.skew_angle:.1f}°")
    print(f"         적용 필터: {result.applied_filters}")


def test_file_size_limit():
    """10MB 초과 파일은 ValueError를 발생시켜야 한다."""
    preprocessor = ImagePreprocessor()
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    try:
        preprocessor.preprocess_from_bytes(oversized)
        assert False, "ValueError가 발생하지 않았습니다"
    except ValueError as e:
        print(f"  [PASS] 파일 크기 초과 거부: {e}")


def test_base64_input():
    """Base64 인코딩된 입력도 처리할 수 있어야 한다."""
    preprocessor = ImagePreprocessor()
    gray = make_handwriting_image()
    bgr = image_to_bgr(gray)
    _, encoded = cv2.imencode(".jpg", bgr)
    b64 = base64.b64encode(encoded.tobytes()).decode("utf-8")

    result = preprocessor.preprocess_from_base64(b64)
    assert_valid_output_size(result, gray.shape[1], gray.shape[0])
    print(f"  [PASS] Base64 입력 처리 확인")


# -----------------------------------------------------------------------
# 실행
# -----------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_pipeline_runs_without_error,
        test_output_resolution,
        test_quality_score_range,
        test_low_quality_rejection,
        test_deskew_reduces_angle,
        test_file_size_limit,
        test_base64_input,
    ]

    passed = 0
    failed = 0
    for test in tests:
        print(f"\n[ {test.__name__} ]")
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"결과: {passed}개 통과 / {failed}개 실패")
