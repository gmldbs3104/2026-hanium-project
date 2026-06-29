"""CRAFT raw row box 시각화 — CCA 이전 단계 확인용"""
import sys, os
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector

IMAGE_PATH = (
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일"
    r"\hanium_test\test.jpg"
)
OUT = "debug_output"
os.makedirs(OUT, exist_ok=True)

def load_bgr(path):
    with open(path, "rb") as f:
        raw = f.read()
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)

preprocessor = ImagePreprocessor()
result = preprocessor.preprocess_from_file(IMAGE_PATH)
binary = result.binary_image

detector = CraftDetector(cuda=False)
row_boxes = detector._craft_row_boxes(binary)
print(f"CRAFT raw row boxes: {len(row_boxes)}개")

img_h, img_w = binary.shape[:2]
vis = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)

PALETTE = [
    (255,60,60),(60,200,60),(60,60,255),(220,180,40),
    (200,60,200),(60,200,200),(255,140,30),(120,255,120),
    (255,100,200),(100,200,255),(180,255,60),(255,200,100),
]

heights = [np.array(b, dtype=np.float32)[:, 1].max() - np.array(b, dtype=np.float32)[:, 1].min()
           for b in row_boxes]
median_h = float(np.median(heights)) if heights else 0
max_h = median_h * 1.8

for i, box in enumerate(row_boxes):
    b = np.array(box, dtype=np.float32)
    h = b[:, 1].max() - b[:, 1].min()
    x0 = int(b[:, 0].min()); x1 = int(b[:, 0].max())
    y0 = int(b[:, 1].min()); y1 = int(b[:, 1].max())
    color = PALETTE[i % len(PALETTE)]
    filtered = h > max_h
    thick = 1 if filtered else 3
    label = f"row{i}({'SKIP' if filtered else f'{int(h)}px'})"
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, thick)
    cv2.putText(vis, label, (x0, max(y0 - 6, 14)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    print(f"  row{i}: ({x0},{y0})-({x1},{y1}) h={h:.0f}  {'[SKIP]' if filtered else ''}")

print(f"median_h={median_h:.0f}  max_h={max_h:.0f}")
cv2.imwrite(f"{OUT}/craft_rows_debug.jpg", vis)
print(f"저장 → debug_output/craft_rows_debug.jpg")
detector.unload()
