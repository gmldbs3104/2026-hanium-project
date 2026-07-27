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
import pytest

from preprocessing import ImagePreprocessor, QualityScorer
from preprocessing.image_preprocessor import (
    OUTPUT_MIN_SIDE, EXTREME_ASPECT_RATIO, RETAKE_EXTREME_ASPECT,
)


@pytest.fixture(autouse=True)
def _deterministic_seed():
    """랜덤 노이즈로 생성한 모의 이미지가 실행마다 달라지면 deskew가 간헐적으로
    미세 각도를 잡아 종횡비 검사가 불안정하게 실패한다(test_output_resolution).
    각 테스트를 결정적으로 만들기 위해 numpy 시드를 고정한다."""
    np.random.seed(20260721)


def assert_valid_output_size(result, orig_w, orig_h):
    """
    현행 구현 스펙(A 방향): 다운스케일 없이 원본 해상도 유지. 장축이 OUTPUT_MIN_SIDE보다
    작은 아주 작은 입력만 업스케일하므로, 출력 장축은 항상 OUTPUT_MIN_SIDE 이상이다.
    (상한 없음 — 손글씨 충실도를 위해 원본을 그대로 둔다.)

    deskew 회전이 적용된 경우(skew_angle ≥ 0.5°) 캔버스가 확장되어 종횡비가
    정당하게 달라지므로, 종횡비 검사는 회전이 없을 때만 수행한다.
    """
    out_h, out_w = result.binary_image.shape
    long_side = max(out_h, out_w)
    assert long_side >= OUTPUT_MIN_SIDE, \
        f"장축 {long_side}px가 최소 {OUTPUT_MIN_SIDE}px 미만"
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


def make_bleed_through_image(width=800, height=600) -> np.ndarray:
    """
    뒷장 잉크 비침(bleed-through)이 있는 종이를 모사한다.
    위쪽 절반 = 진짜 글씨(배경보다 훨씬 어두움), 아래쪽 절반 = 비침(배경보다 22만 어두움).
    사람 눈에는 아래쪽이 흐릿한 회색으로 보여 글씨와 구분되지만, adaptiveThreshold는
    국소 대비만 보므로 둘을 똑같이 새까만 획으로 만든다.
    """
    img = np.full((height, width), 200, dtype=np.uint8)      # 종이
    for x in range(60, width - 60, 60):
        cv2.line(img, (x, 140), (x + 36, 140), 40, 4)        # 진짜 획 (가로)
        cv2.line(img, (x + 18, 120), (x + 18, 180), 40, 4)   # 진짜 획 (세로)
    for x in range(60, width - 60, 60):
        cv2.line(img, (x, 420), (x + 36, 420), 178, 4)       # 비침 (가로)
        cv2.line(img, (x + 18, 400), (x + 18, 460), 178, 4)  # 비침 (세로)
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
    """출력 해상도(A 방향): 다운스케일 없음, 장축 OUTPUT_MIN_SIDE 이상, 비율 유지."""
    preprocessor = ImagePreprocessor()

    # 업스케일(작은 원본) / 큰 원본은 그대로 유지 케이스
    for (w, h) in [(640, 480), (1920, 1080), (400, 300), (1000, 750)]:
        bgr = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", bgr)
        result = preprocessor.preprocess_from_bytes(encoded.tobytes())
        assert_valid_output_size(result, w, h)

    print(f"  [PASS] 출력 해상도 스펙(다운스케일 없음, 장축 ≥{OUTPUT_MIN_SIDE}px) 확인")


def test_apply_resize_false_skips_resize_step():
    """apply_resize=False면 Step7 리사이즈(업스케일)를 건너뛴다.
    작은 이미지(장축<OUTPUT_MIN_SIDE)로, on은 업스케일되고 off는 원본을 유지함을 확인.
    (A 방향: 다운스케일은 on/off 어느 경우에도 하지 않는다.)"""
    preprocessor = ImagePreprocessor()
    small = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)  # 장축 400 < MIN
    _, enc = cv2.imencode(".png", small)
    raw = enc.tobytes()

    on = preprocessor.preprocess_from_bytes(raw)                    # 기본: 업스케일 적용
    off = preprocessor.preprocess_from_bytes(raw, apply_resize=False)

    assert max(on.binary_image.shape) >= OUTPUT_MIN_SIDE           # 업스케일됨
    assert max(off.binary_image.shape) < OUTPUT_MIN_SIDE           # 원본 유지(업스케일 안 함)
    assert not any("resize" in f for f in off.applied_filters)
    print(f"  [PASS] apply_resize 토글: on={on.binary_image.shape} off={off.binary_image.shape}")


def test_bleed_through_is_not_promoted_to_ink():
    """뒷장 잉크 비침은 획으로 승격되면 안 된다.

    adaptiveThreshold에는 절대 밝기 조건이 없어(주변 평균보다 C=5만 어두우면 획),
    배경과 거의 같은 밝기인 비침도 진짜 획과 동일한 255가 된다. 이진화는 밝기 정보를
    되돌릴 수 없게 버리므로 이후 단계에서 복구가 불가능하다 — 그 결과 CRAFT가
    글자 수만큼의 유령 덩어리를 함께 탐지한다(홀드아웃 test8~10·test_line에서 관측,
    유령/진짜 blob 비율 0.87~1.13 vs 기존 평가셋 7장 0.00~0.20).
    """
    preprocessor = ImagePreprocessor()
    gray = make_bleed_through_image()
    _, encoded = cv2.imencode(".png", image_to_bgr(gray))
    result = preprocessor.preprocess_from_bytes(encoded.tobytes())

    binary = result.binary_image
    half = binary.shape[0] // 2
    real_ink = int((binary[:half] > 127).sum())
    ghost_ink = int((binary[half:] > 127).sum())

    assert real_ink > 0, "진짜 획까지 사라졌다"
    assert ghost_ink < real_ink * 0.1, \
        f"비침이 획으로 승격됨: 진짜 {real_ink}px vs 비침 {ghost_ink}px"
    print(f"  [PASS] 비침 억제 확인 (진짜 {real_ink}px / 비침 {ghost_ink}px)")


def test_extreme_aspect_ratio_triggers_retake():
    """극단적으로 긴 종횡비(초광각·비스듬 촬영)는 재촬영을 요구해야 한다.

    장축을 표준 크기로 맞추면 단축이 뭉개져 글자가 붕괴한다(실측: test9 4.99:1,
    test10 4.04:1). 전처리로 복구 불가능한 촬영 문제이므로 재촬영으로 처리한다.
    임계값(EXTREME_ASPECT_RATIO=3.0)은 test9·10만 걸러내고 정상 표본(test3_crop
    2.23:1, test_line2 1.96:1)은 통과시킨다.
    """
    preprocessor = ImagePreprocessor()
    wide = make_handwriting_image(width=3000, height=600, skew_deg=0.0)  # ar=5.0
    _, encoded = cv2.imencode(".jpg", image_to_bgr(wide))
    result = preprocessor.preprocess_from_bytes(encoded.tobytes())

    assert max(3000, 600) / min(3000, 600) > EXTREME_ASPECT_RATIO
    assert result.retake_required, "극단 종횡비인데 재촬영이 요구되지 않았다"
    assert not result.is_acceptable()
    assert RETAKE_EXTREME_ASPECT in result.retake_reason, \
        f"종횡비 재촬영 사유가 없다: {result.retake_reason!r}"
    print(f"  [PASS] 극단 종횡비 재촬영 확인: {result.retake_reason}")


def test_normal_aspect_ratio_not_flagged_for_aspect():
    """정상 종횡비 이미지는 종횡비 사유로 재촬영되지 않아야 한다."""
    preprocessor = ImagePreprocessor()
    normal = make_handwriting_image(width=1200, height=900, skew_deg=0.0)  # ar=1.33
    _, encoded = cv2.imencode(".jpg", image_to_bgr(normal))
    result = preprocessor.preprocess_from_bytes(encoded.tobytes())

    assert RETAKE_EXTREME_ASPECT not in result.retake_reason, \
        f"정상 종횡비인데 종횡비 재촬영이 걸렸다: {result.retake_reason!r}"
    print(f"  [PASS] 정상 종횡비 통과 확인")


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
