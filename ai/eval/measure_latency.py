"""
4단계: 파이프라인 단계별 지연시간 실측.

요구사항 (requirement.md): CRAFT 추론 500ms, 전처리 5s, 분석(50자) 2s.
모델 로드는 서버 기동 시 1회라는 전제로 로드 시간은 별도 표기.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector
from analysis.handwriting_analyzer import analyze_size_angle

IMAGES = ["test_images/test.jpg", "test_images/test2.png", "test_images/test5.jpg"]

t0 = time.perf_counter()
detector = CraftDetector(cuda=False)
load_s = time.perf_counter() - t0
print(f"모델 로드(서버 기동 1회): {load_s:.2f}s\n")

pre = ImagePreprocessor()
print(f"{'이미지':<22} {'전처리':>8} {'CRAFT탐지':>10} {'분석':>8} {'글자수':>5}")
for path in IMAGES:
    full = os.path.join(os.path.dirname(__file__), "..", path)

    t = time.perf_counter()
    result = pre.preprocess_from_file(full)
    pre_s = time.perf_counter() - t

    t = time.perf_counter()
    chars = detector.detect(result.binary_image)
    det_s = time.perf_counter() - t

    t = time.perf_counter()
    analyze_size_angle(chars)
    ana_s = time.perf_counter() - t

    print(f"{os.path.basename(path):<22} {pre_s:>7.2f}s {det_s:>9.2f}s {ana_s:>7.3f}s {len(chars):>5}")

detector.unload()
print("\n요구사항: 전처리 ≤5s, CRAFT 추론 ≤0.5s, 분석 ≤2s")
