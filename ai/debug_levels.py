"""
3단계 시각화: 행(row) → 단어(word) → 글자(char)
결과를 debug_output/에 저장
"""
import sys, os
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector
from detection.bbox_utils import sort_reading_order

IMAGE_PATH = (
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일"
    r"\hanium_test\test2.png"
)
OUT = "debug_output"
os.makedirs(OUT, exist_ok=True)

PALETTE = [
    (220, 50, 50), (50, 180, 50), (50, 50, 220), (200, 160, 30),
    (180, 50, 180), (50, 180, 180), (230, 110, 30), (100, 230, 100),
    (230, 80, 160), (80, 160, 230), (150, 230, 50), (230, 180, 80),
    (80, 80, 230), (230, 130, 130), (130, 230, 180),
]


def draw_box(img, x, y, w, h, color, thickness=3, label="", font_scale=0.7):
    cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)
    if label:
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
        lx, ly = x, max(y - 6, th + 4)
        cv2.rectangle(img, (lx, ly - th - 4), (lx + tw + 6, ly + 2), color, -1)
        cv2.putText(img, label, (lx + 3, ly - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 2, cv2.LINE_AA)


def chars_to_words(chars):
    """
    같은 행에서 인접 글자 사이 gap들의 중앙값 × 2.0 이상이면 단어 경계로 판정.
    행 내 글자가 1~2개뿐이면 gap 비교 불가 → 행 전체를 1단어로.
    """
    if not chars:
        return []

    sorted_c = sort_reading_order(chars)
    avg_h = np.mean([c["bounding_box"]["height"] for c in sorted_c])
    row_tol = avg_h * 0.6

    # 행 그룹화
    rows = []
    for c in sorted_c:
        cy = c["bounding_box"]["y"] + c["bounding_box"]["height"] / 2
        placed = False
        for row in rows:
            row_cy = np.mean([r["bounding_box"]["y"] + r["bounding_box"]["height"] / 2
                              for r in row])
            if abs(cy - row_cy) < row_tol:
                row.append(c)
                placed = True
                break
        if not placed:
            rows.append([c])

    words = []
    for row in rows:
        row_s = sorted(row, key=lambda c: c["bounding_box"]["x"])
        if len(row_s) < 2:
            words.append(row_s)
            continue

        # 인접 글자 간 x gap 계산
        gaps = []
        for i in range(len(row_s) - 1):
            bb_cur  = row_s[i]["bounding_box"]
            bb_next = row_s[i + 1]["bounding_box"]
            gap = bb_next["x"] - (bb_cur["x"] + bb_cur["width"])
            gaps.append(gap)

        median_gap = float(np.median(gaps))
        # 중앙값의 2.5배 이상이면 단어 경계
        word_threshold = max(median_gap * 2.5, 1.0)

        current = [row_s[0]]
        for i, c in enumerate(row_s[1:]):
            if gaps[i] >= word_threshold:
                words.append(current)
                current = [c]
            else:
                current.append(c)
        words.append(current)

    return words


# ── 전처리 ────────────────────────────────────────────────────────────
print("전처리 중...")
preprocessor = ImagePreprocessor()
result = preprocessor.preprocess_from_file(IMAGE_PATH)
binary = result.binary_image
img_h, img_w = binary.shape[:2]
base = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)

status = "RETAKE" if result.retake_required else "PASS"
print(f"전처리: {status}  quality={result.quality_score['total']}pt  "
      f"skew={result.skew_angle:+.1f}deg  출력 크기={img_w}x{img_h}")

# ── CRAFT 탐지 ────────────────────────────────────────────────────────
print("CRAFT 탐지 중...")
detector = CraftDetector(cuda=False)
row_boxes_raw = detector._craft_row_boxes(binary)
merged_rows   = detector._merge_overlapping_rows(row_boxes_raw, img_w, img_h)
chars         = detector.detect(binary)
detector.unload()

words = chars_to_words(chars)
print(f"행: {len(merged_rows)}개  |  단어: {len(words)}개  |  글자: {len(chars)}개")

# ════════════════════════════════════════════════════════════════════
# 1. 행(row) 시각화
# ════════════════════════════════════════════════════════════════════
vis_row = base.copy()
for i, (rx0, ry0, rx1, ry1) in enumerate(merged_rows):
    color = PALETTE[i % len(PALETTE)]
    draw_box(vis_row, rx0, ry0, rx1 - rx0, ry1 - ry0, color,
             thickness=4, label=f"행 {i+1}", font_scale=0.9)
cv2.imwrite(f"{OUT}/level1_rows.jpg", vis_row)
print(f"행 시각화    → debug_output/level1_rows.jpg")

# ════════════════════════════════════════════════════════════════════
# 2. 단어(word) 시각화
# ════════════════════════════════════════════════════════════════════
vis_word = base.copy()
for wi, word in enumerate(words):
    color = PALETTE[wi % len(PALETTE)]
    xs  = [c["bounding_box"]["x"] for c in word]
    ys  = [c["bounding_box"]["y"] for c in word]
    x2s = [c["bounding_box"]["x"] + c["bounding_box"]["width"]  for c in word]
    y2s = [c["bounding_box"]["y"] + c["bounding_box"]["height"] for c in word]
    wx0, wy0 = int(min(xs)), int(min(ys))
    ww,  wh  = int(max(x2s)) - wx0, int(max(y2s)) - wy0
    pad = 6
    draw_box(vis_word, wx0 - pad, wy0 - pad, ww + pad * 2, wh + pad * 2,
             color, thickness=4, label=f"단어 {wi+1}", font_scale=0.8)
cv2.imwrite(f"{OUT}/level2_words.jpg", vis_word)
print(f"단어 시각화  → debug_output/level2_words.jpg")

# ════════════════════════════════════════════════════════════════════
# 3. 글자(char) 시각화
# ════════════════════════════════════════════════════════════════════
vis_char = base.copy()
for i, c in enumerate(chars):
    color = PALETTE[i % len(PALETTE)]
    bb = c["bounding_box"]
    x, y = int(bb["x"]), int(bb["y"])
    w, h = int(bb["width"]), int(bb["height"])
    draw_box(vis_char, x, y, w, h, color, thickness=3,
             label=c["char_id"], font_scale=0.55)
cv2.imwrite(f"{OUT}/level3_chars.jpg", vis_char)
print(f"글자 시각화  → debug_output/level3_chars.jpg")

# ── 글자별 상세 로그 ─────────────────────────────────────────────────
print()
for c in chars:
    bb = c["bounding_box"]
    print(f"  {c['char_id']}: ({bb['x']:.0f},{bb['y']:.0f}) "
          f"{bb['width']:.0f}x{bb['height']:.0f}")

print("\n완료.")
