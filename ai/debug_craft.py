"""
CRAFT 글자 탐지 결과 시각화 디버그 스크립트.

사용법:
  python debug_craft.py <이미지경로> [출력폴더]

예시:
  python debug_craft.py test_images/test.jpg
  python debug_craft.py test_images/test3.png debug_output/test3
"""
import sys, os
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector

IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "test_images/test.jpg"
OUT_DIR    = sys.argv[2] if len(sys.argv) > 2 else (
    "debug_output/" + os.path.splitext(os.path.basename(IMAGE_PATH))[0]
)
os.makedirs(OUT_DIR, exist_ok=True)

PALETTE = [
    (220, 50,  50),  (50, 180,  50),  (50,  50, 220), (200, 160,  30),
    (180, 50, 180),  (50, 180, 180),  (230, 110,  30), (100, 230, 100),
    (230, 80, 160),  (80, 160, 230),  (150, 230,  50), (230, 180,  80),
]

# ── 전처리 ────────────────────────────────────────────────────────────────
print(f"[1] Preprocessing: {IMAGE_PATH}")
preprocessor = ImagePreprocessor()
result       = preprocessor.preprocess_from_file(IMAGE_PATH)
binary       = result.binary_image          # THRESH_BINARY_INV (획=255)
img_h, img_w = binary.shape[:2]
status = "RETAKE" if result.retake_required else "PASS"
print(f"    {status}  quality={result.quality_score['total']}pt"
      f"  skew={result.skew_angle:+.1f}deg  size={img_w}x{img_h}")

# ── CRAFT 탐지 ────────────────────────────────────────────────────────────
print("[2] Running CRAFT detection...")
detector = CraftDetector(cuda=False)
chars    = detector.detect(binary)
detector.unload()
print(f"    → {len(chars)} chars detected")

# ── 시각화 베이스: binary를 BGR로 변환 (흰 배경 + 검은 획) ───────────────
base = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)

# ── 시각화 1: tight bounding box ─────────────────────────────────────────
vis_box = base.copy()
for i, c in enumerate(chars):
    bb    = c["bounding_box"]
    x, y  = int(bb["x"]), int(bb["y"])
    w, h  = int(bb["width"]), int(bb["height"])
    color = PALETTE[i % len(PALETTE)]

    cv2.rectangle(vis_box, (x, y), (x + w, y + h), color, 2)

    # 중심점
    cx, cy = int(c["center"]["x"]), int(c["center"]["y"])
    cv2.circle(vis_box, (cx, cy), 3, color, -1)

    # char_id 레이블
    label = c["char_id"]
    fs    = 0.45
    (tw, th_), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
    lx = max(0, x)
    ly = max(th_ + 3, y - 3)
    cv2.rectangle(vis_box, (lx, ly - th_ - 2), (lx + tw + 4, ly + 1), color, -1)
    cv2.putText(vis_box, label, (lx + 2, ly - 1),
                cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), 1, cv2.LINE_AA)

out_box = f"{OUT_DIR}/chars_bbox.jpg"
cv2.imwrite(out_box, vis_box)
print(f"    saved → {out_box}")

# ── 시각화 2: 중심점 + 기울기 선 ─────────────────────────────────────────
vis_meta = base.copy()
for i, c in enumerate(chars):
    bb     = c["bounding_box"]
    cx, cy = int(c["center"]["x"]), int(c["center"]["y"])
    angle  = c["angle"]
    color  = PALETTE[i % len(PALETTE)]
    half_w = int(bb["width"] / 2)

    # 기울기 방향선
    rad = np.radians(angle)
    dx  = int(half_w * np.cos(rad))
    dy  = int(half_w * np.sin(rad))
    cv2.line(vis_meta, (cx - dx, cy - dy), (cx + dx, cy + dy), color, 2)
    cv2.circle(vis_meta, (cx, cy), 4, color, -1)

    # angle 레이블
    label = f"{angle:+.1f}"
    cv2.putText(vis_meta, label, (cx + 5, cy - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

out_meta = f"{OUT_DIR}/chars_meta.jpg"
cv2.imwrite(out_meta, vis_meta)
print(f"    saved → {out_meta}")

# ── 콘솔 출력 ────────────────────────────────────────────────────────────
print()
print(f"{'id':<8} {'x':>5} {'y':>5} {'w':>5} {'h':>5} {'cx':>7} {'cy':>7} {'angle':>7} {'conf':>6}")
print("-" * 65)
for c in chars:
    bb = c["bounding_box"]
    print(f"{c['char_id']:<8} {bb['x']:>5.0f} {bb['y']:>5.0f}"
          f" {bb['width']:>5.0f} {bb['height']:>5.0f}"
          f" {c['center']['x']:>7.1f} {c['center']['y']:>7.1f}"
          f" {c['angle']:>+7.1f} {c['confidence']:>6.3f}")

print(f"\nDone. total={len(chars)} chars")
