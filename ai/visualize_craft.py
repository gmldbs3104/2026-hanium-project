"""
SFR-004I CRAFT 글자 단위 탐지 시각화

사용법:
    venv/Scripts/python.exe visualize_craft.py
"""
import sys
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector

IMAGE_PATH = (
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일"
    r"\hanium_test\KakaoTalk_20260629_020459531.jpg"
)

PALETTE = [
    (255,  60,  60), (60, 200,  60), (60,  60, 255), (220, 180,  40),
    (200,  60, 200), (60, 200, 200), (255, 140,  30), (120, 255, 120),
    (255, 100, 200), (100, 200, 255), (180, 255,  60), (255, 200, 100),
]
FONT = cv2.FONT_HERSHEY_SIMPLEX
BG   = (25, 25, 25)


def load_bgr(path: str) -> np.ndarray:
    with open(path, "rb") as f:
        raw = f.read()
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def draw_detections(bgr: np.ndarray, chars: list) -> np.ndarray:
    out = bgr.copy()
    for i, c in enumerate(chars):
        color = PALETTE[i % len(PALETTE)]
        bb = c["bounding_box"]
        x, y = int(bb["x"]), int(bb["y"])
        w, h = int(bb["width"]), int(bb["height"])
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 3)
        label = f"{c['char_id']}  {c['angle']:+.1f}d"
        cv2.putText(out, label, (x, max(y - 6, 14)), FONT, 0.55, color, 2, cv2.LINE_AA)
    return out


def make_info_panel(chars: list, quality: dict, retake: bool,
                    retake_reason: str, h: int = 540) -> np.ndarray:
    W = 360
    panel = np.full((h, W, 3), BG, dtype=np.uint8)

    GREEN  = (80, 220, 80)
    RED    = (80,  80, 255)
    WHITE  = (220, 220, 220)
    YELLOW = (80, 220, 255)

    verdict = "RETAKE" if retake else f"PASS  ({quality['total']}pt)"
    v_col   = RED if retake else GREEN

    lines = [
        ("=== Pipeline Result ===", WHITE),
        ("", WHITE),
        (verdict, v_col),
        ("", WHITE),
        (f"Quality: {quality['total']}pt", WHITE),
        (f"  Sharpness:  {quality['sharpness']:.1f}", WHITE),
        (f"  Contrast:   {quality['contrast']:.1f}", WHITE),
        (f"  Bimodality: {quality['bimodality']:.1f}", WHITE),
        ("", WHITE),
        (f"=== CRAFT Detection ===", WHITE),
        ("", WHITE),
        (f"Detected: {len(chars)} chars", GREEN if chars else RED),
    ]

    if retake_reason:
        lines += [("", WHITE), ("Retake reason:", YELLOW)]
        for chunk in [retake_reason[i:i+30] for i in range(0, len(retake_reason), 30)]:
            lines.append((chunk, YELLOW))

    lines += [("", WHITE), ("--- Char list ---", (180, 180, 100))]
    for c in chars[:16]:
        bb = c["bounding_box"]
        col = PALETTE[int(c["char_id"].split("_")[1]) % len(PALETTE)]
        lines.append((
            f"{c['char_id']}  ({bb['x']:.0f},{bb['y']:.0f})"
            f"  {bb['width']:.0f}x{bb['height']:.0f}  {c['angle']:+.1f}d",
            col,
        ))
    if len(chars) > 16:
        lines.append((f"  ...+{len(chars)-16} more", (160, 160, 160)))

    y = 24
    for text, color in lines:
        if text:
            cv2.putText(panel, text, (8, y), FONT, 0.38, color, 1, cv2.LINE_AA)
        y += 22
    return panel


def main():
    print(f"Image: {IMAGE_PATH.split(chr(92))[-1]}")

    # ── 전처리 ─────────────────────────────────────────────────────────
    preprocessor = ImagePreprocessor()
    result = preprocessor.preprocess_from_file(IMAGE_PATH)
    binary = result.binary_image

    status = "RETAKE" if result.retake_required else "PASS"
    print(f"Preprocessing: {status}  quality={result.quality_score['total']}pt  "
          f"skew={result.skew_angle:+.1f}deg")
    if result.retake_required:
        print(f"  reason: {result.retake_reason}")

    # ── CRAFT 탐지 ──────────────────────────────────────────────────────
    print("Running CRAFT detection...")
    detector = CraftDetector(cuda=False)
    chars = detector.detect(binary)
    print(f"Detected {len(chars)} characters")
    for c in chars:
        bb = c["bounding_box"]
        print(f"  {c['char_id']}: ({bb['x']:.0f},{bb['y']:.0f}) "
              f"{bb['width']:.0f}x{bb['height']:.0f}  angle={c['angle']:+.1f}d")

    # ── 시각화 ─────────────────────────────────────────────────────────
    bgr_orig = load_bgr(IMAGE_PATH)

    # 박스는 binary 좌표계에 그림 (흰 배경 = bitwise_not)
    binary_white = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)
    left  = draw_detections(binary_white, chars)

    # 가운데 패널: 원본 사진 참고용 (비율 유지 리사이즈)
    orig_h, orig_w = bgr_orig.shape[:2]
    orig_scale = 960 / orig_h
    mid = cv2.resize(bgr_orig, (int(orig_w * orig_scale), 960))

    right = make_info_panel(
        chars, result.quality_score,
        result.retake_required, result.retake_reason, h=960
    )

    # 높이 960 기준으로 맞추기
    def fit_h(img, target_h=960):
        h, w = img.shape[:2]
        scale = target_h / h
        return cv2.resize(img, (int(w * scale), target_h))

    canvas = np.hstack([fit_h(left), fit_h(mid), fit_h(right)])

    win = "CRAFT Character Detection"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 1540, 600)
    cv2.imshow(win, canvas)
    print("Press any key to exit.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    detector.unload()


if __name__ == "__main__":
    main()
