"""
SFR-005I(analyze_size_angle) 검증 스크립트.

pretrained CRAFT로 test_images/*를 탐지한 뒤 크기균일성/기울기 분석을 돌려서
점수·issues가 합리적으로 나오는지 확인한다.

사용법:
  python debug_analysis.py [이미지경로]
  (생략 시 test_images/ 전체)
"""
import sys
import os
import glob

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector
from analysis.handwriting_analyzer import analyze_size_angle


def run_one(pre: ImagePreprocessor, det: CraftDetector, path: str):
    name = os.path.basename(path)
    result = pre.preprocess_from_file(path)
    binary = result.binary_image
    chars = det.detect(binary)

    if not chars:
        print(f"{name:15s} chars=0 (탐지 없음, 분석 스킵)")
        return

    analysis = analyze_size_angle(chars)

    print(f"\n=== {name} ({len(chars)}글자) ===")
    print(f"  size_uniformity_score = {analysis['size_uniformity_score']}")
    print(f"  mean_angle = {analysis['mean_angle']}  angle_std = {analysis['angle_std']}"
          f"  overall_tilt = {analysis['overall_tilt']}")
    print(f"  line_alignment_score = {analysis['line_alignment_score']}")
    if analysis["issues"]:
        print("  issues:")
        for issue in analysis["issues"]:
            print(f"    - {issue}")
    else:
        print("  issues: (없음)")

    flags = [c["size_flag"] for c in analysis["chars"]]
    print(f"  size_flag 분포: normal={flags.count('normal')} "
          f"large={flags.count('large')} small={flags.count('small')}")


def main():
    pre = ImagePreprocessor()
    det = CraftDetector(cuda=False)

    if len(sys.argv) > 1:
        paths = [sys.argv[1]]
    else:
        paths = sorted(glob.glob("test_images/*"))

    for path in paths:
        run_one(pre, det, path)


if __name__ == "__main__":
    main()
