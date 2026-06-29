"""
raw projection 상세 디버그 - 이진화 후 각 열의 실제 잉크 픽셀 수 확인.
"""
import sys
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from craft_text_detector import Craft
from detection.craft_detector import CONFIDENCE_THRESHOLD, ROW_PAD_RATIO

IMAGE_PATH = (
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일"
    r"\hanium_test\KakaoTalk_20260629_020459531.jpg"
)
OUT_DIR = "debug_output"
import os; os.makedirs(OUT_DIR, exist_ok=True)

preprocessor = ImagePreprocessor()
result = preprocessor.preprocess_from_file(IMAGE_PATH)
binary = result.binary_image
print(f"binary shape: {binary.shape}  skew={result.skew_angle:+.1f}deg")

# binary 저장 (흰 배경)
cv2.imwrite(f"{OUT_DIR}/binary_clean.jpg", cv2.bitwise_not(binary))
print(f"Saved binary_clean.jpg")

craft = Craft(
    output_dir=None, rectify=True, export_extra=False,
    text_threshold=CONFIDENCE_THRESHOLD, link_threshold=0.4,
    low_text=0.4, cuda=False, long_size=1280, refiner=False, crop_type="box",
)
rgb = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2RGB)
pred = craft.detect_text(rgb)
boxes = pred.get("boxes", [])
img_h, img_w = binary.shape[:2]

box_info = []
for box in boxes:
    b = np.array(box, dtype=np.float32)
    x0 = int(np.clip(b[:,0].min(), 0, img_w))
    x1 = int(np.clip(b[:,0].max(), 0, img_w))
    y0 = int(np.clip(b[:,1].min(), 0, img_h))
    y1 = int(np.clip(b[:,1].max(), 0, img_h))
    box_info.append((x0, y0, x1, y1, x1-x0))

box_info.sort(key=lambda v: v[4], reverse=True)

print(f"\nTop 4 boxes (sorted by width):")
for idx, (x0, y0, x1, y1, bw) in enumerate(box_info[:4]):
    row_h = y1 - y0
    pad = int(row_h * ROW_PAD_RATIO)
    ry0 = max(0, y0 - pad)
    ry1 = min(img_h, y1 + pad)
    crop = binary[ry0:ry1, x0:x1]

    # raw projection: 각 열의 255-pixel 수
    proj_raw = np.sum(crop > 0, axis=0).astype(np.float32)  # pixel count per col
    p_max = float(proj_raw.max()) or 1.0
    proj_n = proj_raw / p_max

    # 통계
    print(f"\n  [{idx}] ({x0},{y0})→({x1},{y1})  w={bw}  h={row_h}")
    print(f"    crop h={crop.shape[0]}  raw_proj max={p_max:.0f} min={proj_raw.min():.0f} mean={proj_raw.mean():.1f}")
    print(f"    zero-cols: {np.sum(proj_raw==0)}/{bw}  "
          f"<5% max: {np.sum(proj_n<0.05)}/{bw}  "
          f"<10% max: {np.sum(proj_n<0.10)}/{bw}  "
          f"<15% max: {np.sum(proj_n<0.15)}/{bw}")

    # raw 프로젝션 이미지
    bar_h = 120
    bar = np.ones((bar_h + 40, bw, 3), dtype=np.uint8) * 245
    for xi, v in enumerate(proj_n):
        bht = int(v * bar_h)
        cv2.line(bar, (xi, bar_h - bht), (xi, bar_h), (80,120,200), 1)
    for thresh, col in [(0.05,(220,0,0)),(0.10,(0,120,0)),(0.15,(0,0,200))]:
        ty = bar_h - int(thresh * bar_h)
        cv2.line(bar, (0,ty), (bw,ty), col, 1)
    cv2.putText(bar, f"[{idx}] w={bw} h={row_h}  min={proj_n.min():.3f}",
                (4, bar_h+15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,0,0), 1)
    cv2.putText(bar, f"<5%:{np.sum(proj_n<0.05)} <10%:{np.sum(proj_n<0.10)} <15%:{np.sum(proj_n<0.15)} cols",
                (4, bar_h+32), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,0,0), 1)

    crop_vis = cv2.cvtColor(cv2.bitwise_not(crop), cv2.COLOR_GRAY2BGR)
    out = np.vstack([crop_vis, bar]) if crop_vis.shape[1] == bar.shape[1] else bar
    cv2.imwrite(f"{OUT_DIR}/raw_proj_{idx}.jpg", out)
    print(f"    → debug_output/raw_proj_{idx}.jpg")
