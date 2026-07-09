"""
CRAFT Fine-tuning on AI Hub Korean Handwriting OCR Dataset
Google Colab (T4/A100 GPU) 실행용

사용법:
  1. Google Drive에 다음 구조로 데이터 업로드:
       MyDrive/aihub_handwriting/
         ├── 원천데이터/   (PNG, 하위 폴더 포함)
         ├── 라벨링데이터/ (JSON, 하위 폴더 포함)
         └── matched_pairs.json  (ai/training/matched_pairs.json 업로드)

  2. 학습 스크립트 3개 업로드 (같은 폴더):
       craft_model.py, gt_generator.py, colab_finetune.py

  3. Colab에서 셀 단위로 순서대로 실행

실행 전략:
  1차 실행: 아래 CFG 그대로 → 3,000샘플 × 15 epoch (약 4~5시간)
  2차 실행: 아래 RESUME_CFG 주석 해제 → 나머지 데이터로 이어서 학습
"""

# ======================================================================
# [셀 1] 패키지 설치 (Colab에서 한 번만 실행)
# ======================================================================
# !pip install -q opencv-python-headless tqdm
# (torch/torchvision은 Colab에 이미 설치됨)

# ======================================================================
# [셀 2] Google Drive 마운트
# ======================================================================
# from google.colab import drive
# drive.mount('/content/drive')

# ======================================================================
# [셀 3] 경로 설정 — 본인 Drive 구조에 맞게 수정
# ======================================================================
import os

# ──────────────────────────────────────────────────────────────────────
# 1차 실행 (처음 시작 — 약 4~5시간)
# manifest를 stem 순 정렬 후 [0:5000] 사용 → 2차와 비중복
# 총 시간: 캐시 복사 ~65분 + 학습 ~3시간
# ──────────────────────────────────────────────────────────────────────
CFG = {
    # Drive 경로 (원본 데이터)
    "manifest_path"    : "/content/drive/MyDrive/aihub_handwriting/matched_pairs.json",
    "drive_img_root"   : "/content/drive/MyDrive/aihub_handwriting/원천데이터",
    "drive_label_root" : "/content/drive/MyDrive/aihub_handwriting/라벨링데이터",

    # 로컬 캐시 경로 — Drive보다 10배 빠름 (세션 종료 시 삭제됨)
    "cache_dir"        : "/content/aihub_cache",

    # 학습 설정
    "img_size"    : 512,
    "batch_size"  : 4,
    "num_workers" : 2,
    "lr"          : 1e-4,
    "epochs"      : 10,
    "warmup_ep"   : 2,
    "max_samples" : 5_000,    # stem 정렬 후 [sample_start : sample_start+max_samples]
    "sample_start" : 0,       # 1차: 0~4999번 데이터

    # 저장
    "save_dir"    : "/content/drive/MyDrive/craft_finetuned",
    "save_every"  : 2,

    "pretrained"   : "/content/craft_mlt_25k.pth",
    "resume_from"  : None,
}

os.makedirs(CFG["save_dir"],  exist_ok=True)
os.makedirs(CFG["cache_dir"], exist_ok=True)

# ──────────────────────────────────────────────────────────────────────
# 2차 실행 (시간 생길 때 — 나머지 전체 ~10,314장으로 추가 학습)
# 1차와 완전 비중복 (stem 정렬 기준 5000번 이후 전부)
# 총 시간: 캐시 복사 ~2시간 + 학습 ~3시간 = 약 5시간
# ──────────────────────────────────────────────────────────────────────
# RESUME_CFG = {
#     **{k: v for k, v in CFG.items()},
#
#     "resume_from"   : "/content/drive/MyDrive/craft_finetuned/craft_best.pth",
#     "sample_start"  : 5_000,   # 1차(0~4999) 이후 나머지 전부 (~10,314장)
#     "max_samples"   : None,    # None = sample_start부터 끝까지 전부 사용
#     "epochs"        : 5,       # 10,314장 기준 epoch당 ~35분 → 5 epoch ≈ 3시간
#     "lr"            : 3e-5,
#     "warmup_ep"     : 0,
#     "save_every"    : 1,       # epoch당 저장 (epoch이 길어서)
# }
# CFG = RESUME_CFG   # ← 이 줄 활성화

# ======================================================================
# [셀 4] 사전학습 가중치 확인
# VGG16 ImageNet 가중치로 backbone 초기화 (craft_model.py 내부에서 자동 처리)
# craft_mlt_25k.pth가 있으면 CRAFT 전체 가중치 사용, 없으면 ImageNet backbone만 사용
# ======================================================================
import numpy as np

if os.path.exists(CFG["pretrained"]):
    print("CRAFT 사전학습 가중치 사용:", CFG["pretrained"])
else:
    print("CRAFT 가중치 없음 → VGG16 ImageNet backbone으로 시작 (정상)")
    CFG["pretrained"] = ""   # main()에서 빈 경로는 자동으로 건너뜀

# ======================================================================
# [셀 5] 임포트
# ======================================================================
import sys, glob, json, random, math
import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from tqdm import tqdm

# 이 스크립트와 같은 폴더에 craft_model.py, gt_generator.py가 있어야 함
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '/content')

from craft_model   import CRAFT
from gt_generator  import generate_score_maps, parse_aihub_json

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print("Device:", DEVICE)

# ======================================================================
# [셀 6] Drive → 로컬 캐시 복사 (학습 전 한 번만 실행)
# Drive I/O 병목을 제거해 학습 속도 3~5배 향상
# ======================================================================

def setup_local_cache(cfg: dict) -> tuple:
    """
    manifest에서 max_samples개를 무작위 선택 →
    Drive에서 /content 로컬로 PNG + JSON 복사.

    Returns
    -------
    (local_img_root, local_label_root) : 복사된 로컬 경로
    """
    import shutil
    manifest_path = cfg["manifest_path"]
    drive_img_root   = cfg["drive_img_root"]
    drive_label_root = cfg["drive_label_root"]
    cache_dir        = cfg["cache_dir"]
    max_samples      = cfg["max_samples"]

    local_img_dir   = os.path.join(cache_dir, "images")
    local_label_dir = os.path.join(cache_dir, "labels")
    os.makedirs(local_img_dir,   exist_ok=True)
    os.makedirs(local_label_dir, exist_ok=True)

    # 이미 복사된 경우 건너뜀 (subset 계산 전이라 여기서 max_samples만 확인)
    existing = len(glob.glob(os.path.join(local_img_dir, "*.png")))
    sample_start = cfg.get("sample_start", 0)
    if max_samples is not None and existing >= max_samples:
        print(f"  로컬 캐시 이미 존재 ({existing}개, start={sample_start}) — 복사 생략")
        return local_img_dir, local_label_dir

    # manifest stem 목록 — stem 정렬로 실행마다 동일한 순서 보장
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest.sort(key=lambda e: e["stem"])
    sample_start = cfg.get("sample_start", 0)
    if max_samples is not None:
        subset = manifest[sample_start : sample_start + max_samples]
    else:
        subset = manifest[sample_start:]   # sample_start부터 끝까지 전부

    # Drive에서 stem 기반으로 파일 탐색
    print(f"  Drive에서 stem 인덱스 구축 중...")
    img_map, label_map = {}, {}
    for p in glob.glob(os.path.join(drive_img_root,   "**", "*.png"),  recursive=True):
        img_map[os.path.splitext(os.path.basename(p))[0]] = p
    for p in glob.glob(os.path.join(drive_label_root, "**", "*.json"), recursive=True):
        label_map[os.path.splitext(os.path.basename(p))[0]] = p

    ok = err = 0
    print(f"  [{sample_start}~{sample_start+len(subset)-1}번] {len(subset)}개 로컬 복사 시작...")
    for entry in tqdm(subset, desc="캐시 복사"):
        stem = entry["stem"]
        if stem not in img_map or stem not in label_map:
            err += 1
            continue
        try:
            shutil.copy2(img_map[stem],   os.path.join(local_img_dir,   stem + ".png"))
            shutil.copy2(label_map[stem], os.path.join(local_label_dir, stem + ".json"))
            ok += 1
        except Exception as e:
            err += 1

    print(f"  복사 완료: 성공 {ok}개, 실패 {err}개")
    return local_img_dir, local_label_dir

# ======================================================================
# [셀 7] 데이터셋 클래스
# ======================================================================

class HandwritingDataset(Dataset):
    """AI Hub 손글씨 OCR 데이터셋 (matched_pairs.json 기반)."""

    def __init__(self, manifest_path, img_root, label_root, img_size=512,
                 max_samples=None, augment=True):
        self.img_size = img_size
        self.augment  = augment

        # manifest에서 stem 목록 추출 (Windows 절대경로는 무시, stem만 사용)
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        valid_stems = {entry['stem'] for entry in manifest}
        print(f"  manifest stems: {len(valid_stems)}")

        # Colab 경로에서 stem으로 파일 찾기
        img_map = {}
        for p in glob.glob(os.path.join(img_root, '**', '*.png'), recursive=True):
            stem = os.path.splitext(os.path.basename(p))[0]
            if stem in valid_stems:
                img_map[stem] = p

        label_map = {}
        for p in glob.glob(os.path.join(label_root, '**', '*.json'), recursive=True):
            stem = os.path.splitext(os.path.basename(p))[0]
            if stem in valid_stems:
                label_map[stem] = p

        matched_stems = sorted(img_map.keys() & label_map.keys())
        pairs = [(img_map[s], label_map[s]) for s in matched_stems]

        if max_samples:
            random.shuffle(pairs)
            pairs = pairs[:max_samples]

        self.pairs = pairs
        print(f"  데이터셋: {len(self.pairs)}쌍 로드됨 "
              f"(img_found={len(img_map)}, label_found={len(label_map)})")

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        img_path, lbl_path = self.pairs[idx]

        # 이미지 로드
        img = cv2.imread(img_path)  # BGR
        if img is None:
            # 손상 파일 → 더미 반환
            return self.__getitem__((idx + 1) % len(self))

        # 라벨 파싱
        boxes = parse_aihub_json(lbl_path)  # List[ndarray (4,2)]

        # 실제 서비스 추론 경로(image_preprocessor.py + craft_detector.py)와 동일하게
        # 이진화 -> deskew -> distance transform을 거친 뒤 학습. 원본 컬러 사진을 그대로
        # 학습에 쓰면 모델이 실제 서비스 입력 분포를 한 번도 못 보게 되어 탐지가 거의
        # 안 나온다 (같은 이미지로 실측: 원본 입력 65박스 vs 이진화+distance-transform
        # 입력 3박스).
        binary, boxes = self._binarize_and_deskew(img, boxes)
        img = self._to_dist_transform_rgb(binary)

        # 리사이즈 (장변 = img_size, 비율 유지, 32 배수 패딩)
        img, boxes, ratio = self._resize(img, boxes)
        img_h, img_w = img.shape[:2]

        # 오그멘테이션
        if self.augment:
            img, boxes = self._augment(img, boxes)

        # GT score map 생성
        region_map, affinity_map = generate_score_maps(img_h, img_w, boxes, output_ratio=0.5)

        # 텐서 변환
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
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        # 32 배수로 패딩
        pad_w = math.ceil(new_w / 32) * 32
        pad_h = math.ceil(new_h / 32) * 32

        resized = cv2.resize(img, (new_w, new_h))
        canvas  = np.zeros((pad_h, pad_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized

        scaled_boxes = [b * ratio for b in boxes]
        return canvas, scaled_boxes, ratio

    def _augment(self, img, boxes):
        """간단한 오그멘테이션: 좌우 반전, 밝기/대비 지터."""
        # 좌우 반전
        if random.random() < 0.3:
            img_w = img.shape[1]
            img   = img[:, ::-1, :].copy()
            new_boxes = []
            for b in boxes:
                nb = b.copy()
                nb[:, 0] = img_w - nb[:, 0]
                new_boxes.append(nb[[1, 0, 3, 2]])  # 좌우 순서 교정
            boxes = new_boxes

        # 밝기/대비 지터
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
# [셀 8] 손실 함수
# ======================================================================

class CRAFTLoss(nn.Module):
    """
    OHEM(Online Hard Example Mining) 적용 Region + Affinity MSE Loss.

    GT의 99%+가 배경(0)인 극단적 클래스 불균형 때문에 순수 MSE는 "이미지 내용과
    무관하게 전부 0에 가까운 값 출력"만으로 loss를 충분히 낮출 수 있어 학습이
    collapse한다(실제로 40 epoch 학습 결과 전 픽셀이 상수값으로 수렴하는 현상 확인됨).
    OHEM으로 양성 픽셀 전부 + 가장 틀린 음성 픽셀 top-k만 loss에 반영해 이를 방지한다.
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
                # 가장자리에 맞춰 전반적으로 낮게 예측하는 쪽으로 수렴하기 쉽다.
                # (kaggle_finetune.py 실측: val_loss는 계속 낮아지는데 실제 탐지는
                # epoch가 갈수록 감소하는 현상 확인) 피크(GT값이 클수록)에 더 큰
                # 가중치를 줘서 이 편향을 상쇄한다. 가중치 평균 1로 정규화해 pos/neg
                # 전체 균형은 유지하고 양성 그룹 "내부" 분포만 재배분한다.
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
        # 예측 크기를 GT 크기에 맞춤 (GT는 이미 1/2)
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
# [셀 9] 학습 루프
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
    model.eval()
    total_loss = 0.0
    for imgs, regions, affinities in loader:
        imgs, regions, affinities = (x.to(device) for x in (imgs, regions, affinities))
        pred_r, pred_a = model(imgs)
        loss, _, _     = criterion(pred_r, pred_a, regions, affinities)
        total_loss    += loss.item()
    return total_loss / len(loader)

# ======================================================================
# [셀 10] 메인 학습
# ======================================================================

def main():
    # ── 로컬 캐시 구성 (Drive I/O 병목 제거) ──────────────────────────
    print("=== 1단계: 로컬 캐시 구성 ===")
    local_img_root, local_label_root = setup_local_cache(CFG)

    # ── 데이터셋 ──────────────────────────────────────────────────────
    print("\n=== 2단계: 데이터셋 로드 ===")
    all_pairs = HandwritingDataset(
        manifest_path = CFG["manifest_path"],
        img_root      = local_img_root,
        label_root    = local_label_root,
        img_size      = CFG["img_size"],
        max_samples   = CFG["max_samples"],
        augment       = True,
    )

    val_size  = max(50, int(len(all_pairs) * 0.1))
    train_ds  = torch.utils.data.Subset(all_pairs, range(val_size, len(all_pairs)))
    val_ds    = torch.utils.data.Subset(all_pairs, range(val_size))

    train_loader = DataLoader(train_ds, batch_size=CFG["batch_size"],
                              shuffle=True,  num_workers=CFG["num_workers"],
                              collate_fn=collate_fn, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=CFG["batch_size"],
                              shuffle=False, num_workers=CFG["num_workers"],
                              collate_fn=collate_fn, pin_memory=True)

    print(f"\n=== 3단계: 학습 시작 ===")
    print(f"학습: {len(train_ds)}장  검증: {len(val_ds)}장")

    # ── 모델 ──────────────────────────────────────────────────────────
    resuming = bool(CFG.get("resume_from"))
    # resume 시 backbone 동결 없이 전체 파라미터 학습
    model = CRAFT(pretrained_backbone=(not resuming),
                  freeze_backbone=(not resuming)).to(DEVICE)

    start_epoch = 1
    best_val    = float('inf')
    history     = []

    if resuming:
        ckpt_path = CFG["resume_from"]
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(f"체크포인트 없음: {ckpt_path}")
        ckpt = torch.load(ckpt_path, map_location=DEVICE)
        model.load_state_dict(ckpt["model_state"])
        start_epoch = ckpt["epoch"] + 1
        best_val    = ckpt.get("val_loss", float('inf'))
        history     = ckpt.get("history", [])
        print(f"  체크포인트 로드: {ckpt_path}")
        print(f"  재개 지점: epoch {ckpt['epoch']}  val_loss={best_val:.4f}")
        print(f"  {start_epoch} epoch부터 추가 학습 시작")
    else:
        if os.path.exists(CFG["pretrained"]):
            model.load_pretrained_craft(CFG["pretrained"])
        else:
            print("  사전학습 가중치 없음 — 처음부터 학습")

    criterion = CRAFTLoss(lambda_affinity=1.0)

    # ── 옵티마이저 ────────────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=CFG["lr"], weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=CFG["epochs"], eta_min=CFG["lr"] * 0.01,
    )

    end_epoch = start_epoch + CFG["epochs"] - 1

    for epoch in range(start_epoch, end_epoch + 1):
        local_ep = epoch - start_epoch + 1  # 이번 세션 기준 epoch 번호

        # warmup: 1차 학습 전용 (resume 시 warmup_ep=0 으로 설정됨)
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
        val_loss = validate(model, val_loader, criterion, DEVICE)
        scheduler.step()

        is_best = val_loss < best_val
        history.append({
            "epoch": epoch, "train": tr_loss, "val": val_loss,
            "region": tr_r, "affinity": tr_a,
        })

        print(f"Epoch {epoch:3d} ({local_ep}/{CFG['epochs']}) "
              f"| train={tr_loss:.4f} (r={tr_r:.4f} a={tr_a:.4f}) "
              f"| val={val_loss:.4f}"
              + (" ← best" if is_best else ""))

        # best 체크포인트 (optimizer state 포함 — resume 지원)
        if is_best:
            best_val = val_loss
            torch.save({
                "epoch":           epoch,
                "model_state":     model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "val_loss":        best_val,
                "history":         history,
                "cfg":             CFG,
            }, os.path.join(CFG["save_dir"], "craft_best.pth"))

        # 주기적 체크포인트
        if local_ep % CFG["save_every"] == 0:
            torch.save({
                "epoch":           epoch,
                "model_state":     model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "history":         history,
                "cfg":             CFG,
            }, os.path.join(CFG["save_dir"], f"craft_ep{epoch:03d}.pth"))

    print(f"\n학습 완료. 최적 val_loss={best_val:.4f}")
    print(f"최적 가중치: {CFG['save_dir']}/craft_best.pth")
    return history


# ======================================================================
# [셀 11] 학습된 가중치 → craft_detector.py 교체 방법
# ======================================================================
"""
craft_model.py의 CRAFT는 craft_text_detector 패키지의 공식 CraftNet과
state_dict 키가 100% 동일하도록 작성되어 있음 (basenet.slice1~5, upconv1~4.conv.*,
conv_cls.*, sigmoid 없음). 따라서 별도 통합 코드 없이 체크포인트 파일만 옮기면 됨:

1. craft_best.pth(또는 craft_ep*.pth)를 프로젝트 ai/models/craft_finetuned_raw.pth로 복사
   ※ 이 스크립트가 저장하는 체크포인트는 {"model_state": ..., ...} 딕셔너리이므로
     model_state만 꺼내서 저장해야 함:
       ckpt = torch.load('craft_best.pth', map_location='cpu')
       torch.save(ckpt['model_state'], 'craft_finetuned_raw.pth')

2. ai/detection/craft_detector.py는 이미 ai/models/craft_finetuned_raw.pth가 있으면
   자동으로 로드하도록 되어 있음 (Craft(weight_path_craft_net=...)) — 코드 수정 불필요.

3. 로드 확인: python -c "from detection.craft_detector import CraftDetector; CraftDetector()"
   가 에러 없이 끝나고, ai/test_images/의 7개 이미지 재탐지 결과 및
   ai/debug_gt.py의 score map 통계(collapse 여부)를 확인할 것.
"""

if __name__ == '__main__':
    history = main()
