# 백엔드 통합 가이드 — AI 파트 인계 문서

> **독자**: 이 코드베이스를 처음 보는 백엔드 담당 팀원.
> **정본 관계**: 함수 계약(시그니처·입출력 JSON)의 정본은 [`AI_MODEL_INTERFACE.md`](AI_MODEL_INTERFACE.md) — 여기서 반복하지 않는다.
> 이 문서는 **통합하면서 실제로 겪을 일**(병합·환경·함정·검증·팀 결정 목록)만 다룬다.
> **작성**: 2026-08-01. 모든 수치는 이날 재실측했거나 출처(파일)를 병기함.

---

## 0. 한눈에 — 통합 절차

```
① 브랜치 병합(§2) → ② 환경 구축(§3) → ③ 라우트 연결(§4) → ④ 자가 검증(§7)
```

**가장 중요한 두 가지**만 기억하면 큰 사고는 없다:
- **전처리 체인**(§5-1): `craft_detect_chars`에는 반드시 어댑터의 `preprocess_image` 출력을 넣는다. 자체 이진화를 섞으면 성능 무보장.
- **좌표계**(§5-2): 반환 bbox는 "전처리 후" 좌표다. 오버레이는 **전처리 이미지 위에** 그린다(팀 확정). 원본 사진 위에 그리면 어긋난다.

---

## 1. 무엇이 인계되는가 (전체 그림)

두 개의 **완전히 독립된** 파이프라인(요구사항이 로직 공유를 금지, `requirement.md`):

| 파이프라인 | 무엇을 하나 | 상태 | 실측 (2026-08-01 재확인) |
|---|---|---|---|
| **이미지 모드** (사진) | 전처리 → CRAFT 글자 탐지 → 크기·기울기·자간·행간·기준선 5지표 채점 | ✅ 완성 | 평가셋 12장 **F1@0.3 0.891 / F1@0.5 0.820** |
| **캔버스 모드** (태블릿 획) | 획 그룹핑 → 획순·크기·자간 채점 | ✅ 규칙 기반 동작 | 단위 테스트 포함 **pytest 34개 전부 통과** |

**숨기지 않는 한계** (알고 시작할 것):
- **과병합**: 탐지 오류의 대부분(merge 151 vs split 23)은 붙여쓴/흘림 2음절을 한 박스로 잡는 것. 파라미터로 못 넘는 벽이라 현재 수준이 상한 (`STATUS.md` §1).
- **레이턴시**: CPU 실측 이미지당 약 2.9초(로드 제외; 첫 호출은 모델 로드 포함 7.3초). 요구 목표 500ms(REQ-004I-1)는 CPU로 불가 → **팀 결정 필요**(§8-4).
- **캔버스 LSTM 2곳은 스텁**: `lstm_refine_grouping`(입력 그대로 반환)·`lstm_analyze_stroke_order`(획 개수 비교만). 실사용자 데이터 확보 후 내부만 교체 예정. 대신 실동작 대안이 있음(§5-4).
- 파인튜닝 가중치는 **없음** — 3회 시도 모두 pretrained보다 낮아 미배포, 학습 코드도 2026-07-31 트리에서 제거됨. 리포의 파인튜닝 관련 내용은 전부 **문서 기록**이니 통합 시 신경 쓸 것 없음.

---

## 2. 브랜치 병합

- 실구현은 **`feature/ai-setup`** 브랜치에 있다: `backend/app/services/ai_adapters.py`(실구현 연결본) + `ai/` 패키지 전체.
- `feature/backend-setup`에도 같은 경로에 **스텁 버전**이 있어 병합 시 충돌한다 → **ai-setup 쪽(실구현)을 채택**하면 된다. 계약 문서에 명시된 의도된 교체다 (`AI_MODEL_INTERFACE.md` 상단 2026-07-18 노트).
- `ai/` 폴더 전체가 런타임 의존이다 — 어댑터가 `from ai.analysis...` 식 절대 import를 쓴다.

---

## 3. 환경 구축 (그대로 따라하기)

Python **3.14**에서 검증된 조합 (`ai/requirements.txt` 상단 주석이 원본 절차 — 아래는 요약):

```bash
# git 루트(2026-hanium-project/)에서
python3 -m venv ai/venv
P=ai/venv/bin/python            # Windows는 ai/venv/Scripts/python.exe
$P -m pip install --upgrade pip
$P -m pip install -r ai/requirements.txt
# craft-text-detector는 반드시 --no-deps로 따로 설치 (이유: 주의② 아래)
$P -m pip install --no-deps craft-text-detector==0.4.3
# 마지막으로 vgg16_bn.py 1줄 패치 (이유·정확한 위치: ai/requirements.txt 주석 30~43행)
#   venv/lib/python3.*/site-packages/craft_text_detector/models/basenet/vgg16_bn.py
#     - `from torchvision.models.vgg import model_urls` 줄 삭제
#     - `models.vgg16_bn(pretrained=pretrained)` → `models.vgg16_bn(weights=None)`
#     - `model_urls[...] = ...` 재할당 줄 삭제
```

- **주의① opencv는 4.x 고정** (`opencv-python-headless==4.11.0.86`). 5.x는 `HoughLinesP`/`connectedComponents` 동작이 바뀌어 `craft_detector.py`가 깨진다. **업그레이드 금지.**
- **주의② craft-text-detector 0.4.3**은 잘못된 opencv 핀을 갖고 있어 requirements에 같이 넣으면 pip가 구버전 opencv 빌드를 시도하다 실패한다 → `--no-deps` 필수.
- **백엔드 requirements 반영**: 백엔드 서비스가 이미지 모드를 서빙하려면 위 의존성(torch·torchvision CPU, opencv 4.x, scipy, gdown, craft-text-detector)이 백엔드 환경에도 필요하다. `ai/requirements.txt`를 그대로 합치는 것을 권장.
- **모델 가중치는 git에 없다**(`.gitignore`). 첫 `craft_detect_chars` 호출 때 gdown이 `~/.craft_text_detector/weights/craft_mlt_25k.pth`(83MB)를 **자동 다운로드**한다 → **첫 실행은 인터넷 필요**. 오프라인 서버는 이 파일을 같은 경로에 미리 배치하면 된다.

---

## 4. 호출 — 함수 6개와 예제

`backend/app/services/ai_adapters.py`가 제공하는 것 (입출력 스펙은 `AI_MODEL_INTERFACE.md` 정본):

| 함수 | 역할 | 실제 구현 | 상태 |
|---|---|---|---|
| `craft_detect_chars(binary, w, h)` | 글자 박스 탐지 (계약③) | `ai/detection/craft_detector.py` | ✅ CRAFT pretrained |
| `lstm_refine_grouping(groups)` | 획 그룹핑 보정 (계약①) | `ai/canvas/stroke_grouping.py` | ⛔ 스텁(입력 그대로) |
| `lstm_analyze_stroke_order(strokes, seq)` | 획순 분석 (계약②) | `ai/canvas/stroke_standards.py` | ⛔ 스텁(개수 비교) — §5-4 |
| `preprocess_image(bytes)` | AI 전처리 드롭인 — `(binary, w, h)` 반환 | `ai/preprocessing/image_preprocessor.py` | ✅ **탐지 전 필수**(§5-1) |
| `preprocess_image_full(bytes)` | 전처리 + 품질점수·재촬영 판정(REQ-003I-4) | 〃 | ✅ |
| `analyze_size_angle(chars, binary)` | 크기·기울기·기준선 채점 (SFR-005I) | `ai/analysis/handwriting_analyzer.py` | ✅ |

**이미지 모드 라우트의 표준 흐름** (= `ai/debug_e2e_image_mode.py`가 그대로 시연):

```python
from app.services.ai_adapters import (
    preprocess_image_full, craft_detect_chars, analyze_size_angle)

pre   = preprocess_image_full(raw_bytes)          # ① 전처리 + 품질/재촬영 판정
chars = craft_detect_chars(pre["binary_image"],   # ② 글자 탐지 (반드시 ①의 출력 사용)
                           pre["width"], pre["height"])
ana   = analyze_size_angle(chars, pre["binary_image"])  # ③ 채점·피드백
# 오버레이용으로 pre["binary_image"](전처리 이미지)를 응답에 포함할 것 (§5-2)
```

**성능 특성** (2026-08-01 WSL CPU, test.jpg 1676×2216 실측):
- CRAFT는 **프로세스당 1회 로드되는 싱글턴**(동시 호출은 내부 Lock 직렬화). 첫 호출 7.3초(로드 포함) → 이후 이미지당 약 2.9초.
- 캔버스 모드 함수들은 **torch 없이 동작**(lazy import) — 캔버스 요청은 CRAFT 로드를 유발하지 않는다.

**캔버스 모드**: 계약 함수 2개는 스텁이므로, 실제 채점 라우트는
`ai/canvas/canvas_quality_analyzer.py`의 **`analyze_canvas_writing(char_groups, target_text)`**
(크기·자간·획순 종합, `requirement.md` SFR-005C 스펙 그대로 반환)를 쓰는 것을 권장 (`HANDOFF.md` §4.5).

---

## 5. ⚠️ 함정 목록 — 무시하면 생기는 일

| # | 함정 | 무시하면 | 대처 |
|---|---|---|---|
| 1 | **전처리 체인 의존** — 탐지 성능(F1 0.891)은 전부 AI 전처리(측지 재구성 계열) 출력이 전제 | 백엔드 자체 Otsu 이진화 등을 넣으면 성능 무보장. 같은 이미지가 전처리 도메인 차이로 65 vs 3박스가 된 실측 사례 있음(`STATUS.md` §3) | 탐지 입력은 **반드시 어댑터 `preprocess_image` 출력** |
| 2 | **좌표계** — bbox는 deskew·리사이즈 반영된 **"전처리 후" 좌표** | 프론트가 원본 사진 위에 박스를 그리면 전부 어긋남 — *통합 첫날 터지는 유형의 버그* | 오버레이는 **전처리 이미지 위**(팀 확정, `IMPLEMENTATION_PLAN.md` §3.1). 전처리 이미지를 API 응답에 포함 |
| 3 | **어댑터 docstring의 낡은 수치** — `ai_adapters.py` 주석의 "F1@0.3=0.960", "Adaptive Threshold blockSize=15 C=5", "DETECTION_IMPROVEMENT_PLAN.md" 언급은 2026-07-27 전처리 개편 **이전** 서술 | 옛 수치를 계약으로 오해 | 수치·전처리 설명은 **이 문서와 `STATUS.md`가 최신**. 병합 후 docstring 갱신 권장(AI 파트 클론이 sparse라 backend 파일을 못 고쳤음) |
| 4 | **획순 함수가 두 개** — 계약의 `lstm_analyze_stroke_order`는 시그니처 유지용 스텁 | "획순 분석이 안 되네?" 하고 헤맴 | 실동작 구현은 `analyze_canvas_writing()`(§4 끝). 채점 라우트는 이쪽 |
| 5 | **한글 경로 + `cv2.imread/imwrite`** (Windows) | 에러 없이 **조용히 실패** | `np.frombuffer`+`cv2.imdecode` / `cv2.imencode` 패턴 사용 — 모든 `ai/debug_*.py`가 예시 |
| 6 | **콘솔 인코딩** — 한글/이모지 `print()` 깨짐 (cp949) | 디버깅 출력이 깨지거나 에러 | `PYTHONIOENCODING=utf-8`로 실행 |
| 7 | **가중치 자동 다운로드** | 오프라인 첫 배포에서 탐지가 죽음 | §3 마지막 항목 — 사전 배치 |
| 8 | **실행 위치/import 규약** — 코드는 `ai.*` 절대 import | 직접 스크립트 실행 시 ModuleNotFoundError | 어댑터는 sys.path를 스스로 처리(uvicorn을 backend/에서든 루트에서든 OK). **직접 스크립트는 git 루트에서** 실행 |

---

## 6. 변경 금지 (바꾸면 무슨 일이 생기는지)

- **계약 3함수의 이름·파라미터·반환 형식** — 백엔드↔AI 접점 전체가 깨짐. 내부 구현만 교체 가능 (`AI_MODEL_INTERFACE.md`).
- **`craft_detector.py` 내부 탐지 파라미터** (배포 설정: `text=0.7, link=1.0, low=0.4, long=960` — 평가 리포트 헤더 출처). 특히 `link_threshold=1.0`과 후처리(과폭 분할·자소 병합)는 과병합 억제 체인의 일부라 임의 조정 시 F1 0.891이 무보장.
- **opencv 5.x 업그레이드 금지** (§3 주의①).
- **전처리 교체·생략 금지** (§5-1).

---

## 7. 통합 후 자가 검증 (혼자 확인 가능, 기대값 포함)

git 루트에서, `P=ai/venv/bin/python` (Windows: `ai/venv/Scripts/python.exe`):

1. **단위 테스트**: `$P -m pytest ai/tests -q` → **34 passed** (2026-08-01 실측 2.78s).
2. **탐지 정확도**: `$P ai/eval/evaluate_detection.py` →
   - 클론에 있는 사진 7장(test·test2·test5~7·test8·test_line1) 기준 평균 **F1@0.3 ≈ 0.857 / F1@0.5 ≈ 0.792**.
   - `skip: IMG_OCR_... — 이미지 없음` 5줄이 나오는 것은 **정상** — 태블릿 평가 5장은 AI Hub 원본이라 git에 없다(재배포 금지, AI 파트 로컬 전용). 12장 전체 기준 수치가 F1@0.3 0.891/@0.5 0.820.
3. **E2E (어댑터 경로 그대로)**: `$P ai/debug_e2e_image_mode.py` — `preprocess_image_full → craft_detect_chars → analyze_size_angle`를 4장에 실행하고 단계별 시간·결과 출력 (backend/가 체크아웃된 풀 클론에서 동작).
4. **한 장 스모크 기대값** (test.jpg, 2026-08-01 실측): 전처리 후 1676×2216 → **13개 박스**(`char_0`~) → `total_score` 42.5 "보통". 같은 버전 조합이면 동일하게 재현된다.

---

## 8. 팀에서 정해야 할 것 (AI 파트 혼자 못 정함 — `STATUS.md` §3 원본)

1. **라우트 교체 범위**: 기존 `image_preprocessing.preprocess_image`(Otsu)를 어댑터 `preprocess_image`로 교체할지, 기존 `image_analysis.py`를 `analyze_size_angle`로 교체할지. ⚠️ 정확도 수치는 전부 AI 전처리 전제(§5-1)라 **교체 권장**.
2. **좌표계·오버레이 합의(프론트 포함)**: "bbox=전처리 후 좌표, 오버레이=전처리 이미지 위"를 프론트에 명시 전달 + 전처리 이미지를 응답 스키마에 포함.
3. **백엔드 requirements에 AI 의존성 추가** (§3).
4. **레이턴시 정책**: 목표 500ms vs CPU 실측 ~2.9초/장 → GPU 인프라, 비동기 처리(작업 큐), 또는 요구값 개정 중 택1.
5. (선택) `preprocess_image_full`의 재촬영 판정(REQ-003I-4, 품질 40점 미만)을 라우트에 반영할지.

---

## 9. 문서 지도 — 뭘 읽고, 뭘 무시해도 되는가

**통합에 필요한 것만 순서대로**:
1. 이 문서 → 2. `AI_MODEL_INTERFACE.md`(계약 정본) → 3. `HANDOFF.md` §5.1·§3(통합 상세 배경) → 4. `STATUS.md` §3(미결 트래커)

**무시해도 되는 것** (AI 파트 내부 기록 — 통합과 무관):
- `DEVLOG.md`(개발 서사)·`archive/`(과거 상세)·`IMAGE_PIPELINE_REBUILD_PLAN.md`(전처리 개편 내부 계획)
- **파인튜닝 관련 서술 전부** — 코드 리포에는 파인튜닝 코드가 없다(문서 기록만 존재). 재도전 여부는 AI 파트 내부 과제.

궁금한 점은 AI 파트 담당에게 — 이 문서에 없는 답은 대부분 `HANDOFF.md`에 있다.
