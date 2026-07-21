# STATUS — 현재 상태 · 남은 일 · 미결 (단일 출처)

> 여러 문서에 흩어져 있던 "미완/한계/논의 필요"를 **한곳에 모은 살아있는 트래커**입니다.
> 남은 일은 여기만 보면 됩니다. 설계 결정의 배경은 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md),
> 과거 경위는 [archive/IMPLEMENTATION_HISTORY.md](archive/IMPLEMENTATION_HISTORY.md) ·
> [archive/DETECTION_IMPROVEMENT_PLAN.md](archive/DETECTION_IMPROVEMENT_PLAN.md).
> 최종 갱신: 2026-07-21. 코드의 실제 상태는 항상 파일과 `git log`를 우선.

## 상태 표기
- ✅ **됨** · 🟡 **부족**(근사치/한계) · ⛔ **안 됨**(스텁/미착수) · 🤝 **팀 논의**(AI 혼자 못 정함)

---

## 0. 한눈에 보기

| 영역 | 항목 | 상태 |
|---|---|---|
| 이미지 | 전처리·탐지·크기/기울기 채점·종합점수·절대규범 | ✅ 됨 |
| 이미지 | CRAFT 파인튜닝 (더 정확하게 특훈) | ⛔ 미배포·조건부 재도전 (→ §4) |
| 이미지 | 탐지 정확도 한계 (소형 밀집·흘림·획굵기 왜곡) | 🟡 부족 |
| 이미지 | 평가셋(채점 정확도 확인용 시험지) | 🟡 4장뿐·GT 오류 17% |
| 이미지 | 속도 (500ms 목표) | 🤝 GPU 필요 |
| 캔버스 | 규칙 기반 채점 (획순·자간·크기) | ✅ 임시버전 동작 |
| 캔버스 | LSTM 2곳 (진짜 똑똑한 부분) | ⛔ 스텁 (실데이터 필요) |
| 캔버스 | 실사용자 데이터 수집 | 🤝 팀 논의 |
| 캔버스 | 획순 복수 정본 | 🟡 ㅌ만 됨 (확장 여지) |
| 통합 | 백엔드 병합·라우트·좌표계·torch | 🤝 팀 논의 |
| 범위밖 | 개인화·실시간영상·OCR·자유필기 획순 | ⏸ 청사진(범위 밖) |

---

## 1. 이미지 모드 (사진 채점)

**✅ 이미 된 것** — 전처리, 글자 탐지(CRAFT pretrained), 크기·기울기·자간·행간·기준선·획굵기 채점,
종합점수(교육 가중 3:2:1), 명료도 경고화, 절대 규범 축(norm_deviations). *참고: 전처리 리사이즈
유지 vs 제거 측정 결과 **유지가 정답**으로 확정(제거 시 큰 사진에서 글자 손실+지연 급증) — [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §3.1.*

- **🟡 탐지 정확도 한계** — 소형 밀집(모델이 반응 안 함, 후처리 불가·확정된 한계) / 흘림(test5·test7,
  라벨링조차 어려움) / 좁게 붙인 2음절('오른'·'급한', 기하만으론 분리 불가) / 획 굵기 과대측정(윤곽선
  이진화 사진) / 기울기 게이트 보수적. 근거: `archive/DETECTION_IMPROVEMENT_PLAN.md`.
- **🟡 평가셋·정답지(GT) 부족 — 가장 레버 큼** — 표본 4장(197음절), GT 자체 오류 ≈17%(검수 필요),
  순환성(탐지기 초안 GT), test4 미라벨, @0.5 병행 필요. 할 일: 손글씨 추가 + 독립 GT + test4 라벨링.
- **🤝 속도(레이턴시)** — 목표 500ms(REQ-004I-1)인데 CPU 실측 1.8~11초 → GPU/비동기/ONNX 없이는 불가.
  요구값 하향 개정 또는 인프라 결정 필요.
- **🟡 규범 임계값 임시값** — `TILT_NORM_DEG=7`·`LINE_NORM_MIN_RATIO=1.0`·`WORD_GAP_RATIO=0.55`·가중치
  3:2:1 모두 초안. 실데이터로 재튜닝. 근거: [NORM_STROKE_RESEARCH.md](NORM_STROKE_RESEARCH.md) §1·§3.
- **🟡 문서 낡음** — [handwriting_evaluation.md](handwriting_evaluation.md)가 갱신됨(구현 완료 반영).

## 2. 캔버스 모드 (태블릿 직접 쓰기)

- **⛔ LSTM 2곳이 스텁** — `lstm_refine_grouping`(입력 그대로 반환), `lstm_analyze_stroke_order`(획 개수
  비교만). 단 `analyze_stroke_order_by_position`(위치+모양 기하)가 대신 동작해 임시 근사치로는 쓸 만함.
  교체 조건 = 실사용자 데이터 확보(→ 2번). 함수 이름/형식 고정, 내부만 교체.
- **🤝 실사용자 데이터 수집(self-labeling)** — "제시형 연습이 곧 자동 정답 라벨". 정할 것: 전송 시점·
  엔드포인트, 목표 규모, 개인정보·동의, 수집 주체/역할, 소규모 파일럿 여부. 근거: [../CANVAS_DATA_PLAN.md](../CANVAS_DATA_PLAN.md).
- **🟡 획순 복수 정본 — 지금은 ㅌ만** — 감점 없이 "표준은 X" 안내 병기. ㅋ·ㅂ·ㄹ·ㅅ·ㅎ은 교과서 실물
  근거 확보 시 `ALTERNATIVE_STROKE_ORDERS`에 한 줄씩 추가(근거 없이 임의 추가 금지). 대안 많아지면
  채점이 느슨해질 수 있어 신중히. 근거: [NORM_STROKE_RESEARCH.md](NORM_STROKE_RESEARCH.md) §2.
- **🟡 기타** — 여러 줄(멀티라인) 미지원, 필압은 센서 미지원 기기에서 1.0 고정, 위치 기반 획순의 겹침 오판.

## 3. 통합 · 범위

- **🤝 백엔드 통합(실서비스 실질 블로커)** — 어댑터 `backend/app/services/ai_adapters.py` 실구현은 있음.
  남은 것: ① 브랜치 병합(ai-setup 실구현 채택) ② 라우트가 AI 전처리/분석 쓰도록 결정(⚠️ 정확도는
  전부 AI 전처리 전제 — 다른 방식 섞으면 보장 안 됨) ③ bbox "전처리 후" 좌표계 오버레이 합의 ④
  backend `requirements.txt`에 torch 추가. 근거: [HANDOFF.md](HANDOFF.md) §5.1.
- **⏸ 범위 밖(청사진)** — 개인화·실시간 영상(YOLO)·OCR 텍스트 변환·자유필기 획순 채점. 이번 범위 =
  두 모드 분석 + 학습 대시보드(SFR-008)까지. 근거: [requirement.md](requirement.md).

---

## 4. 파인튜닝 재도전 판단 메모 ⭐

> 결론: **지금 당장은 불필요**(pretrained로 서비스 가능). 시간·여지 있을 때 조건부 재도전.
> 상세 경위는 [archive/IMPLEMENTATION_HISTORY.md](archive/IMPLEMENTATION_HISTORY.md) Phase 12·§14.

- **예전 실패 이유(쉽게)** — ① 정답지 불균형으로 학습 붕괴 ② 학습/실제 입력이 다른 그림 ③ 좋은
  시점(체크포인트)을 못 골랐음(자체 점수↓인데 실제 탐지는↓) ④ **결정적**: 검증이 실제 배포 경로가 아닌
  기준 낮춘 별도 스크립트였음 → 진짜 경로로 재검증하니 0개 탐지 → 최종 포기.
- **지금 달라진 점(재도전 가치)** — ① **실제 배포 경로 기준 F1 채점 하니스**(`eval/evaluate_detection.py`)
  생김 ② 정밀 수동 GT(197음절, 2차 검수) ③ 검증 전용 `debug_compare_production.py`. → 예전의 "시점 잘못
  고르기" 실수를 원천 차단 가능.
- **다시 한다면 — 바꿔볼 가설** — ① 정답지 정밀화(watershed로 pseudo-GT 정제) ② distance-transform이
  학습 땐 신호를 약화했을 가능성 → 빼고 비교 ③ 학습률/스케줄 과했을 가능성.
- **✋ 절대 규칙** — 매 체크포인트를 **실제 `CraftDetector`(기본 threshold)로 검증**(자체 loss 믿지 말 것).
  재도전 조건 = 다른 개선 다 해도 목표(평균 F1@0.3 ≥ 0.7, AI Hub 각 R@0.3 ≥ 0.5) 미달일 때만.
- **재사용 자산** — `craft_model.py`(구조 완전 호환), 학습 파이프라인 전체(OHEM·도메인 일치), `gt_generator.py`,
  `kaggle_finetune.py`(resume), `debug_compare_production.py`(검증), `craft_finetuned_epoch9.pth.bak`(보관).

---

## 5. 우선순위 제안

1. **[블로커]** 백엔드 통합(§3) + 속도/GPU 결정(§1)
2. **[품질 근간]** 평가셋 확장·독립 GT(§1) — 모든 정확도 판단의 신뢰도. 파인튜닝 재도전도 이게 선행.
3. **[캔버스]** 데이터 수집 논의 착수(§2)
4. **[정리]** 규범 임계값은 실데이터 모이면 재튜닝
5. **[조건부·후순위]** 파인튜닝 재도전(§4) — 2번 갖춰지고 시간 여유 있을 때만

> 항목을 처리하면 이 표의 상태 배지와 원본 문서를 함께 갱신하세요.
