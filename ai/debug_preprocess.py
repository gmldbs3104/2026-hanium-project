"""전처리 전/후 비교 이미지 생성 (보고서 첨부용)."""
import sys
import os
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor

IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "test_images/test.jpg"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else (
    "debug_output/" + os.path.splitext(os.path.basename(IMAGE_PATH))[0] + "_preprocess"
)
os.makedirs(OUT_DIR, exist_ok=True)


def load_bytes(path):
    with open(path, "rb") as f:
        raw = np.frombuffer(f.read(), dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


pre = ImagePreprocessor()
result = pre.preprocess_from_file(IMAGE_PATH)

original = load_bytes(IMAGE_PATH)
binary_vis = cv2.cvtColor(cv2.bitwise_not(result.binary_image), cv2.COLOR_GRAY2BGR)

h = max(original.shape[0], binary_vis.shape[0])
orig_r = cv2.resize(original, (int(original.shape[1] * h / original.shape[0]), h))
bin_r = cv2.resize(binary_vis, (int(binary_vis.shape[1] * h / binary_vis.shape[0]), h))
side_by_side = np.hstack([orig_r, np.full((h, 8, 3), 255, np.uint8), bin_r])

out_path = f"{OUT_DIR}/before_after.jpg"
cv2.imwrite(out_path, side_by_side)

print(f"quality={result.quality_score['total']}pt  skew={result.skew_angle:+.1f}deg  "
      f"retake={result.retake_required}")
print(f"saved -> {out_path}")
