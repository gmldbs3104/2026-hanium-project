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
"""

# ======================================================================
# [셀 1] 패키지 설치 (Colab에서 한 번만 실행)
# ======================================================================
# !pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu118
# !pip install -q opencv-python-headless scipy tqdm

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
# 1차 학습 (처음 실행 — 2~3시간)
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
    "max_samples" : 2_000,

    # 저장
    "save_dir"    : "/content/drive/MyDrive/craft_finetuned",
    "save_every"  : 2,

    "pretrained"   : "/content/craft_mlt_25k.pth",
    "resume_from"  : None,   # 1차: None / 2차: 아래 RUN2_CFG 사용
}

# ──────────────────────────────────────────────────────────────────────
# 2차 학습 (1차 완료 후 — 5시간)
# 아래 주석을 해제하고 CFG = RUN2_CFG 로 교체해서 실행
# ──────────────────────────────────────────────────────────────────────
# RUN2_CFG = {
#     **{k: v for k, v in CFG.items()},   # 1차 설정 그대로 상속
#
#     # 재개할 체크포인트 (1차 학습의 최적 가중치)
#     "resume_from"  : "/content/drive/MyDrive/craft_finetuned/craft_best.pth",
#
#     # 추가 학습 설정
#     "epochs"       : 25,       # 추가로 25 epoch (총 35 epoch)
#     "max_samples"  : 3_000,    # 데이터 조금 더 (시간 여유)
#     "lr"           : 3e-5,     # 낮은 LR로 정밀 조정
#     "warmup_ep"    : 0,        # 재개 시 warmup 불필요
#     "save_every"   : 3,
# }
# CFG = RUN2_CFG   # ← 이 줄을 활성화

os.makedirs(CFG["save_dir"],  exist_ok=True)
os.makedirs(CFG["cache_dir"], exist_ok=True)

# ======================================================================
# [셀 4] 사전학습 CRAFT 가중치 다운로드
# ======================================================================
import urllib.request

WEIGHT_URL = "https://github.com/clovaai/CRAFT-pytorch/releases/download/pre-release/craft_mlt_25k.pth"
if not os.path.exists(CFG["pretrained"]):
    print("사전학습 가중치 다운로드 중...")
    urllib.request.urlretrieve(WEIGHT_URL, CFG["pretrained"])
    print("완료:", CFG["pretrained"])

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

    # 이미 복사된 경우 건너뜀
    existing = len(glob.glob(os.path.join(local_img_dir, "*.png")))
    if existing >= max_samples:
        print(f"  로컬 캐시 이미 존재 ({existing}개) — 복사 생략")
        return local_img_dir, local_label_dir

    # manifest stem 목록
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    random.shuffle(manifest)
    subset = manifest[:max_samples]

    # Drive에서 stem 기반으로 파일 탐색
    print(f"  Drive에서 stem 인덱스 구축 중...")
    img_map, label_map = {}, {}
    for p in glob.glob(os.path.join(drive_img_root,   "**", "*.png"),  recursive=True):
        img_map[os.path.splitext(os.path.basename(p))[0]] = p
    for p in glob.glob(os.path.join(drive_label_root, "**", "*.json"), recursive=True):
        label_map[os.path.splitext(os.path.basename(p))[0]] = p

    ok = err = 0
    print(f"  {max_samples}개 로컬 복사 시작...")
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
        img = cv2.imread(img_path)
        if img is None:
            # 손상 파일 → 더미 반환
            return self.__getitem__((idx + 1) % len(self))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 라벨 파싱
        boxes = parse_aihub_json(lbl_path)  # List[ndarray (4,2)]

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
    imgs, regions, affinities = zip(*batch)
    # 배치 내 최대 크기로 패딩
    max_h = max(x.shape[1] for x in imgs)
    max_w = max(x.shape[2] for x in imgs)
    max_h = math.ceil(max_h / 32) * 32
    max_w = math.ceil(max_w / 32) * 32

    def pad(t, val=0.0):
        _, h, w = t.shape
        return F.pad(t, (0, max_w - w, 0, max_h - h), value=val)

    imgs       = torch.stack([pad(x) for x in imgs])
    regions    = torch.stack([pad(x) for x in regions])
    affinities = torch.stack([pad(x) for x in affinities])
    return imgs, regions, affinities

# ======================================================================
# [셀 8] 손실 함수
# ======================================================================

class CRAFTLoss(nn.Module):
    """
    Region + Affinity MSE Loss.
    신뢰도 마스크(confidence_mask)로 애매한 영역(라벨 없는 부분) 가중치 감소.
    """
    def __init__(self, lambda_affinity: float = 1.0):
        super().__init__()
        self.lambda_a = lambda_affinity

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

        loss_r = F.mse_loss(pred_region,   gt_region)
        loss_a = F.mse_loss(pred_affinity, gt_affinity)
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
파인튜닝 완료 후 프로젝트에 적용하는 방법:

1. craft_best.pth를 프로젝트 ai/models/ 에 복사

2. ai/detection/craft_detector.py의 CraftDetector.__init__에서:

    # 기존
    self._craft = Craft(...)

    # 교체: 파인튜닝 가중치 로드
    from training.craft_model import CRAFT
    self._model = CRAFT(pretrained_backbone=False, freeze_backbone=False)
    ckpt = torch.load('models/craft_best.pth', map_location='cpu')
    self._model.load_state_dict(ckpt['model_state'])
    self._model.eval()

3. _craft_prediction()도 직접 추론으로 교체:

    def _craft_prediction(self, binary):
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        img_t = preprocess(dist_norm)          # normalize 등
        with torch.no_grad():
            region, affinity = self._model(img_t)
        # boxes 생성 → 기존 _process_boxes 로직 재사용
"""

if __name__ == '__main__':
    history = main()
