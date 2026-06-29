"""
파이프라인 전체 테스트 — 결과를 debug_output/ 에 이미지로 저장 (GUI 불필요)
"""
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

PALETTE = [
    (255,60,60),(60,200,60),(60,60,255),(220,180,40),
    (200,60,200),(60,200,200),(255,140,30),(120,255,120),
    (255,100,200),(100,200,255),(180,255,60),(255,200,100),
]

def load_bgr(path):
    with open(path, "rb") as f:
        raw = f.read()
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)

# ── 원본 로드 ──────────────────────────────────────────────────────────
bgr_orig = load_bgr(IMAGE_PATH)
print(f"원본 이미지: {bgr_orig.shape[1]}x{bgr_orig.shape[0]}")

# ── 전체 파이프라인 (전처리 → 이진화) ─────────────────────────────────
print("전체 파이프라인 실행 중...")
preprocessor = ImagePreprocessor()
result = preprocessor.preprocess_from_file(IMAGE_PATH)

status = "RETAKE" if result.retake_required else "PASS"
print(f"전처리: {status}  quality={result.quality_score['total']}pt  "
      f"skew={result.skew_angle:+.1f}deg")
print(f"적용 필터: {result.applied_filters}")
if result.retake_required:
    print(f"재촬영 이유: {result.retake_reason}")

binary = result.binary_image

# 이진화 결과 저장 (흰 배경)
cv2.imwrite(f"{OUT}/binary_new.jpg", cv2.bitwise_not(binary))
print(f"이진화 결과  →  debug_output/binary_new.jpg  ({binary.shape[1]}x{binary.shape[0]})")

# ── CRAFT 탐지 ─────────────────────────────────────────────────────────
print("\nCRAFT 탐지 실행 중...")
detector = CraftDetector(cuda=False)
chars = detector.detect(binary)
print(f"탐지 결과: {len(chars)}개 글자")

for c in chars:
    bb = c["bounding_box"]
    print(f"  {c['char_id']}: ({bb['x']:.0f},{bb['y']:.0f}) "
          f"{bb['width']:.0f}x{bb['height']:.0f}  angle={c['angle']:+.1f}d")

# CRAFT 박스를 이진화 이미지에 그리기
vis = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)
for i, c in enumerate(chars):
    color = PALETTE[i % len(PALETTE)]
    bb = c["bounding_box"]
    x, y, w, h = int(bb["x"]), int(bb["y"]), int(bb["width"]), int(bb["height"])
    cv2.rectangle(vis, (x,y), (x+w,y+h), color, 3)
    cv2.putText(vis, c["char_id"], (x, max(y-6,14)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

cv2.imwrite(f"{OUT}/craft_result_new.jpg", vis)
print(f"탐지 시각화  →  debug_output/craft_result_new.jpg")

detector.unload()
print("\n완료.")
