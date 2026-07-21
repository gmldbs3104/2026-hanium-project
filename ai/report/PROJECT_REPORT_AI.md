# 프로젝트 결과보고서 작성용 — AI 파트(이미지 모드)

> 작성일: 2026-07-10
> 범위: 이미지 모드(전처리 → CRAFT 글자 탐지 → 크기/기울기 판단) 관련 내용만 포함.
> 캔버스 모드(SFR-003C/004C/005C)는 제외.
> 팀 공용 보고서 양식(II. 프로젝트 내용)의 각 항목에 맞춰 정리했습니다. 그대로 옮기거나
> 필요에 맞게 요약해서 쓰면 됩니다.

---

## 1. 프로젝트 구성도

그림 대신 텍스트로 먼저 정리했습니다. 이 흐름 그대로 플로우차트/파이프라인 다이어그램으로
그리면 됩니다.

```
[사용자 업로드 이미지]
        │
        ▼
① 이미지 전처리 (ImagePreprocessor, SFR-003I)
   이진화 → 기울기 보정(deskew) → 품질 검사(RETAKE 여부)
        │
        ▼
② CRAFT 기반 글자 영역 탐지 (CraftDetector, SFR-004I)
   Distance Transform 전처리 → CRAFT 추론(region/affinity score map)
   → connected-component 박스 디코딩 → 잉크 픽셀 기준 tight bbox 재계산
   → 읽기 순서 정렬
        │
        ▼
③ 판단 모듈 (handwriting_analyzer.py, SFR-005I)
   행(row) 분류 → 글자별 기울기(②에서 계산된 angle 재사용)
   → 행 중앙값 대비 크기 비율 → 크기 균일성/기울기 점수 산출
        │
        ▼
[char_id, bounding_box, angle, confidence, 크기/기울기 분석 결과]
```

S/W로만 구성, 별도 H/W 없음.

---

## 2. 프로젝트 기능

### 1) 전체 기능 목록

| 구분 | 기능 | 설명 | 현재진척도(%) |
|---|---|---|---|
| S/W | 이미지 전처리 | 업로드된 손글씨 사진을 이진화하고 기울어짐을 보정, 화질/조명 품질을 점수화해 재촬영 필요 여부 판단 | 100 |
| S/W | CRAFT 기반 글자 영역 탐지 | 전처리된 이미지에서 글자 단위 bounding box, 기울기, 신뢰도를 추출 | 100 (pretrained 가중치 기준) |
| S/W | 손글씨 도메인 CRAFT 파인튜닝 | AI Hub 손글씨 데이터셋으로 CRAFT를 재학습해 탐지 정확도를 높이는 시도 | 실험 완료 / 미채택 (6번 참고) |
| S/W | 크기·기울기 판단 모듈 | 탐지된 글자들의 크기 균일성, 기울기, 행 정렬을 분석해 교정 피드백용 지표 산출 | 100 |

> 파인튜닝 항목은 "완성 가능 시점"을 적어야 한다면, 근본 원인이 아직 미확정이라 특정 시점을
> 약속하기보다 "재검토 필요(원인 미확정)" 정도로 적는 걸 권장합니다.

### 2) S/W 주요 기능

| 기능 | 설명 | 프로젝트 실물사진 |
|---|---|---|
| 이미지 전처리 | 카메라로 찍은 손글씨 사진을 CRAFT가 인식하기 좋은 형태로 변환. Adaptive Threshold 이진화, HoughLinesP 기반 기울기 검출 후 회전 보정, 밝기/대비/블러 등을 점수화해 품질 미달 시 재촬영 요청 | `ai/debug_output/report_preprocess/before_after.jpg` (아래 3번 참고) |
| CRAFT 기반 글자 탐지 | 이진화 이미지에 Distance Transform을 적용해 CRAFT가 학습된 자연 이미지 그라디언트와 유사한 입력으로 변환 후 추론. Region score map을 threshold+connected-component로 디코딩해 글자별 박스 추출, 박스 내 잉크 픽셀로 tight bbox와 기울기(minAreaRect)를 재계산 | `ai/debug_output/report_test/chars_bbox.jpg`, `ai/debug_output/report_test3/chars_bbox.jpg` |
| 크기·기울기 분석 | 탐지된 글자들을 행 단위로 그룹핑하고, CRAFT 단계에서 계산된 기울기 값을 재사용해 글자별 기울기와 행 내 정렬(baseline) 편차를 산출. 행 중앙값 대비 각 글자의 크기 비율로 균일성 점수 계산 | `ai/debug_output/report_test/chars_meta.jpg` + 아래 콘솔 출력 캡처 |

### 3) H/W 주요 기능

해당 없음 (AI 파트는 S/W로만 구성)

---

## 3. 주요 적용 기술

**시나리오**: 사용자가 손글씨가 적힌 사진을 업로드하면, 전처리 단계에서 사진 품질을 검사하고
이진화·기울기 보정을 거친다. 이 결과를 CRAFT 기반 탐지 모듈에 전달해 글자 단위로
위치·크기·기울기를 추출하고, 이 결과를 판단 모듈에 다시 전달해 손글씨의 크기 균일성과
기울기 일관성을 정량화한다. 이 값들이 최종적으로 사용자에게 "글자 크기가 들쭉날쭉함",
"기울어짐" 같은 교정 피드백의 근거 데이터가 된다.

**적용 알고리즘 / 주요 기술**

- **CRAFT (Character Region Awareness for Text Detection)**: clovaai의 공식 아키텍처
  (VGG16-BN backbone + U-Net 형태의 upconv 구조)를 직접 vendoring하여, 학습(Kaggle/Colab)과
  추론(로컬) 환경 어디서든 별도 패키지 의존성 없이 동일한 구조로 가중치를 주고받도록 구성
- **Distance Transform 전처리**: 순수 이진(흑백) 이미지를 그라디언트가 있는 이미지로
  변환(`cv2.distanceTransform`)해, 자연 사진으로 사전학습된 CRAFT의 반응성을 높임
- **OHEM (Online Hard Example Mining)**: 배경 픽셀이 99% 이상을 차지하는 극단적 클래스
  불균형 문제를 해결하기 위해, 예측이 어려운(loss가 큰) 배경 픽셀 위주로 선별해 학습
- **단어→글자 GT 분할**: AI Hub 라벨은 단어 단위 bounding box만 제공하므로, 글자 수에 맞춰
  사다리꼴 형태로 균등 분할하여 글자 단위 학습 정답(Ground Truth) score map을 생성
- **Connected-Component 기반 박스 디코딩**: CRAFT의 region score map을 threshold로
  이진화한 뒤 connected-component 분석으로 개별 글자 영역을 분리, `minAreaRect`로 기울기를
  함께 계산
- **한글 유니코드 완성형 분해**: `(초성idx×21+중성idx)×28+종성idx` 산술 공식을 이용해
  초성 19개/중성 21개/종성 27개 정의만으로 11,172개 완성형 음절 전체를 프로그래밍적으로
  다룰 수 있도록 구현

---

## 4. 프로젝트 개발 환경

| 구분 | | 상세내용 |
|---|---|---|
| S/W 개발환경 | OS | Windows 11 (로컬 개발), Kaggle Notebook / Google Colab (GPU 학습) |
| | 개발환경(IDE) | VS Code (Claude Code 연동) |
| | 개발도구 | Kaggle Notebook, Google Colab, Git |
| | 개발언어 | Python 3 |
| | 기타사항 | PyTorch, OpenCV, NumPy, torchvision |
| H/W 구성장비 | | 해당 없음 |
| 프로젝트 관리환경 | 형상관리 | Git / GitHub |
| | 의사소통관리 | *(팀 협의 후 기재 — 실제 사용 툴로 채워넣기)* |
| | 기타사항 | *(필요 시 기재)* |

---

## 5. 기타 사항 (본문에서 표현되지 못한 프로젝트의 가치 및 제작 노력)

- **실측 기반 검증 원칙**: 학습 손실(loss)이나 자체 정의 지표가 개선되어도 실제 배포
  파이프라인 기준으로는 결과가 다를 수 있다는 것을 발견하고, 이후 모든 모델 검증을 반드시
  실제 서비스가 쓰는 추론 경로(threshold, 후처리 포함)로 재확인하는 절차를 세움
- **안정성 우선 설계(Fallback)**: 파인튜닝된 가중치가 로드 실패하거나 성능이 기준 이하로
  판단될 경우 자동으로 사전학습(pretrained) 가중치로 대체되도록 설계해, 학습 실험의 성패와
  무관하게 서비스가 항상 정상 동작하도록 함
- **데이터 없이도 가능한 부분을 최대한 코드로 해결**: 한글 획순/자모 표준처럼 이미 정해진
  규칙은 별도 데이터셋 없이 유니코드 산술 분해로 프로그래밍적으로 생성해, 데이터 확보 병목
  없이 구현 범위를 넓힘

---

## 6. 프로젝트 추진 과정에서의 문제점 및 해결방안

### 1) 프로젝트 관리 측면

- Google Colab에서 학습 중 세션 연결이 반복적으로 끊겨 장시간 학습이 불가능했음 → Kaggle
  Notebook(Save & Run All 방식의 백그라운드 실행 지원)으로 전환하고, 매 N epoch마다
  체크포인트를 저장한 뒤 이어서 학습을 재개(resume)할 수 있는 구조로 스크립트를 재설계
- 학습 환경(Kaggle Internet:Off 정책)에서 ImageNet 사전학습 가중치 다운로드가 실패하는
  문제 → 온라인 다운로드 의존성을 제거하고, 자체 보유한 CRAFT 사전학습 가중치만으로 학습이
  가능하도록 구성

### 2) 프로젝트 개발 측면

- **아키텍처 불일치**: 별도 패키지(`craft_text_detector`)의 내부 클래스 구조와 직접 구현한
  학습용 모델 클래스 간 state_dict 키가 어긋나 가중치 로드가 실패 → clovaai 공식 구조를
  그대로 vendoring하여 두 환경에서 동일한 키 이름을 갖도록 재작성 (`missing=0,
  unexpected=0` 검증)
- **학습/추론 입력 도메인 불일치**: 학습은 원본 컬러 사진, 추론은 이진화+기울기보정+Distance
  Transform을 거친 이미지를 사용하고 있어 같은 모델이 서로 다른 성격의 입력을 보고 있었음 →
  학습 데이터 파이프라인에도 추론과 동일한 전처리를 적용해 도메인을 일치시킴
- **극심한 클래스 불균형**: 배경 픽셀이 절대다수를 차지해 모델이 "전부 배경"으로 예측하는
  방향으로 collapse하는 문제 → OHEM 적용으로 어려운 배경 샘플 위주 학습
- **평가지표와 실제 성능의 괴리**: 검증 손실(val_loss)이 개선되는 방향으로 체크포인트를
  선택했음에도 실제 글자 탐지 개수는 오히려 감소하는 현상을 발견 → GT 피크 영역 가중치를
  높인 손실 함수와 별도 지표(peak_quality)를 시도했으나, 이 지표 역시 실제 배포 threshold
  기준 탐지 성능과 상관관계가 낮다는 것을 최종 확인. **파인튜닝된 모델 전체가 사전학습
  모델보다 낮은 성능을 보여, 최종적으로 파인튜닝을 채택하지 않고 사전학습 가중치로 롤백**
- **검증 방법 자체의 오류**: 초기에는 자체적으로 낮춘 임의 threshold로 raw score map을 잘라
  성능을 비교했는데, 실제 서비스가 쓰는 정식 추론 경로(기본 threshold 0.7/0.4/0.4)로는
  결과가 전혀 다르게 나온다는 것을 뒤늦게 발견 → 이후 모든 검증을 실제 배포 클래스
  (`CraftDetector`)를 직접 호출하는 방식으로 통일

### 3) 종합 결론

파인튜닝 시도 자체는 여러 차례의 원인 진단과 개선(아키텍처 통합, 도메인 일치, 손실함수
개선)을 거쳤음에도 최종적으로 사전학습 모델의 성능을 넘어서지 못했습니다. 다만 이 과정에서
아키텍처 호환성 문제, 데이터 파이프라인 불일치, 평가지표 신뢰성 문제를 구체적으로 진단하고
문서화했으며, 실패를 서비스 장애로 이어지지 않도록 자동 폴백 구조를 구축한 것이 이번
개발의 실질적 성과입니다.

---

## 7. 프로젝트를 통해 배우거나 느낀 점

- 학습 지표(loss, 자체 정의 metric)가 개선된다고 해서 실제 목적에 맞는 성능이 개선된다는
  보장은 없으며, 최종적으로는 실제 서비스가 쓰는 경로 그대로 검증해야 한다는 것을
  체감했습니다.
- 사전학습 모델을 파인튜닝할 때는 학습 데이터의 입력 분포가 실제 추론 시점의 입력 분포와
  정확히 일치해야 한다는 점이 생각보다 쉽게 어긋날 수 있고, 그 영향이 매우 크다는 것을
  확인했습니다.
- 시도한 개선이 항상 성공하는 것은 아니며, 실패를 판단하고 이전 상태로 되돌리는 것도 개발
  과정의 정당한 결론이라는 것을 배웠습니다.

---

## 첨부 사진 안내

아래 파일들이 이미 생성되어 있습니다 (`ai/debug_output/` 하위, git에는 커밋 안 됨 —
보고서 작성 시 직접 첨부).

| 파일 | 용도 |
|---|---|
| `ai/debug_output/report_preprocess/before_after.jpg` | 전처리 전/후 비교 (원본 사진 \| 이진화+기울기보정 결과) — "이미지 전처리" 실물사진 |
| `ai/debug_output/report_test/chars_bbox.jpg` | test.jpg(8글자, 짧은 문장)에 대한 CRAFT 탐지 bbox 시각화 — "CRAFT 기반 글자 탐지" 실물사진 |
| `ai/debug_output/report_test3/chars_bbox.jpg` | test3.png(130글자, 밀집 손글씨)에 대한 CRAFT 탐지 bbox 시각화 — 복잡한 사례 보여주고 싶으면 이걸로 |
| `ai/debug_output/report_test/chars_meta.jpg` | 글자별 중심점+기울기 방향선 시각화 — "크기·기울기 분석" 실물사진과 함께 사용 |

**판단 모듈(크기·기울기 분석) 콘솔 출력** (스크린샷 대신 텍스트로 캡처해서 표에 같이 넣어도 됨):

```
=== test.jpg (8글자) ===
  size_uniformity_score = 3.9
  mean_angle = -1.43  angle_std = 6.32  overall_tilt = straight
  line_alignment_score = 37.9
  issues:
    - 글자 크기가 고르지 않습니다 (균일성 4/100)
    - 왼쪽으로 기운 글자: char_7
    - 글자들이 기준선에 잘 맞춰져 있지 않습니다 (정렬 38/100)
  size_flag 분포: normal=8 large=0 small=0
```

재생성하려면:
```
cd ai
python debug_preprocess.py test_images/test.jpg debug_output/report_preprocess
python debug_craft.py test_images/test.jpg debug_output/report_test
python debug_craft.py test_images/test3.png debug_output/report_test3
python debug_analysis.py test_images/test.jpg
```
