# 중간보고용 핵심 구현 코드

> 이미지 모드(SFR-003I~004I) 파이프라인 — 전처리 / CRAFT 탐지 / 파인튜닝 3가지로 정리.

```
카메라 촬영 → [1] 전처리(이진화) → [2] CRAFT 글자 탐지 → 크기/간격 분석 → 피드백
                                        ↑
                                   [3] AI Hub 데이터로 파인튜닝
```

---

## 1. 이미지 전처리 — 기울기 자동 보정

`ai/preprocessing/image_preprocessor.py`

```python
def _detect_skew_angle(self, binary: np.ndarray) -> float:
    """이진화된 문서 이미지에서 직선 성분을 검출해 전체 기울기를 추정한다."""
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 80,
                            minLineLength=max(100, int(w * 0.15)), maxLineGap=10)
    # 검출된 직선들의 각도 중 ±6° 이내인 것만 골라 중앙값을 최종 기울기로 사용
    return angle

def _deskew(self, binary):
    angle = self._detect_skew_angle(binary)
    return self._rotate_image(binary, -angle), angle   # warpAffine으로 역방향 회전 보정
```

Canny로 엣지를 뽑고 HoughLinesP로 직선(문서 테두리·표 경계 등)을 검출한 뒤, 그 직선들의 각도 중앙값을 문서 전체 기울기로 간주해 반대 방향으로 회전시켜 보정한다.

---

## 2. CRAFT 탐지 — Distance Transform 입력 변환 + Tight Bbox

`ai/detection/craft_detector.py`

```python
def _craft_prediction(self, binary: np.ndarray) -> dict:
    """이진 이미지를 그대로 넣는 대신, 각 잉크 픽셀이 획 중심에서 얼마나
       가까운지를 밝기값으로 표현한 그레디언트 이미지로 변환해 CRAFT에 입력."""
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    return self._craft.detect_text(cv2.cvtColor(dist_norm, cv2.COLOR_GRAY2RGB))

def _tighten_box(self, pts, binary):
    """CRAFT가 반환한 박스 내부의 실제 잉크 픽셀만 골라 min/max 좌표로
       꽉 끼는(tight) bbox를 다시 계산한다."""
    ink = (roi > 0) & (poly_mask > 0)
    tx, ty = x0 + ix.min(), y0 + iy.min()
    tw, th = ix.max() - ix.min() + 1, iy.max() - iy.min() + 1
```

CRAFT는 region score map(글자 존재 확률)과 affinity map(인접 글자 연결성)을 픽셀 단위로 예측하는 모델이며, 그 결과 박스를 잉크 픽셀 기준으로 재계산해 최종 bbox로 사용한다.

---

## 3. 파인튜닝 — 글자 단위 GT 생성 + 동일 전처리 재사용 + OHEM

`ai/training/gt_generator.py` / `ai/training/kaggle_finetune.py`

```python
def split_word_box(word_pts, num_chars):
    """AI Hub 라벨은 단어(어절) 단위 bbox뿐이라, 텍스트 길이만큼 등분해
       글자 단위 정답을 직접 생성한다. 상단/하단 변을 독립적으로 등분해
       대응점을 이어 기울어진 단어도 원본 기울기를 따라가도록 처리."""
    tl, tr, br, bl = word_pts
    top    = [tl + (tr - tl) * (i / num_chars) for i in range(num_chars + 1)]
    bottom = [bl + (br - bl) * (i / num_chars) for i in range(num_chars + 1)]
    return [np.array([top[i], top[i+1], bottom[i+1], bottom[i]]) for i in range(num_chars)]


class HandwritingDataset(Dataset):
    def __getitem__(self, idx):
        img = cv2.imread(img_path)
        boxes = parse_aihub_json(lbl_path)                     # 글자 단위 polygon (위 함수)
        binary, boxes = self._binarize_and_deskew(img, boxes)  # 1번과 동일한 전처리 재사용
        img = self._to_dist_transform_rgb(binary)                # 2번과 동일한 전처리 재사용
        region_map, affinity_map = generate_score_maps(img_h, img_w, boxes)


def _ohem_mse(self, pred, gt):
    """양성(글자) 픽셀은 전부, 음성(배경) 픽셀은 loss가 가장 큰 상위 k개만 골라 평균."""
    loss = (pred - gt) ** 2
    pos_loss = loss[gt > 0.1]
    hard_neg_loss, _ = torch.topk(loss[gt <= 0.1], k=...)
    return torch.cat([pos_loss, hard_neg_loss]).mean()
```

학습 데이터 로더는 AI Hub의 단어 단위 라벨을 `split_word_box`로 글자 단위 정답으로 변환하고, 이미지 자체도 1·2번과 동일한 전처리(이진화+deskew, distance transform)를 거치도록 구성해 학습 입력과 서비스 입력의 형태를 통일한다. 손실 함수는 배경 비중이 압도적인 데이터 특성상 OHEM으로 양성 픽셀과 어려운(hard) 음성 픽셀만 반영한다.
