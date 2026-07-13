"""AI Hub 이미지의 예측 박스를 시각화 + 병합 통계 (3단계 디버그, 일회성)."""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector

with open(os.path.join(os.path.dirname(__file__), "..", "training", "matched_pairs.json"),
          encoding="utf-8") as f:
    manifest = {e["stem"]: e for e in json.load(f)}

stem = "IMG_OCR_53_4TO_03894"
pre = ImagePreprocessor()
det = CraftDetector(cuda=False, link_threshold=1.0)
result = pre.preprocess_from_file(manifest[stem]["image"])
binary = result.binary_image
chars = det.detect(binary)

hs = sorted(c["bounding_box"]["height"] for c in chars)
ws = sorted(c["bounding_box"]["width"] for c in chars)
n = len(chars)
print(f"박스 {n}개")
print(f"height 분포: min={hs[0]:.0f} p25={hs[n//4]:.0f} p50={hs[n//2]:.0f} "
      f"p75={hs[3*n//4]:.0f} p90={hs[int(n*0.9)]:.0f} max={hs[-1]:.0f}")
print(f"width  분포: min={ws[0]:.0f} p50={ws[n//2]:.0f} p90={ws[int(n*0.9)]:.0f} max={ws[-1]:.0f}")

vis = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)
for c in chars:
    bb = c["bounding_box"]
    x, y, w, h = int(bb["x"]), int(bb["y"]), int(bb["width"]), int(bb["height"])
    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 1)
out = os.path.join(os.path.dirname(__file__), "gt_work", f"{stem}_pred.jpg")
cv2.imwrite(out, vis)
print(f"시각화 → {out}")
det.unload()
