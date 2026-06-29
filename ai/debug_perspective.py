"""
원근 보정 내부 단계별 중간 이미지 저장 — 어느 전략이 왜 실패하는지 파악
"""
import sys, os
import cv2
import numpy as np

sys.path.insert(0, ".")
from preprocessing.perspective_corrector import PerspectiveCorrector

IMAGE_PATH = (
    r"C:\Users\dmack\OneDrive\문서\카카오톡 받은 파일"
    r"\hanium_test\KakaoTalk_20260629_020459531.jpg"
)
OUT = "debug_output"
os.makedirs(OUT, exist_ok=True)

with open(IMAGE_PATH, "rb") as f:
    raw = f.read()
bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)

# 다운샘플
DETECT_WIDTH = 800
h, w = blurred.shape[:2]
scale = DETECT_WIDTH / w
small = cv2.resize(blurred, (DETECT_WIDTH, int(h * scale)))
print(f"small shape: {small.shape}  min={small.min()}  max={small.max()}  median={int(np.median(small))}")
cv2.imwrite(f"{OUT}/dbg_small.jpg", small)

# ── 전략 1: CLAHE + Otsu (bright region) ─────────────────────────────
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(small)
cv2.imwrite(f"{OUT}/dbg_clahe.jpg", enhanced)
print(f"CLAHE  min={enhanced.min()}  max={enhanced.max()}  median={int(np.median(enhanced))}")

_, bright = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
cv2.imwrite(f"{OUT}/dbg_otsu_clahe.jpg", bright)
white_pct = np.sum(bright > 0) / bright.size * 100
print(f"Otsu(CLAHE)  흰 픽셀 비율: {white_pct:.1f}%")

k = max(25, int(small.shape[1] * 0.06))
k = k if k % 2 == 1 else k + 1
kernel = np.ones((k, k), np.uint8)
closed = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)
cv2.imwrite(f"{OUT}/dbg_closed_clahe.jpg", closed)
print(f"Closing kernel: {k}x{k}")

contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print(f"컨투어 수: {len(contours)}")
if contours:
    areas = sorted([cv2.contourArea(c) for c in contours], reverse=True)
    print(f"상위 5개 면적: {[int(a) for a in areas[:5]]}")
    print(f"이미지 면적: {small.shape[0]*small.shape[1]}  10%: {int(small.shape[0]*small.shape[1]*0.10)}")

    largest = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(largest)

    vis = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(vis, [largest], -1, (0,255,0), 2)
    cv2.drawContours(vis, [hull], -1, (0,0,255), 2)

    peri = cv2.arcLength(hull, True)
    for eps in [0.02, 0.03, 0.04, 0.05, 0.07, 0.10, 0.12, 0.15]:
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        pts = approx.reshape(-1, 2).astype(np.float32)
        label = f"eps={eps:.2f} -> {len(approx)}pts"
        if len(approx) == 4:
            # 유효성 검사
            area = cv2.contourArea(pts.astype(np.int32))
            corrector = PerspectiveCorrector()
            valid = corrector._is_valid_quad(pts, small)
            label += f"  [{'VALID' if valid else 'INVALID'}]"
            if not valid:
                # 왜 invalid?
                ordered = corrector._order_points(pts)
                tl, tr, br, bl = ordered
                width  = max(float(np.linalg.norm(tr - tl)), float(np.linalg.norm(br - bl)))
                height = max(float(np.linalg.norm(bl - tl)), float(np.linalg.norm(br - tr)))
                aspect = width / height if height > 0 else 0
                mask = np.zeros(small.shape[:2], dtype=np.uint8)
                cv2.fillPoly(mask, [pts.astype(np.int32)], 255)
                brightness = float(np.median(small[mask > 0])) if np.any(mask > 0) else 0
                label += f" area={int(area)} asp={aspect:.2f} bright={brightness:.0f}"
        print(f"  {label}")
    cv2.imwrite(f"{OUT}/dbg_contour.jpg", vis)

# ── 전략 2: 원본 Otsu (CLAHE 없이) ──────────────────────────────────
_, bright2 = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
cv2.imwrite(f"{OUT}/dbg_otsu_raw.jpg", bright2)
white_pct2 = np.sum(bright2 > 0) / bright2.size * 100
print(f"\nOtsu(raw)  흰 픽셀 비율: {white_pct2:.1f}%")

closed2 = cv2.morphologyEx(bright2, cv2.MORPH_CLOSE, kernel)
cv2.imwrite(f"{OUT}/dbg_closed_raw.jpg", closed2)
contours2, _ = cv2.findContours(closed2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if contours2:
    areas2 = sorted([cv2.contourArea(c) for c in contours2], reverse=True)
    print(f"컨투어 수: {len(contours2)}  상위 면적: {[int(a) for a in areas2[:5]]}")

print("\n완료. debug_output/ 에 중간 이미지 저장됨")
