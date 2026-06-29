"""
전처리 파이프라인 시각화 스크립트 (원근 보정 포함)
"""
import sys
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
from preprocessing.quality_scorer import QualityScorer
from preprocessing.perspective_corrector import PerspectiveCorrector, PerspectiveCorrectionError


# ── 단계별 중간 결과 수집 ─────────────────────────────────────────────

def collect_steps(bgr: np.ndarray):
    steps = []
    steps.append(("Original", bgr.copy()))

    # Step 1: Grayscale
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    steps.append(("Step1: Grayscale", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)))

    # Step 2: Gaussian Blur
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    steps.append(("Step2: Gaussian Blur", cv2.cvtColor(blurred, cv2.COLOR_GRAY2BGR)))

    # Step 3: 원근 보정
    corrector = PerspectiveCorrector()
    corners = None
    perspective_ok = False
    retake_msg = ""
    try:
        warped, corners = corrector.correct(blurred)
        perspective_ok = True

        # 원본 이미지에 탐지된 꼭짓점 오버레이
        overlay = bgr.copy()
        pts = corners.astype(np.int32)
        cv2.polylines(overlay, [pts], isClosed=True, color=(0, 255, 0), thickness=6)
        for i, pt in enumerate(pts):
            cv2.circle(overlay, tuple(pt), 20, (0, 0, 255), -1)
            cv2.putText(overlay, ["TL","TR","BR","BL"][i], tuple(pt + np.array([10, -10])),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 0), 3, cv2.LINE_AA)
        steps.append(("Step3: Corners Found", overlay))

        # 원근 보정 결과
        warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
        steps.append(("Step3: Perspective Fix", warped_bgr))
        working = warped

    except PerspectiveCorrectionError as e:
        retake_msg = str(e)
        fail_img = bgr.copy()
        # 긴 메시지를 두 줄로 나눠 표시
        words = retake_msg.split()
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        cv2.putText(fail_img, line1, (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
        cv2.putText(fail_img, line2, (20, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
        cv2.putText(fail_img, "-> RETAKE", (20, 280),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 80, 255), 4, cv2.LINE_AA)
        steps.append(("Step3: Perspective [FAILED]", fail_img))
        working = blurred

    # 품질 점수 (보정 후 기준)
    scorer = QualityScorer()
    quality = scorer.score(working)
    quality_ok = scorer.is_acceptable(quality)

    # Step 4: Adaptive Threshold
    binary = cv2.adaptiveThreshold(
        working, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=11, C=2,
    )
    steps.append(("Step4: Threshold", cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)))

    # Step 5: Deskew
    preprocessor = ImagePreprocessor()
    corrected_bin, skew_angle = preprocessor._deskew(binary)
    label = f"Step5: Deskew ({skew_angle:+.1f}d)"
    steps.append((label, cv2.cvtColor(corrected_bin, cv2.COLOR_GRAY2BGR)))

    # Step 6: Resize
    resized = cv2.resize(corrected_bin, (1280, 960), interpolation=cv2.INTER_AREA)
    steps.append(("Step6: Resize 1280x960", cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)))

    retake_reason = "" if (perspective_ok and quality_ok) else (retake_msg if not perspective_ok else f"Quality {quality['total']}pt < 40pt")
    return steps, quality, quality_ok, skew_angle, corners, perspective_ok, retake_reason


# ── 타일 레이아웃 ─────────────────────────────────────────────────────

TILE_W, TILE_H = 380, 270
LABEL_H = 28
COLS = 4
FONT = cv2.FONT_HERSHEY_SIMPLEX
BG    = (30, 30, 30)
WHITE = (230, 230, 230)
GREEN = (80, 200, 80)
RED   = (80, 80, 255)
CYAN  = (200, 200, 80)
YELLOW = (80, 200, 255)


def make_tile(title: str, image: np.ndarray) -> np.ndarray:
    tile = np.full((TILE_H + LABEL_H, TILE_W, 3), BG, dtype=np.uint8)
    tile[LABEL_H:] = cv2.resize(image, (TILE_W, TILE_H))
    cv2.rectangle(tile, (0, 0), (TILE_W, LABEL_H), (55, 55, 55), -1)
    color = RED if "FAILED" in title else WHITE
    cv2.putText(tile, title, (5, LABEL_H - 7), FONT, 0.42, color, 1, cv2.LINE_AA)
    return tile


def make_info_tile(quality, quality_ok, skew_angle, perspective_ok, corners, retake_reason="") -> np.ndarray:
    tile = np.full((TILE_H + LABEL_H, TILE_W, 3), BG, dtype=np.uint8)
    cv2.rectangle(tile, (0, 0), (TILE_W, LABEL_H), (55, 55, 55), -1)
    cv2.putText(tile, "Quality Report", (5, LABEL_H - 7), FONT, 0.42, WHITE, 1, cv2.LINE_AA)

    if perspective_ok and quality_ok:
        verdict = f"PASS  ({quality['total']}pt)"
        v_color = GREEN
    else:
        verdict = "RETAKE REQUIRED"
        v_color = RED

    lines = [
        (verdict, v_color),
        ("", WHITE),
        (f"Sharpness:  {quality['sharpness']:.1f}  (w=40%)", WHITE),
        (f"Contrast:   {quality['contrast']:.1f}  (w=30%)", WHITE),
        (f"Bimodality: {quality['bimodality']:.1f}  (w=30%)", WHITE),
        ("", WHITE),
        (f"Perspective: {'OK' if perspective_ok else 'FAILED'}", GREEN if perspective_ok else RED),
        (f"Skew: {skew_angle:+.1f}deg", CYAN if abs(skew_angle) >= 0.5 else WHITE),
    ]
    if retake_reason:
        lines += [("", WHITE), ("Reason:", YELLOW)]
        # 긴 메시지를 20자씩 잘라서 출력
        for chunk in [retake_reason[j:j+28] for j in range(0, len(retake_reason), 28)]:
            lines.append((chunk, YELLOW))

    y = LABEL_H + 22
    for text, color in lines:
        if text:
            cv2.putText(tile, text, (10, y), FONT, 0.38, color, 1, cv2.LINE_AA)
        y += 23
    return tile


def build_grid(steps, quality, quality_ok, skew_angle, corners, perspective_ok, retake_reason="") -> np.ndarray:
    tiles = [make_tile(t, img) for t, img in steps]
    tiles.append(make_info_tile(quality, quality_ok, skew_angle, perspective_ok, corners, retake_reason))

    rows = []
    for i in range(0, len(tiles), COLS):
        row = tiles[i:i + COLS]
        while len(row) < COLS:
            row.append(np.full_like(tiles[0], BG))
        rows.append(np.hstack(row))
    return np.vstack(rows)


# ── 메인 ─────────────────────────────────────────────────────────────

IMAGE_PATHS = [
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일\hanium_test\KakaoTalk_20260628_215804559.jpg",
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일\hanium_test\KakaoTalk_20260628_215804559_01.jpg",
]


def main():
    win = "OpenCV Preprocessing Pipeline"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 1520, 820)

    for idx, path in enumerate(IMAGE_PATHS, 1):
        print(f"\n[{idx}/{len(IMAGE_PATHS)}] {path.split(chr(92))[-1]}")
        with open(path, "rb") as f:
            raw = f.read()
        bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            print("  ERROR: cannot read image")
            continue

        steps, quality, quality_ok, skew, corners, persp_ok, retake_reason = collect_steps(bgr)

        verdict = "PASS" if (persp_ok and quality_ok) else "RETAKE"
        print(f"  Perspective: {'OK' if persp_ok else 'FAILED'}")
        print(f"  Quality: {quality['total']}pt  (sharpness={quality['sharpness']:.1f}  contrast={quality['contrast']:.1f}  bimodal={quality['bimodality']:.1f})")
        print(f"  Skew: {skew:+.1f}deg")
        print(f"  => {verdict}" + (f"  ({retake_reason})" if retake_reason else ""))

        grid = build_grid(steps, quality, quality_ok, skew, corners, persp_ok, retake_reason)
        cv2.imshow(win, grid)
        key_msg = "next" if idx < len(IMAGE_PATHS) else "exit"
        print(f"  Press any key to {key_msg}.")
        cv2.waitKey(0)

    cv2.destroyAllWindows()
    print("\nDone.")


if __name__ == "__main__":
    main()
