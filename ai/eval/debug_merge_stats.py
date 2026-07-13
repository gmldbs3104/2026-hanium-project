"""03894에서 병합 단계가 실제로 뭘 하는지 계측 (8~9단계 디버그, 일회성)."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector, _group_rows
import detection.craft_detector as cd

with open(os.path.join(os.path.dirname(__file__), "..", "training", "matched_pairs.json"),
          encoding="utf-8") as f:
    manifest = {e["stem"]: e for e in json.load(f)}

stem = sys.argv[1] if len(sys.argv) > 1 else "IMG_OCR_53_4TO_03894"
pre = ImagePreprocessor()
det = CraftDetector(cuda=False, link_threshold=1.0)
result = pre.preprocess_from_file(manifest[stem]["image"])
binary = result.binary_image

pred = det._craft_prediction(binary)
raw = det._process_boxes(pred, binary)
efter_split = cd.split_wide_boxes(raw, binary)
print(f"raw={len(raw)}  split후={len(efter_split)}")

rows = _group_rows(efter_split)
print(f"행 개수: {len(rows)}")
row_sizes = sorted(len(r) for r in rows)
print(f"행 크기 분포: {row_sizes[:10]} ... {row_sizes[-5:]}")

for row in sorted(rows, key=len, reverse=True)[:5]:
    members = [efter_split[i] for i in row]
    n = len(members)
    y0s = sorted(c["y"] for c in members)
    y1s = sorted(c["y"] + c["h"] for c in members)
    ref_h = y1s[min(n - 1, int(n * 0.9))] - y0s[int(n * 0.1)]
    hs = sorted(c["h"] for c in members)
    ws = sorted(c["w"] for c in members)
    # 인접 박스 x간격 통계
    xs = sorted((c["x"], c["x"] + c["w"]) for c in members)
    gaps = [max(0, xs[i+1][0] - xs[i][1]) for i in range(len(xs)-1)]
    gaps_s = sorted(gaps)
    print(f"행 n={n} ref_h={ref_h:.0f} | h중앙값={hs[n//2]:.0f} w중앙값={ws[n//2]:.0f} "
          f"| x간격 p25={gaps_s[len(gaps)//4]:.0f} p50={gaps_s[len(gaps)//2]:.0f} "
          f"p75={gaps_s[3*len(gaps)//4]:.0f} | 허용간격(0.18ref)={ref_h*0.18:.1f}")

merged = cd.merge_jaso_boxes(efter_split)
print(f"병합 후: {len(merged)}")
det.unload()
