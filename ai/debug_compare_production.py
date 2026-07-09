"""
실제 배포 파이프라인(CraftDetector, 기본 threshold 0.7/0.4/0.4)으로
pretrained vs epoch9 파인튜닝 모델을 절대 수치로 비교.

AI Hub 3개 이미지(정답 글자수 기지) + test_images 7개 전부 실행.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "training")
from preprocessing.image_preprocessor import ImagePreprocessor
from gt_generator import parse_aihub_json
import detection.craft_detector as cd


def load_image_bytes(path):
    with open(path, "rb") as f:
        raw = np.frombuffer(f.read(), dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


AIHUB_IMAGES = {
    "IMG_OCR_53_4TO_03894": r"C:\Users\dmack\Downloads\053.대용량 손글씨 OCR 데이터\01.데이터\1.Training\원천데이터\TS9\HW-OCR\4.Validation\T.Tablet\O.Form\IMG_OCR_53_4TO_03894.png",
    "IMG_OCR_53_4TO_03895": r"C:\Users\dmack\Downloads\053.대용량 손글씨 OCR 데이터\01.데이터\1.Training\원천데이터\TS9\HW-OCR\4.Validation\T.Tablet\O.Form\IMG_OCR_53_4TO_03895.png",
    "IMG_OCR_53_4TO_03896": r"C:\Users\dmack\Downloads\053.대용량 손글씨 OCR 데이터\01.데이터\1.Training\원천데이터\TS9\HW-OCR\4.Validation\T.Tablet\O.Form\IMG_OCR_53_4TO_03896.png",
}

with open("training/matched_pairs.json", encoding="utf-8") as f:
    manifest = json.load(f)
label_paths = {e["stem"]: e["label"] for e in manifest}


def run(weight_override, label):
    print(f"\n===== {label} (weight={weight_override}) =====")
    orig = cd._FINETUNED_WEIGHT
    cd._FINETUNED_WEIGHT = weight_override if weight_override else "__none__"
    pre = ImagePreprocessor()
    detector = cd.CraftDetector(cuda=False)  # default thresholds 0.7/0.4/0.4

    print("--- AI Hub (in-domain, GT count known) ---")
    for stem, path in AIHUB_IMAGES.items():
        char_boxes = parse_aihub_json(label_paths[stem])
        gt_count = len(char_boxes)
        result = pre.preprocess_from_file(path)
        chars = detector.detect(result.binary_image)
        print(f"  {stem}: 탐지={len(chars)}  정답={gt_count}  recall={len(chars)/gt_count*100:.0f}%")

    print("--- test_images (out-of-domain, no GT) ---")
    for name in sorted(os.listdir("test_images")):
        path = os.path.join("test_images", name)
        result = pre.preprocess_from_file(path)
        chars = detector.detect(result.binary_image)
        print(f"  {name}: 탐지={len(chars)}")

    detector.unload()
    cd._FINETUNED_WEIGHT = orig


if __name__ == "__main__":
    run(None, "PRETRAINED (파인튜닝 없음)")
    run(os.path.abspath("models/craft_finetuned_raw.pth"), "EPOCH 9 (현재 배포본)")
