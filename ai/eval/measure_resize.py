"""
IMPLEMENTATION_PLAN 3.1 — 전처리 Step6 리사이즈 on/off 탐지 성능/지연 측정.

목적: "전처리 리사이즈(긴 변 ≤OUTPUT_MAX_SIDE)를 유지 vs 제거" 결정을 실측으로.
결정 기준(2026-07-21 인터뷰): **박스 순증** — 어느 이미지에서도 매칭 박스를 잃지
않고(off ≥ on) 전체 합이 순증할 때만 리사이즈 제거를 채택. 아니면 현행(유지).

좌표계 주의: 수동 GT(eval/gt/*.json)는 '전처리(리사이즈) 후' 좌표계에 라벨돼 있다.
리사이즈를 끄면 이미지가 커지므로 GT도 같은 균일 배율(off/on 장축비)로 스케일해야
공정 비교가 된다 — 리사이즈는 종횡비 보존 균일 스케일이라 단일 배율로 정확히 역변환된다.

참고: CRAFT 자체 long_size(기본 960) 내부 리사이즈가 별도로 있으므로, 이 실험은
'전처리 리사이즈→CRAFT 리사이즈'(이중) vs 'CRAFT 리사이즈만'(단일)의 차이를 본다.

사용법:  PYTHONIOENCODING=utf-8 venv/bin/python eval/measure_resize.py
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector
from evaluate_detection import match_boxes, GT_DIR


def _scale_boxes(boxes, factor):
    return [{"x": b["x"] * factor, "y": b["y"] * factor,
             "width": b["width"] * factor, "height": b["height"] * factor}
            for b in boxes]


def _measure(detector, pre, image_path, gt_boxes, apply_resize):
    """한 조건(resize on/off)에서 탐지 → 매칭 박스 수·pred 수·탐지 지연."""
    result = pre.preprocess_from_file(image_path, apply_resize=apply_resize)
    t0 = time.perf_counter()
    chars = detector.detect(result.binary_image)
    detect_ms = (time.perf_counter() - t0) * 1000.0
    pred_boxes = [c["bounding_box"] for c in chars]
    return {
        "shape": result.binary_image.shape,
        "pred": len(pred_boxes),
        "pred_boxes": pred_boxes,
        "detect_ms": detect_ms,
    }


def main():
    pre = ImagePreprocessor()
    # CraftDetector 배포 기본값과 일치 (evaluate_detection.py 주석과 동일한 함정 회피).
    detector = CraftDetector(cuda=False, long_size=960,
                             text_threshold=0.7, link_threshold=1.0, low_text=0.4)

    rows = []
    for gt_path in sorted(glob.glob(os.path.join(GT_DIR, "*.json"))):
        with open(gt_path, encoding="utf-8") as f:
            gt = json.load(f)
        name = os.path.basename(gt["image"])
        image_path = os.path.join(os.path.dirname(__file__), "..", gt["image"])
        gt_boxes = gt["syllable_boxes"]  # 리사이즈(on) 좌표계
        n_gt = len(gt_boxes)

        on = _measure(detector, pre, image_path, gt_boxes, apply_resize=True)
        off = _measure(detector, pre, image_path, gt_boxes, apply_resize=False)

        # off 좌표계로 GT 스케일 (장축비 = off_h / on_h)
        factor = off["shape"][0] / on["shape"][0]
        gt_off = _scale_boxes(gt_boxes, factor)

        m_on_30 = match_boxes(on["pred_boxes"], gt_boxes, 0.3)
        m_off_30 = match_boxes(off["pred_boxes"], gt_off, 0.3)
        m_on_50 = match_boxes(on["pred_boxes"], gt_boxes, 0.5)
        m_off_50 = match_boxes(off["pred_boxes"], gt_off, 0.5)

        rows.append({
            "name": name, "gt": n_gt, "factor": factor,
            "on_shape": on["shape"], "off_shape": off["shape"],
            "on_pred": on["pred"], "off_pred": off["pred"],
            "m_on_30": m_on_30, "m_off_30": m_off_30,
            "m_on_50": m_on_50, "m_off_50": m_off_50,
            "on_ms": on["detect_ms"], "off_ms": off["detect_ms"],
        })

    detector.unload()

    # 출력
    hdr = (f"{'이미지':<16}{'gt':>4}{'배율':>6} | "
           f"{'on크기':>11}{'off크기':>11} | "
           f"{'m@30 on/off':>12}{'m@50 on/off':>12} | {'지연 on/off(ms)':>18}")
    print("\n===== 3.1 리사이즈 on/off 측정 =====")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['name']:<16}{r['gt']:>4}{r['factor']:>6.2f} | "
              f"{str(r['on_shape']):>11}{str(r['off_shape']):>11} | "
              f"{r['m_on_30']:>5}/{r['m_off_30']:<6}{r['m_on_50']:>5}/{r['m_off_50']:<6} | "
              f"{r['on_ms']:>7.0f}/{r['off_ms']:<9.0f}")

    # 결정: 박스 순증 (@0.3 매칭 기준 — 관대, GT 근사치 감안. @0.5도 손실 없어야 함)
    sum_on_30 = sum(r["m_on_30"] for r in rows)
    sum_off_30 = sum(r["m_off_30"] for r in rows)
    sum_on_50 = sum(r["m_on_50"] for r in rows)
    sum_off_50 = sum(r["m_off_50"] for r in rows)
    any_loss_30 = any(r["m_off_30"] < r["m_on_30"] for r in rows)
    any_loss_50 = any(r["m_off_50"] < r["m_on_50"] for r in rows)
    net_gain = (sum_off_30 > sum_on_30) or (sum_off_50 > sum_on_50)

    print("-" * len(hdr))
    print(f"합계 매칭박스 @0.3: on={sum_on_30} off={sum_off_30} | "
          f"@0.5: on={sum_on_50} off={sum_off_50}")
    adopt = (not any_loss_30) and (not any_loss_50) and net_gain
    print(f"\n[결정 기준: 박스 순증] 이미지별 손실 없음(@0.3,@0.5) + 전체 순증")
    print(f"  → 이미지별 손실: @0.3={any_loss_30} @0.5={any_loss_50} / 전체 순증={net_gain}")
    print(f"  → 리사이즈 제거 채택 여부: {'채택(off)' if adopt else '기각 — 현행 유지(리사이즈 on)'}")


if __name__ == "__main__":
    main()
