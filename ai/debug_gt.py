"""
GT score map 시각화/검증 스크립트.

용도
----
1. gt_generator.py의 단어→글자 분할이 실제 AI Hub 라벨에 대해 올바르게 동작하는지
   (글자 단위로 Gaussian이 분리되는지) 육안 확인.
2. 파인튜닝 체크포인트(ai/models/craft_finetuned_raw.pth)를 실제로 로드해서
   score map이 collapse(전 픽셀 상수값)됐는지 통계로 확인.

사용법
------
  GT 시각화 (matched_pairs.json에서 N개 샘플):
    python debug_gt.py gt [N]

  체크포인트 collapse 여부 확인 (ai/test_images/의 이미지들로):
    python debug_gt.py ckpt [path/to/checkpoint.pth]
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "training"))
from gt_generator import parse_aihub_json, generate_score_maps  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), "debug_output", "gt_check")


def _load_image(path: str) -> np.ndarray:
    """cv2.imread()는 Windows 한글 경로 미지원 → 바이트로 직접 로드."""
    with open(path, "rb") as f:
        raw = np.frombuffer(f.read(), dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


def visualize_gt(manifest_path: str, n: int):
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    os.makedirs(OUT_DIR, exist_ok=True)

    # 다중 글자 단어가 섞인 샘플 위주로 확인 (분할 효과가 잘 보이도록)
    picked = 0
    for entry in manifest:
        if picked >= n:
            break
        img_path, lbl_path = entry["image"], entry["label"]
        if not os.path.exists(img_path) or not os.path.exists(lbl_path):
            continue

        img = _load_image(img_path)
        if img is None:
            continue
        h, w = img.shape[:2]

        char_boxes = parse_aihub_json(lbl_path)
        if not char_boxes:
            continue

        with open(lbl_path, encoding="utf-8") as f:
            raw_words = [it.get("data", "") for it in json.load(f).get("bbox", [])]
        n_words = len(raw_words)
        n_chars = len(char_boxes)
        if n_chars <= n_words:  # 다글자 단어가 하나도 없으면 스킵 (분할 효과 확인 불가)
            continue

        region_map, affinity_map = generate_score_maps(h, w, char_boxes, output_ratio=0.5)

        # region_map을 원본 크기로 업샘플 후 히트맵으로 오버레이
        heat = cv2.resize(region_map, (w, h), interpolation=cv2.INTER_LINEAR)
        heat_u8 = (np.clip(heat, 0, 1) * 255).astype(np.uint8)
        heat_color = cv2.applyColorMap(heat_u8, cv2.COLORMAP_JET)
        overlay = cv2.addWeighted(img, 0.5, heat_color, 0.5, 0)

        # 분할된 글자 박스 경계도 그려서 분할 자체를 직접 확인
        for box in char_boxes:
            pts = box.astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(overlay, [pts], isClosed=True, color=(0, 255, 0), thickness=2)

        stem = entry["stem"]
        out_path = os.path.join(OUT_DIR, f"{stem}_region.jpg")
        cv2.imwrite(out_path, overlay)

        print(f"[{stem}] words={n_words} -> chars={n_chars} "
              f"| region min/max/mean = {region_map.min():.4f}/{region_map.max():.4f}/{region_map.mean():.4f} "
              f"| affinity max = {affinity_map.max():.4f} "
              f"| words: {raw_words}")
        print(f"   -> {out_path}")
        picked += 1

    if picked == 0:
        print("다중 글자 단어를 포함한 샘플을 찾지 못했습니다 (manifest/경로 확인 필요).")


def check_checkpoint(weight_path: str):
    """체크포인트를 CraftNet 구조에 로드해 score map이 collapse했는지 확인."""
    sys.path.insert(0, os.path.dirname(__file__))
    from training.craft_model import CRAFT
    import torch

    model = CRAFT(pretrained_backbone=False, freeze_backbone=False)
    state = torch.load(weight_path, map_location="cpu")
    if isinstance(state, dict) and "model_state" in state:
        state = state["model_state"]
    missing, unexpected = model.load_state_dict(state, strict=False)
    print(f"missing={len(missing)} unexpected={len(unexpected)}")
    if missing or unexpected:
        print("  키가 완전히 일치하지 않습니다 — 이 체크포인트는 현재 구조로 학습된 게 아닐 수 있습니다.")
    model.eval()

    test_dir = os.path.join(os.path.dirname(__file__), "test_images")
    from preprocessing.image_preprocessor import ImagePreprocessor
    pre = ImagePreprocessor()

    import torch.nn.functional as F
    from torchvision import transforms
    normalize = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

    for name in sorted(os.listdir(test_dir)):
        path = os.path.join(test_dir, name)
        result = pre.preprocess_from_file(path)
        binary = result.binary_image
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        rgb = cv2.cvtColor(dist_norm, cv2.COLOR_GRAY2RGB)

        img_t = torch.from_numpy(rgb.transpose(2, 0, 1)).float() / 255.0
        img_t = normalize(img_t).unsqueeze(0)

        with torch.no_grad():
            region, affinity = model(img_t)
        r, a = region.numpy(), affinity.numpy()
        print(f"{name:15s} region  min/max/mean = {r.min():.4f}/{r.max():.4f}/{r.mean():.4f}   "
              f"affinity min/max/mean = {a.min():.4f}/{a.max():.4f}/{a.mean():.4f}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "gt"
    if mode == "gt":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        visualize_gt(os.path.join(os.path.dirname(__file__), "training", "matched_pairs.json"), n)
    elif mode == "ckpt":
        weight_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
            os.path.dirname(__file__), "models", "craft_finetuned_raw.pth")
        check_checkpoint(weight_path)
    else:
        print(__doc__)
