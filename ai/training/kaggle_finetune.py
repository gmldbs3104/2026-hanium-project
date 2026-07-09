"""
CRAFT Fine-tuning on AI Hub Korean Handwriting OCR Dataset — Kaggle Notebook용

Colab 버전(colab_finetune.py)과 차이점:
  - Google Drive 마운트/캐시 복사 단계 없음 — Kaggle Dataset은 이미 로컬 NVMe급
    속도로 마운트되므로 필요 없음 (Colab에서 가장 오래 걸리던 "Drive->로컬 복사"
    단계가 통째로 사라짐).
  - craft_model.py / gt_generator.py / craft_mlt_25k.pth / images / labels 전부
    하나의 Kaggle Dataset 안에 미리 패키징되어 있다고 가정 (prepare_kaggle_dataset.py
    로 로컬에서 만든 kaggle_upload/ 폴더를 그대로 압축해서 업로드한 것).
  - 시간 예산(max_minutes) 안전장치 추가 — epoch마다 경과 시간을 확인해서 예산을
    넘기면 체크포인트 저장 후 안전하게 학습을 종료함. Kaggle GPU 종류(T4/P100)에
    따라 속도가 달라 정확한 epoch 수를 미리 확정하기 어려우므로, "대략 몇 시간
    돌린다"는 목표는 epoch 수가 아니라 이 시간 예산으로 보장한다.

사용법 (Kaggle Notebook)
------------------------
  1. kaggle.com/datasets 에서 New Dataset -> prepare_kaggle_dataset.py가 만든
     kaggle_upload/ 폴더를 압축한 zip을 업로드
  2. 새 Notebook 생성 -> 우측 Add Input -> 방금 만든 Dataset 추가
  3. Notebook 설정(우측 패널) -> Accelerator: GPU T4 x2 또는 GPU P100,
     Internet: Off로 두어도 무방 (전부 로컬 Dataset에서 읽으므로 인터넷 불필요)
  4. 이 파일 전체를 노트북 셀 하나(또는 섹션별로 나눠서 여러 셀)에 붙여넣고 실행
     — 데이터 경로는 아래 [셀 1]이 /kaggle/input/ 밑을 직접 뒤져서 자동으로 찾으므로
     데이터셋 이름을 손으로 맞출 필요 없음 (zip 압축 방식에 따라 Kaggle이 폴더를
     한 겹 더 씌우는 경우가 흔해서, 경로를 하드코딩하는 대신 항상 이렇게 찾음)
  5. 학습 완료(또는 시간 예산 초과로 자동 종료) 후 우측 Output 탭에서
     /kaggle/working/craft_finetuned/craft_best.pth 를 다운로드
"""

# ======================================================================
# [셀 1] 경로 자동 탐색 + 설정
# ======================================================================
import glob
import os

# craft_model.py가 실제로 어디 있는지 /kaggle/input/ 전체를 뒤져서 찾는다.
# Kaggle이 zip을 풀 때 kaggle_upload/ 폴더가 한 겹 더 씌워지는 경우가 있어서
# (/kaggle/input/<데이터셋>/craft_model.py 대신 /kaggle/input/<데이터셋>/kaggle_upload/craft_model.py),
# 경로를 고정하지 않고 직접 찾는 편이 안전하다.
_candidates = glob.glob("/kaggle/input/**/craft_model.py", recursive=True)
if not _candidates:
    raise FileNotFoundError(
        "craft_model.py를 /kaggle/input/ 아래에서 찾지 못했습니다.\n"
        "  1) 우측 'Add Input'에서 Dataset을 추가했는지\n"
        "  2) kaggle_upload/ 폴더 안의 파일들이 zip에 제대로 담겼는지\n"
        "확인하세요. 디버깅용으로 아래를 실행해 실제 폴더 구조를 확인할 수 있습니다:\n"
        "    for root, dirs, files in os.walk('/kaggle/input'):\n"
        "        print(root, files)"
    )
DATA_ROOT = os.path.dirname(_candidates[0])
print("DATA_ROOT 자동 탐색됨:", DATA_ROOT)
print("DATA_ROOT 내용물:", os.listdir(DATA_ROOT))

# 이전 실행에서 만든 체크포인트를 Kaggle Dataset에 올려뒀으면 자동으로 찾아서
# 이어서 학습(resume)한다. craft_mlt_25k.pth(원본 pretrained)와는 파일명이 달라서
# 구분됨. 없으면 처음부터 학습.
#
# craft_best.pth든 craft_ep*.pth든 전부 후보로 찾고(파일명을 정확히 안 맞춰
# 올려도 되도록), 여러 Dataset에 체크포인트가 여러 개 붙어있어도(예: 이전
# 버전을 지우지 않고 새 Dataset을 추가로 붙인 경우) 안에 저장된 epoch 값을
# 직접 열어봐서 가장 진행된 것을 자동으로 고른다 — 어떤 파일이 뭐가 붙어있는지
# 사람이 정확히 정리해두지 않아도 항상 올바른 체크포인트로 이어서 학습되게 하기 위함.
import torch as _torch

_resume_candidates = (
    glob.glob("/kaggle/input/**/craft_best.pth", recursive=True)
    + glob.glob("/kaggle/input/**/craft_ep*.pth", recursive=True)
)
_resume_from = None
if _resume_candidates:
    def _ckpt_epoch(path):
        try:
            return _torch.load(path, map_location="cpu").get("epoch", -1)
        except Exception:
            return -1
    _epochs = {p: _ckpt_epoch(p) for p in _resume_candidates}
    _resume_from = max(_epochs, key=_epochs.get)
    print(f"체크포인트 후보 {len(_resume_candidates)}개 발견: {_epochs}")
    print(f"-> epoch이 가장 큰 것을 선택해 이어서 학습: {_resume_from}")
else:
    print("이전 체크포인트 없음 — 처음부터(craft_mlt_25k.pth 기준) 학습")

CFG = {
    "img_root"    : os.path.join(DATA_ROOT, "images"),
    "label_root"  : os.path.join(DATA_ROOT, "labels"),
    "pretrained"  : os.path.join(DATA_ROOT, "craft_mlt_25k.pth"),

    "img_size"    : 512,
    "batch_size"  : 4,
    "num_workers" : 3,         # 이진화+deskew(Canny/Hough) 전처리가 추가돼 CPU 부담이 늘어서 상향
    "lr"          : 1e-4,
    "epochs"      : 6,         # resume 여부와 무관하게 "이번 실행에서 몇 epoch 더 돌릴지"
                               # -- OHEM 피크 가중치 수정이 실제로 효과 있는지 짧게
                               # 먼저 확인하기 위해 이번엔 15가 아니라 6으로 축소.
                               # peak_quality가 epoch마다 오르는 게 확인되면 그때
                               # 더 늘려서 이어서 돌리면 됨.
    "warmup_ep"   : 0 if _resume_from else 2,  # resume 시엔 이미 backbone이 풀려있어 warmup 불필요

    "save_dir"    : "/kaggle/working/craft_finetuned",
    "save_every"  : 2,         # epoch 수가 늘어서 매 epoch 저장은 체크포인트 용량이 커짐 -> 2epoch마다

    "resume_from"  : _resume_from,
    "max_minutes"  : 360,      # 6시간 — Kaggle 세션 한도(9~12시간) 안에서 넉넉히 잡은 안전장치.
                               # 이진화+deskew 전처리 추가로 epoch당 시간이 이전 실행(3,500장
                               # 기준 6.4분/epoch)보다 더 걸릴 수 있어 정확한 예측이 어려움 —
                               # 실제로는 이 시간 예산이 끊어주기 전에 15 epoch가 먼저 끝날 수도,
                               # 못 끝내고 여기서 끊길 수도 있음. 어느 쪽이든 체크포인트는 보존됨.
}

os.makedirs(CFG["save_dir"], exist_ok=True)

for key in ("img_root", "label_root", "pretrained"):
    if not os.path.exists(CFG[key]):
        print(f"경고: {key} 경로가 없습니다 -> {CFG[key]}")

# ======================================================================
# [셀 2] craft_model.py / gt_generator.py 임포트
# ======================================================================
import sys
sys.path.insert(0, DATA_ROOT)

from craft_model  import CRAFT                              # noqa: E402
from gt_generator import generate_score_maps, parse_aihub_json  # noqa: E402

import json
import math
import random
import time

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from tqdm import tqdm

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print("Device:", DEVICE)
if not torch.cuda.is_available():
    print("경고: GPU가 안 잡혔습니다 — Notebook 설정에서 Accelerator를 GPU로 바꾸세요.")

# ======================================================================
# [셀 3] 데이터셋 클래스
# ======================================================================
# Kaggle에서는 kaggle_upload/images, kaggle_upload/labels에 이미 딱 필요한
# 서브셋만 들어있으므로(prepare_kaggle_dataset.py가 미리 골라놓음), Colab 버전과
# 달리 manifest로 다시 필터링할 필요 없이 폴더를 그대로 훑으면 됨.

class HandwritingDataset(Dataset):
    """
    AI Hub 손글씨 OCR 데이터셋 (Kaggle: img_root/label_root를 stem 기준으로 매칭).

    중요: 실제 서비스 추론 경로(ai/detection/craft_detector.py)는 원본 컬러 사진이 아니라
    "이진화 -> deskew -> distance transform"을 거친 이미지를 CRAFT에 입력한다
    (ai/preprocessing/image_preprocessor.py 파이프라인 + craft_detector.py의
    distance-transform 트릭). 학습을 원본 컬러 사진으로 하면 모델이 실제 서비스에서
    한 번도 본 적 없는 입력 분포를 받게 되어 탐지가 거의 안 나온다(직접 확인됨:
    같은 이미지가 원본 입력으로는 박스 65개, 이진화+distance-transform 입력으로는
    3개). 그래서 아래 __getitem__은 image_preprocessor.py와 동일한 이진화/deskew
    파라미터를 그대로 재현해서 학습·추론의 입력 도메인을 맞춘다.
    """

    def __init__(self, img_root, label_root, img_size=512, augment=True):
        self.img_size = img_size
        self.augment  = augment

        img_map = {
            os.path.splitext(os.path.basename(p))[0]: p
            for p in glob.glob(os.path.join(img_root, "*.png"))
        }
        label_map = {
            os.path.splitext(os.path.basename(p))[0]: p
            for p in glob.glob(os.path.join(label_root, "*.json"))
        }
        matched_stems = sorted(img_map.keys() & label_map.keys())
        self.pairs = [(img_map[s], label_map[s]) for s in matched_stems]
        print(f"  데이터셋: {len(self.pairs)}쌍 로드됨 "
              f"(img={len(img_map)}, label={len(label_map)})")

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        img_path, lbl_path = self.pairs[idx]

        img = cv2.imread(img_path)  # BGR
        if img is None:
            return self.__getitem__((idx + 1) % len(self))

        boxes = parse_aihub_json(lbl_path)  # List[ndarray (4,2)] — 글자 단위로 이미 분할됨

        # image_preprocessor.py와 동일: grayscale -> blur -> adaptive threshold -> deskew
        binary, boxes = self._binarize_and_deskew(img, boxes)
        # craft_detector.py와 동일: distance transform -> RGB
        img = self._to_dist_transform_rgb(binary)

        img, boxes, ratio = self._resize(img, boxes)
        img_h, img_w = img.shape[:2]

        if self.augment:
            img, boxes = self._augment(img, boxes)

        region_map, affinity_map = generate_score_maps(img_h, img_w, boxes, output_ratio=0.5)

        img_t = torch.from_numpy(img.transpose(2, 0, 1)).float() / 255.0
        img_t = transforms.Normalize([0.485, 0.456, 0.406],
                                      [0.229, 0.224, 0.225])(img_t)
        region_t   = torch.from_numpy(region_map).unsqueeze(0)
        affinity_t = torch.from_numpy(affinity_map).unsqueeze(0)

        return img_t, region_t, affinity_t

    # ------------------------------------------------------------------
    # image_preprocessor.py / craft_detector.py와 동일한 전처리 재현
    # ------------------------------------------------------------------

    def _binarize_and_deskew(self, bgr, boxes):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
            blockSize=15, C=5,
        )

        angle = self._detect_skew_angle(binary)
        if abs(angle) < 0.5 or abs(angle) > 45.0:
            return binary, boxes

        h, w = binary.shape[:2]
        center = (w / 2.0, h / 2.0)
        matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
        cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)
        matrix[0, 2] += (new_w / 2.0) - center[0]
        matrix[1, 2] += (new_h / 2.0) - center[1]
        rotated = cv2.warpAffine(binary, matrix, (new_w, new_h), borderValue=0)

        new_boxes = []
        for box in boxes:
            pts = np.column_stack([box, np.ones(len(box), dtype=np.float32)])
            new_boxes.append((pts @ matrix.T).astype(np.float32))
        return rotated, new_boxes

    def _detect_skew_angle(self, binary):
        h, w = binary.shape[:2]
        edges = cv2.Canny(binary, 50, 150, apertureSize=3)
        min_len = max(100, int(w * 0.15))
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 80,
                                minLineLength=min_len, maxLineGap=10)
        if lines is None:
            return 0.0
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line.flatten()[:4]
            if x2 - x1 == 0:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if -6.0 < angle < 6.0:
                angles.append(angle)
        if len(angles) < 5:
            return 0.0
        return float(np.median(angles))

    def _to_dist_transform_rgb(self, binary):
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        return cv2.cvtColor(dist_norm, cv2.COLOR_GRAY2RGB)

    def _resize(self, img, boxes):
        h, w = img.shape[:2]
        ratio = self.img_size / max(h, w)
        new_w, new_h = int(w * ratio), int(h * ratio)
        pad_w = math.ceil(new_w / 32) * 32
        pad_h = math.ceil(new_h / 32) * 32

        resized = cv2.resize(img, (new_w, new_h))
        canvas  = np.zeros((pad_h, pad_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized

        scaled_boxes = [b * ratio for b in boxes]
        return canvas, scaled_boxes, ratio

    def _augment(self, img, boxes):
        if random.random() < 0.3:
            img_w = img.shape[1]
            img   = img[:, ::-1, :].copy()
            new_boxes = []
            for b in boxes:
                nb = b.copy()
                nb[:, 0] = img_w - nb[:, 0]
                new_boxes.append(nb[[1, 0, 3, 2]])
            boxes = new_boxes

        if random.random() < 0.5:
            alpha = random.uniform(0.8, 1.2)
            beta  = random.randint(-20, 20)
            img   = np.clip(img.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)

        return img, boxes


def collate_fn(batch):
    """
    배치 내 최대 크기로 패딩.
    주의: region/affinity map은 원본 이미지의 1/2 해상도이므로, 이미지와 같은
    (max_h, max_w)로 패딩하면 절반 크기 GT를 억지로 2배로 늘려 패딩하는 셈이 되어
    예측(원래부터 1/2 해상도)과 정렬이 완전히 어긋난다. 반드시 max_h/2, max_w/2로
    따로 패딩해야 한다.
    """
    imgs, regions, affinities = zip(*batch)
    max_h = max(x.shape[1] for x in imgs)
    max_w = max(x.shape[2] for x in imgs)
    max_h = math.ceil(max_h / 32) * 32
    max_w = math.ceil(max_w / 32) * 32

    def pad(t, target_h, target_w, val=0.0):
        _, h, w = t.shape
        return F.pad(t, (0, target_w - w, 0, target_h - h), value=val)

    imgs       = torch.stack([pad(x, max_h, max_w) for x in imgs])
    regions    = torch.stack([pad(x, max_h // 2, max_w // 2) for x in regions])
    affinities = torch.stack([pad(x, max_h // 2, max_w // 2) for x in affinities])
    return imgs, regions, affinities

# ======================================================================
# [셀 4] 손실 함수 — OHEM 적용 (score map collapse 방지)
# ======================================================================

class CRAFTLoss(nn.Module):
    """
    OHEM(Online Hard Example Mining) 적용 Region + Affinity MSE Loss.
    GT의 99%+가 배경(0)인 극단적 클래스 불균형 때문에 순수 MSE는 "전부 0에 가깝게
    출력"만으로 loss를 낮출 수 있어 학습이 collapse한다. OHEM으로 양성 픽셀 전부 +
    가장 틀린 음성 픽셀 top-k만 loss에 반영해 이를 방지한다.
    """
    def __init__(self, lambda_affinity: float = 1.0,
                 ohem_ratio: int = 3, ohem_min_neg: int = 100):
        super().__init__()
        self.lambda_a = lambda_affinity
        self.ohem_ratio = ohem_ratio
        self.ohem_min_neg = ohem_min_neg

    def _ohem_mse(self, pred, gt):
        loss = (pred - gt) ** 2
        total = 0.0
        B = pred.shape[0]
        for b in range(B):
            gt_b, loss_b = gt[b], loss[b]
            pos_mask = gt_b > 0.1
            num_pos  = int(pos_mask.sum().item())
            pos_loss = loss_b[pos_mask]

            if num_pos > 0:
                # Gaussian 특성상 "양성"(GT>0.1)으로 잡히는 픽셀 대부분은 피크가
                # 아니라 가장자리(낮은 값)라, 가중치 없이 평균내면 모델이 그 다수
                # 가장자리에 맞춰 전반적으로 낮게(더 안전하게) 예측하는 쪽으로
                # 수렴하기 쉽다. 실측 결과 이 상태로 계속 학습하니 loss는 계속
                # 낮아지는데 실제 탐지(피크가 threshold를 넘는지)는 오히려
                # 나빠지는 현상을 확인함 — epoch 9→11→13 갈수록 탐지량 지속 감소.
                # 피크(GT값이 클수록)에 더 큰 가중치를 줘서 이 편향을 상쇄한다.
                # 가중치 평균이 1이 되도록 정규화해 pos/neg 전체 균형은 유지하고
                # 양성 그룹 "내부" 분포만 피크 쪽으로 재배분한다.
                peak_weight = gt_b[pos_mask] ** 2
                peak_weight = peak_weight * (num_pos / peak_weight.sum().clamp(min=1e-6))
                pos_loss = pos_loss * peak_weight

            neg_loss = loss_b[~pos_mask]
            k = min(max(self.ohem_min_neg, self.ohem_ratio * max(num_pos, 1)), neg_loss.numel())
            hard_neg_loss, _ = torch.topk(neg_loss, k)

            sample_loss = (torch.cat([pos_loss, hard_neg_loss]).mean()
                           if num_pos > 0 else hard_neg_loss.mean())
            total = total + sample_loss
        return total / B

    def forward(self, pred_region, pred_affinity, gt_region, gt_affinity):
        if pred_region.shape != gt_region.shape:
            pred_region   = F.interpolate(pred_region.unsqueeze(1),
                                          size=gt_region.shape[-2:],
                                          mode='bilinear', align_corners=False).squeeze(1)
            pred_affinity = F.interpolate(pred_affinity.unsqueeze(1),
                                          size=gt_affinity.shape[-2:],
                                          mode='bilinear', align_corners=False).squeeze(1)

        gt_region   = gt_region.squeeze(1)
        gt_affinity = gt_affinity.squeeze(1)

        loss_r = self._ohem_mse(pred_region,   gt_region)
        loss_a = self._ohem_mse(pred_affinity, gt_affinity)
        return loss_r + self.lambda_a * loss_a, loss_r.item(), loss_a.item()

# ======================================================================
# [셀 5] 학습 루프
# ======================================================================

def train_one_epoch(model, loader, optimizer, criterion, device, epoch):
    model.train()
    total_loss = total_r = total_a = 0.0

    pbar = tqdm(loader, desc=f"Epoch {epoch}", leave=False)
    for imgs, regions, affinities in pbar:
        imgs       = imgs.to(device)
        regions    = regions.to(device)
        affinities = affinities.to(device)

        optimizer.zero_grad()
        pred_r, pred_a = model(imgs)
        loss, lr, la   = criterion(pred_r, pred_a, regions, affinities)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
        optimizer.step()

        total_loss += loss.item()
        total_r    += lr
        total_a    += la
        pbar.set_postfix(loss=f"{loss.item():.4f}")

    n = len(loader)
    return total_loss / n, total_r / n, total_a / n


@torch.no_grad()
def validate(model, loader, criterion, device):
    """
    val_loss와 함께 peak_quality(GT 피크 위치에서 모델이 실제로 얼마나 높게
    반응하는지, GT>0.7인 픽셀들의 평균 예측값)를 같이 계산해서 반환한다.

    val_loss가 낮아지는 것과 실제 탐지 품질이 같이 좋아지는 게 아니라는 걸 실측으로
    확인함(epoch가 진행될수록 val_loss는 계속 개선됐지만 실제 탐지 개수는 꾸준히
    감소) — OHEM이 양성 픽셀 대부분을 차지하는 Gaussian 가장자리(낮은 값)에 맞춰
    모델이 전반적으로 낮게 예측하는 쪽으로 수렴했기 때문으로 추정. peak_quality는
    "글자 중심에서 확신 있게 반응하는지"를 직접 재기 때문에 val_loss보다 실제
    탐지 품질과 더 직접적으로 연결된다고 판단해 체크포인트 선택 기준으로 사용한다.
    """
    model.eval()
    total_loss = 0.0
    peak_sum, peak_count = 0.0, 0
    for imgs, regions, affinities in loader:
        imgs, regions, affinities = (x.to(device) for x in (imgs, regions, affinities))
        pred_r, pred_a = model(imgs)
        loss, _, _     = criterion(pred_r, pred_a, regions, affinities)
        total_loss    += loss.item()

        pred_r_matched = pred_r
        gt_r = regions.squeeze(1)
        if pred_r_matched.shape != gt_r.shape:
            pred_r_matched = F.interpolate(pred_r_matched.unsqueeze(1), size=gt_r.shape[-2:],
                                           mode='bilinear', align_corners=False).squeeze(1)
        peak_mask = gt_r > 0.7
        if peak_mask.any():
            peak_sum   += pred_r_matched[peak_mask].sum().item()
            peak_count += int(peak_mask.sum().item())

    val_loss = total_loss / len(loader)
    peak_quality = peak_sum / peak_count if peak_count > 0 else 0.0
    return val_loss, peak_quality

# ======================================================================
# [셀 6] 메인 학습 — 시간 예산(max_minutes) 안전장치 포함
# ======================================================================

def main():
    start_time = time.time()
    max_seconds = CFG.get("max_minutes", 0) * 60

    print("=== 데이터셋 로드 ===")
    all_pairs = HandwritingDataset(
        img_root=CFG["img_root"], label_root=CFG["label_root"],
        img_size=CFG["img_size"], augment=True,
    )

    val_size = max(50, int(len(all_pairs) * 0.1))
    train_ds = torch.utils.data.Subset(all_pairs, range(val_size, len(all_pairs)))
    val_ds   = torch.utils.data.Subset(all_pairs, range(val_size))

    train_loader = DataLoader(train_ds, batch_size=CFG["batch_size"],
                              shuffle=True,  num_workers=CFG["num_workers"],
                              collate_fn=collate_fn, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=CFG["batch_size"],
                              shuffle=False, num_workers=CFG["num_workers"],
                              collate_fn=collate_fn, pin_memory=True)

    print(f"학습: {len(train_ds)}장  검증: {len(val_ds)}장")
    print(f"시간 예산: {CFG['max_minutes']}분")

    resuming = bool(CFG.get("resume_from"))
    # pretrained_backbone=True는 torchvision이 ImageNet VGG16-BN 가중치를 인터넷에서
    # 내려받으려 시도한다 (Kaggle Internet:Off 환경에서 DNS 실패로 크래시). 아래에서
    # craft_mlt_25k.pth를 바로 이어서 로드하면 그 안에 이미 학습된 backbone까지 통째로
    # 들어있어 ImageNet 다운로드 자체가 불필요 -> 항상 False로 생성하고 인터넷 의존 제거.
    model = CRAFT(pretrained_backbone=False,
                  freeze_backbone=(not resuming)).to(DEVICE)

    start_epoch = 1
    best_val    = float('inf')
    best_peak   = -float('inf')
    history     = []

    if resuming:
        ckpt = torch.load(CFG["resume_from"], map_location=DEVICE)
        model.load_state_dict(ckpt["model_state"])
        start_epoch = ckpt["epoch"] + 1
        best_val    = ckpt.get("val_loss", float('inf'))
        best_peak   = ckpt.get("peak_quality", -float('inf'))
        history     = ckpt.get("history", [])
        print(f"체크포인트 재개: epoch {ckpt['epoch']} -> {start_epoch}부터")
    elif os.path.exists(CFG["pretrained"]):
        model.load_pretrained_craft(CFG["pretrained"])
    else:
        print("경고: 사전학습 가중치(craft_mlt_25k.pth)를 못 찾아 완전 랜덤 초기화로 "
              "시작합니다 — 이 시간 예산으로는 수렴이 크게 부족할 가능성이 높습니다.")

    criterion = CRAFTLoss(lambda_affinity=1.0)
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=CFG["lr"], weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=CFG["epochs"], eta_min=CFG["lr"] * 0.01,
    )

    end_epoch = start_epoch + CFG["epochs"] - 1
    stopped_early = False

    for epoch in range(start_epoch, end_epoch + 1):
        local_ep = epoch - start_epoch + 1

        if CFG["warmup_ep"] > 0 and local_ep == CFG["warmup_ep"] + 1:
            for p in model.parameters():
                p.requires_grad = True
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=CFG["lr"] * 0.1, weight_decay=1e-4,
            )
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=CFG["epochs"] - CFG["warmup_ep"],
                eta_min=CFG["lr"] * 0.001,
            )
            print(f"  [Epoch {epoch}] backbone 동결 해제")

        tr_loss, tr_r, tr_a = train_one_epoch(
            model, train_loader, optimizer, criterion, DEVICE, epoch)
        val_loss, peak_quality = validate(model, val_loader, criterion, DEVICE)
        scheduler.step()

        elapsed_min = (time.time() - start_time) / 60
        # val_loss가 아니라 peak_quality(GT 피크 위치에서의 평균 예측값, 높을수록
        # 좋음)로 "best"를 결정한다 — val_loss는 계속 낮아지는데 실제 탐지는
        # 나빠지는 현상을 실측했기 때문(validate() docstring 참고).
        is_best = peak_quality > best_peak
        history.append({
            "epoch": epoch, "train": tr_loss, "val": val_loss,
            "peak_quality": round(peak_quality, 4),
            "region": tr_r, "affinity": tr_a, "elapsed_min": round(elapsed_min, 1),
        })

        print(f"Epoch {epoch:3d} ({local_ep}/{CFG['epochs']}) "
              f"| train={tr_loss:.4f} (r={tr_r:.4f} a={tr_a:.4f}) "
              f"| val={val_loss:.4f} | peak_quality={peak_quality:.4f} | 경과 {elapsed_min:.1f}분"
              + (" <- best" if is_best else ""))

        if is_best:
            best_val  = val_loss
            best_peak = peak_quality
            torch.save({
                "epoch": epoch, "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "val_loss": best_val, "peak_quality": best_peak,
                "history": history, "cfg": CFG,
            }, os.path.join(CFG["save_dir"], "craft_best.pth"))

        if local_ep % CFG["save_every"] == 0:
            torch.save({
                "epoch": epoch, "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "history": history, "cfg": CFG,
            }, os.path.join(CFG["save_dir"], f"craft_ep{epoch:03d}.pth"))

        if max_seconds and (time.time() - start_time) > max_seconds:
            print(f"\n시간 예산({CFG['max_minutes']}분) 초과 — 학습을 여기서 종료합니다. "
                  f"마지막 체크포인트는 이미 저장되어 있습니다.")
            stopped_early = True
            break

    print(f"\n학습 {'조기 ' if stopped_early else ''}종료. "
          f"최적 peak_quality={best_peak:.4f} (그때 val_loss={best_val:.4f})")
    print(f"최적 가중치: {CFG['save_dir']}/craft_best.pth")
    return history


if __name__ == "__main__":
    history = main()

# ======================================================================
# [셀 7] 학습 완료 후 — 프로젝트에 적용하는 방법
# ======================================================================
"""
1. 우측 Output 탭 (또는 /kaggle/working/craft_finetuned/) 에서 craft_best.pth 다운로드

2. {"model_state": ...} 래핑을 벗겨서 프로젝트에 저장:

    import torch
    ckpt = torch.load('craft_best.pth', map_location='cpu')
    torch.save(ckpt['model_state'], 'craft_finetuned_raw.pth')

   이 craft_finetuned_raw.pth를 로컬 프로젝트의 ai/models/ 에 넣으면
   (craft_model.py가 craft_text_detector 공식 구조와 키가 동일하므로)
   ai/detection/craft_detector.py가 별도 코드 수정 없이 자동으로 로드함.

3. 로컬에서 검증:
     cd ai
     python debug_gt.py ckpt models/craft_finetuned_raw.pth
   (collapse 여부부터 확인 — region/affinity min/max/mean이 상수면 실패)

     python -c "from detection.craft_detector import CraftDetector; CraftDetector()"
   (에러 없이 뜨는지 + test_images/ 7장 재탐지 결과 확인)
"""
