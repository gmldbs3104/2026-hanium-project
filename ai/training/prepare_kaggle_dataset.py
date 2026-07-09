"""
Kaggle 업로드용 서브셋 패키징 스크립트 — 로컬(이 컴퓨터)에서 실행.

matched_pairs.json의 앞 N개(stem 정렬 기준 — 기존 1차 학습 관례와 동일한 순서라
나중에 나머지 구간을 이어서 학습하고 싶을 때도 일관성이 유지됨)를 골라 이미지+라벨을
하나의 폴더로 모으고, 학습에 필요한 craft_model.py / gt_generator.py / craft_mlt_25k.pth도
함께 담는다. 이 폴더를 압축해서 Kaggle Dataset으로 업로드하면 kaggle_finetune.py가
그대로 사용한다.

사용법
------
    python prepare_kaggle_dataset.py [N]

    N 생략 시 기본 3,500장. Kaggle 무료 GPU(T4/P100) 기준 img_size=512, batch=4,
    10 epoch으로 대략 2~3시간 안에 끝나도록 잡은 값 — 정확한 시간은 GPU 종류에 따라
    달라지므로 kaggle_finetune.py 쪽에 시간 예산(max_minutes) 안전장치를 별도로 둠.
"""
import json
import os
import shutil
import sys

N_DEFAULT = 3500

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, "matched_pairs.json")
OUT_DIR = os.path.join(BASE_DIR, "kaggle_upload")
PRETRAINED_SRC = os.path.join(
    os.path.expanduser("~"), ".craft_text_detector", "weights", "craft_mlt_25k.pth"
)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest.sort(key=lambda e: e["stem"])
    subset = manifest[:n]
    print(f"전체 {len(manifest)}장 중 {len(subset)}장 선택 (stem 정렬 기준 앞부분)")

    img_dir = os.path.join(OUT_DIR, "images")
    lbl_dir = os.path.join(OUT_DIR, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    ok = err = 0
    for i, entry in enumerate(subset, 1):
        stem = entry["stem"]
        img_src, lbl_src = entry["image"], entry["label"]
        try:
            shutil.copy2(img_src, os.path.join(img_dir, stem + ".png"))
            shutil.copy2(lbl_src, os.path.join(lbl_dir, stem + ".json"))
            ok += 1
        except Exception as e:
            err += 1
            if err <= 10:
                print(f"  스킵: {stem} ({e})")
        if i % 500 == 0:
            print(f"  {i}/{len(subset)} 처리 중... (성공 {ok}, 실패 {err})")

    print(f"\n이미지/라벨 복사 완료: 성공 {ok}개, 실패 {err}개 -> {OUT_DIR}")

    # 학습 코드 + pretrained 가중치도 함께 패키징 (Kaggle에서 인터넷 없이도 돌아가도록)
    shutil.copy2(os.path.join(BASE_DIR, "craft_model.py"), OUT_DIR)
    shutil.copy2(os.path.join(BASE_DIR, "gt_generator.py"), OUT_DIR)
    print("craft_model.py / gt_generator.py 복사 완료")

    if os.path.exists(PRETRAINED_SRC):
        shutil.copy2(PRETRAINED_SRC, OUT_DIR)
        print("craft_mlt_25k.pth 복사 완료 (사전학습 가중치로 시작 — 강력 권장)")
    else:
        print(f"주의: pretrained 가중치를 찾지 못함 ({PRETRAINED_SRC})")
        print("      이 파일 없이 업로드하면 ImageNet backbone만으로 처음부터 학습되어")
        print("      2~3시간 예산으로는 수렴이 부족할 가능성이 큽니다.")

    total_bytes = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, files in os.walk(OUT_DIR) for f in files
    )
    print(f"\n총 용량: {total_bytes / 1e9:.2f} GB  ({OUT_DIR})")
    print("다음 단계: 이 폴더(kaggle_upload)를 압축해서 kaggle.com/datasets 에")
    print("새 Dataset으로 업로드하세요.")


if __name__ == "__main__":
    main()
