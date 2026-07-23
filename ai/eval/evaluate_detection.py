"""
음절 단위 탐지 정확도 평가 스크립트 (1단계 산출물).

평가셋
------
1. 수동 GT (eval/gt/*.json): test(10)·test2(25)·test3_crop(140)·test4(238)·
   test5(39)·test6(22)·test7(62) — 총 7장 536음절.
   — label_helper.py로 blob을 음절 단위로 사람이 그룹핑해서 만든 정밀 GT.
   — 좌표계: 전처리(이진화+deskew) 후 이미지 기준.
2. AI Hub 자동 GT: 3장 (531자) — 사람이 라벨링한 단어 박스를 글자 수로 등분
   (gt_generator.parse_aihub_json). 박스는 근사치지만 개수는 정확.
   — 좌표계: 원본 기준. deskew가 0도일 때만 사용(스크립트가 검증).

지표
----
- 예측 박스 ↔ GT 박스를 IoU 내림차순 그리디 1:1 매칭.
- P/R/F1 @ IoU 0.5 (엄격) 및 @ IoU 0.3 (관대 — GT 근사치 감안)
- count_ratio: 예측 수 / 정답 수 (1.0이 이상적; >1 과분할, <1 과병합)
- split/merge: 과분할·과병합을 분리 카운트(count_merge_split). count_ratio는 둘이
  상쇄돼 1.0처럼 보일 수 있어, F1 하나로는 안 보이는 오류 구성을 드러낸다.
  후처리를 손볼 때 "병합을 줄였나 / 분할을 늘렸나"를 이 두 수로 확인한다.
  split = 여러 pred가 겹친 GT 수, merge = 여러 GT를 덮은 pred 수.

사용법
------
  python eval/evaluate_detection.py                 # 기본(현재 배포 설정)
  python eval/evaluate_detection.py --tag baseline  # 결과에 태그 표시
  옵션: --text-th 0.7 --link-th 0.4 --low-text 0.4  (2단계 실험용)
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "training"))
from preprocessing.image_preprocessor import ImagePreprocessor
from detection.craft_detector import CraftDetector
from gt_generator import parse_aihub_json

GT_DIR = os.path.join(os.path.dirname(__file__), "gt")

# AI Hub 평가 이미지 (수동 GT가 커버 못 하는 소형·밀집 손글씨 도메인)
AIHUB_ROOT = r"C:\Users\dmack\Downloads\053.대용량 손글씨 OCR 데이터"
AIHUB_STEMS = ["IMG_OCR_53_4TO_03894", "IMG_OCR_53_4TO_03895", "IMG_OCR_53_4TO_03896"]


def _load_manifest():
    path = os.path.join(os.path.dirname(__file__), "..", "training", "matched_pairs.json")
    with open(path, encoding="utf-8") as f:
        return {e["stem"]: e for e in json.load(f)}


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["width"], a["y"] + a["height"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def _iou_contain(a, b):
    """(IoU, 포함비율) 반환. 포함비율 = 교집합 / 두 박스 중 작은 쪽 넓이."""
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["width"], a["y"] + a["height"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if inter <= 0:
        return 0.0, 0.0
    aa = (ax1 - ax0) * (ay1 - ay0)
    ab = (bx1 - bx0) * (by1 - by0)
    iou = inter / (aa + ab - inter)
    contain = inter / min(aa, ab)
    return iou, contain


def count_merge_split(pred_boxes, gt_boxes, iou_th=0.3, contain_th=0.6):
    """과분할·과병합을 분리 측정. F1만 보면 둘이 상쇄돼 보이는 착시를 막는다.

    겹침 성립 = IoU >= iou_th 또는 (작은 박스가) contain_th 이상 포함됨.
    (작은 조각이 큰 박스에 들어가는 경우 IoU는 낮아도 병합/분할 신호이므로 포함비율 병용.)

    반환 (split_gt, merge_pred):
      split_gt   = 2개 이상의 pred가 겹친 GT 수  → 정답 글자가 여러 조각으로 쪼개짐(과분할)
      merge_pred = 2개 이상의 GT를 덮은 pred 수  → 예측 박스 하나가 글자들을 뭉침(과병합)
    """
    gt_hits = [0] * len(gt_boxes)
    pred_hits = [0] * len(pred_boxes)
    for pi, p in enumerate(pred_boxes):
        for gi, g in enumerate(gt_boxes):
            iou, contain = _iou_contain(p, g)
            if iou >= iou_th or contain >= contain_th:
                gt_hits[gi] += 1
                pred_hits[pi] += 1
    split_gt = sum(1 for h in gt_hits if h >= 2)
    merge_pred = sum(1 for h in pred_hits if h >= 2)
    return split_gt, merge_pred


def match_boxes(pred_boxes, gt_boxes, iou_thresh):
    """IoU 내림차순 그리디 1:1 매칭 → 매칭 수 반환."""
    pairs = []
    for pi, p in enumerate(pred_boxes):
        for gi, g in enumerate(gt_boxes):
            v = _iou(p, g)
            if v >= iou_thresh:
                pairs.append((v, pi, gi))
    pairs.sort(reverse=True)
    used_p, used_g = set(), set()
    matched = 0
    for v, pi, gi in pairs:
        if pi in used_p or gi in used_g:
            continue
        used_p.add(pi)
        used_g.add(gi)
        matched += 1
    return matched


def evaluate_image(detector, pre, image_path, gt_boxes, gt_in_original_coords=False):
    result = pre.preprocess_from_file(image_path)
    if gt_in_original_coords:
        # 원본 좌표계 GT(AI Hub) → 전처리(리사이즈) 후 좌표계로 변환.
        # deskew(회전)까지 걸리면 변환이 복잡해지므로 그 경우엔 평가 제외.
        if abs(result.skew_angle) > 0.01:
            raise RuntimeError(
                f"{image_path}: deskew {result.skew_angle:+.1f}° 적용됨 — 원본 좌표계 GT와 "
                f"불일치하므로 이 이미지는 자동 GT 평가에 쓸 수 없습니다")
        import cv2
        with open(image_path, "rb") as f:
            raw = np.frombuffer(f.read(), dtype=np.uint8)
        orig_h = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE).shape[0]
        scale = result.binary_image.shape[0] / orig_h
        gt_boxes = [{"x": b["x"] * scale, "y": b["y"] * scale,
                     "width": b["width"] * scale, "height": b["height"] * scale}
                    for b in gt_boxes]
    chars = detector.detect(result.binary_image)
    pred_boxes = [c["bounding_box"] for c in chars]

    n_pred, n_gt = len(pred_boxes), len(gt_boxes)
    split_gt, merge_pred = count_merge_split(pred_boxes, gt_boxes)
    row = {"pred": n_pred, "gt": n_gt,
           "count_ratio": n_pred / n_gt if n_gt else 0.0,
           "split_gt": split_gt, "merge_pred": merge_pred}
    for th in (0.5, 0.3):
        m = match_boxes(pred_boxes, gt_boxes, th)
        p = m / n_pred if n_pred else 0.0
        r = m / n_gt if n_gt else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        row[f"P@{th}"], row[f"R@{th}"], row[f"F1@{th}"] = p, r, f1
    return row


def aihub_gt_boxes(label_path):
    """parse_aihub_json의 4점 폴리곤 → 축정렬 bbox 리스트."""
    boxes = []
    for pts in parse_aihub_json(label_path):
        pts = np.asarray(pts, dtype=np.float32)
        x0, y0 = pts[:, 0].min(), pts[:, 1].min()
        x1, y1 = pts[:, 0].max(), pts[:, 1].max()
        boxes.append({"x": float(x0), "y": float(y0),
                      "width": float(x1 - x0), "height": float(y1 - y0)})
    return boxes


def main():
    # 기본값은 반드시 CraftDetector 배포 기본값과 일치시킬 것 — 과거 이 기본값이
    # 1단계 기준선 시점(link=0.4, long=1280)에 머물러 있어서, 인자 없이 돌리면
    # 배포 설정(link=1.0, long=960+adaptive)이 아닌 옛 설정을 평가하는 함정이
    # 있었다 (2026-07-18 발견·수정). "자체 설정으로 검증하다 배포 경로와 어긋나는"
    # Phase 12의 실수와 같은 유형이므로, CraftDetector 기본값을 바꾸면 여기도 갱신.
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="current")
    ap.add_argument("--text-th", type=float, default=0.7)
    ap.add_argument("--link-th", type=float, default=1.0)
    ap.add_argument("--low-text", type=float, default=0.4)
    ap.add_argument("--long-size", type=int, default=960)
    # 팀 결정(2026-07-18): 손글씨 평가는 test_images 수동 GT만 사용. AI Hub 양식지
    # 3장(인쇄 텍스트 FP·도메인 불일치로 참고 가치만 있음)은 --aihub 지정 시에만 포함.
    ap.add_argument("--aihub", action="store_true",
                    help="AI Hub 양식지 3장(참고용 자동 GT)도 평가에 포함")
    args = ap.parse_args()

    pre = ImagePreprocessor()
    detector = CraftDetector(
        cuda=False,
        long_size=args.long_size,
        text_threshold=args.text_th,
        link_threshold=args.link_th,
        low_text=args.low_text,
    )

    rows = {}

    # 1) 수동 GT
    for gt_path in sorted(glob.glob(os.path.join(GT_DIR, "*.json"))):
        with open(gt_path, encoding="utf-8") as f:
            gt = json.load(f)
        image_path = os.path.join(os.path.dirname(__file__), "..", gt["image"])
        name = os.path.basename(gt["image"])
        rows[name] = evaluate_image(detector, pre, image_path, gt["syllable_boxes"])

    # 2) AI Hub 자동 GT (--aihub 지정 시에만 — 기본 평가는 손글씨 test_images만)
    if args.aihub:
        manifest = _load_manifest()
        for stem in AIHUB_STEMS:
            entry = manifest.get(stem)
            if entry is None or not os.path.exists(entry["image"]):
                print(f"(스킵) {stem}: 이미지/라벨 없음")
                continue
            gt_boxes = aihub_gt_boxes(entry["label"])
            rows[stem] = evaluate_image(detector, pre, entry["image"], gt_boxes,
                                        gt_in_original_coords=True)

    detector.unload()

    # 출력
    print(f"\n===== 평가 결과 [{args.tag}] "
          f"(text={args.text_th} link={args.link_th} low={args.low_text} "
          f"long={args.long_size}) =====")
    hdr = (f"{'이미지':<24} {'pred':>5} {'gt':>4} {'ratio':>6} "
           f"{'F1@0.5':>7} {'F1@0.3':>7} {'R@0.3':>6} {'split':>6} {'merge':>6}")
    print(hdr)
    print("-" * len(hdr))
    f1_50, f1_30 = [], []
    tot_split, tot_merge = 0, 0
    for name, r in rows.items():
        print(f"{name:<24} {r['pred']:>5} {r['gt']:>4} {r['count_ratio']:>6.2f} "
              f"{r['F1@0.5']:>7.3f} {r['F1@0.3']:>7.3f} {r['R@0.3']:>6.3f} "
              f"{r['split_gt']:>6} {r['merge_pred']:>6}")
        f1_50.append(r["F1@0.5"])
        f1_30.append(r["F1@0.3"])
        tot_split += r["split_gt"]
        tot_merge += r["merge_pred"]
    print("-" * len(hdr))
    print(f"{'평균/합계':<24} {'':>5} {'':>4} {'':>6} "
          f"{sum(f1_50)/len(f1_50):>7.3f} {sum(f1_30)/len(f1_30):>7.3f} {'':>6} "
          f"{tot_split:>6} {tot_merge:>6}")


if __name__ == "__main__":
    main()
