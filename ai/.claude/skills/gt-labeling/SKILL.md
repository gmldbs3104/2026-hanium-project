---
name: gt-labeling
description: 손글씨 탐지 평가용 음절 GT(ground truth, 정답지)를 새로 만들거나 기존 GT를 고칠 때 사용. blob 라벨링 GUI를 생성해 사람이 브라우저에서 음절을 묶고 label_helper로 빌드한다. AI가 이미지를 직접 판독하지 않아 토큰을 거의 쓰지 않으며, 판독은 사람이 하므로 흘림체도 정확하다. 평가셋 확장(test 이미지 추가), GT 검수·재수정, "박스가 겹친다/틀렸다/음절 경계가 잘못됐다" 수정에 모두 적용.
---

# 음절 GT 라벨링

`ai/eval/`의 손글씨 탐지 평가셋(`eval/gt/*.json`)을 만들거나 수정하는 절차. **AI가 이미지를
확대·판독하며 blob 번호를 눈으로 맞추던 방식은 토큰 낭비이고 흘림체에서 자주 틀린다.** 대신
사람이 브라우저 GUI에서 클릭으로 라벨링한다. AI의 역할은 GUI 파일을 생성하고, 사람이 저장한
groups.json으로 build를 돌리는 것뿐이다.

## 절대 규칙

- **AI는 라벨링을 위해 test 이미지나 확대 crop을 Read하지 않는다.** 판독은 사람 몫이다.
  (검수 시각화 `*_gt_check.jpg`를 사람이 눈으로 보거나, 정 필요하면 사람이 지적한 박스 번호만
  받아 처리한다.)
- blob 번호·순서, 조각 이름 규칙은 `eval/label_helper.py`가 단일 출처다. GUI는 이와 일치하도록
  생성된다(검증됨). 규칙을 GUI에만 손대지 말 것.

## 절차

새 이미지든 기존 GT 수정이든 동일하다.

1. **GUI 생성** (AI가 실행):
   ```
   ai/venv/bin/python eval/label_gui.py test_images/<이미지>
   → eval/gt_work/<stem>_label.html
   ```
2. **브라우저에서 라벨링** (사람이 수행). WSL이면:
   ```
   explorer.exe "$(wslpath -w eval/gt_work/<stem>_label.html)"
   ```
   - **묶기 모드**: 조각(blob)을 클릭해 현재 음절에 넣고 `Enter`(또는 "새 음절")로 다음 음절
     시작. 같은 조각 재클릭 = 해제. 어느 음절에도 안 넣은 조각은 GT에서 제외된다.
   - **분할 모드**: 흘림으로 한 blob이 두 음절에 걸치면 blob을 선택 후 그 위 클릭으로 세로
     절단선(`Shift`+클릭 = 가로). 생긴 조각을 각 음절에 배정. 절단선 클릭 = 제거.
   - **기존 GT 수정**: "기존 groups.json 불러오기"로 `eval/gt_work/<stem>_groups.json`을
     불러와 고친다. (진행 상황은 localStorage에 자동 저장됨.)
   - 완료되면 "다운로드" 또는 "복사"로 `eval/gt_work/<stem>_groups.json` 저장.
3. **빌드** (AI가 실행):
   ```
   ai/venv/bin/python eval/label_helper.py build test_images/<이미지>
   → eval/gt/<stem>.json + eval/gt_work/<stem>_gt_check.jpg (검수 시각화)
   ```
4. **평가**:
   ```
   ai/venv/bin/python eval/evaluate_detection.py
   ```

## GT 라벨링 관례 (이 프로젝트에서 확정)

- **문장부호 제외**: 마침표·쉼표·물음표·느낌표는 음절이 아니므로 어느 음절에도 넣지 않는다
  (= GT 제외). 작은 점은 면적 필터로 이미 blob에서 빠지기도 한다.
- **긴 장식·연결 획 제외**: 흘림에서 한 획이 옆 글자 아래로 길게 뻗어 박스를 크게 왜곡하면,
  분할 후 그 꼬리 조각을 GT에서 제외한다. (예: test4 '복'의 ㄱ 꼬리, test7 '노'의 긴 ㄴ 밑변.)
- **영문/숫자**: 글자별로 1박스.
- **매직펜 등 굵은 획의 내부 윤곽 blob**: 해당 음절에 함께 포함.
- **절단 위치는 눈대중이 아니라 잉크 골짜기**: GUI에서 획이 얇아지는 지점(골짜기)에 절단선을
  긋는다. 글자폭 등분으로 찍으면 받침이 옆 음절로 넘어가는 오류가 난다(검수에서 걸렸던 실수).

## 검증·트러블슈팅

- **build가 "blobs에 없는 id" 에러**: groups.json의 조각 이름이 잘못됨. 보통 분할 안 한 blob에
  글자를 붙였거나(예: `12a`인데 splits에 12 없음), 오타. GUI가 생성한 걸 그대로 쓰면 안 난다.
- **build가 "그룹에 안 들어간 blob 경고"**: 정상. 제외한 문장부호·꼬리 조각이 여기 뜬다.
- **조각 이름 규칙 일치 검증**(도구 수정 시): GUI의 `piecesOf`와 `label_helper._split_blob`이
  같은 이름을 내야 한다. 규칙 = y 바깥·x 안쪽 순회, 잉크 없는 칸도 이름 인덱스 소비, 픽셀<128을
  잉크로 판정. test4의 splits로 대조하면 불일치 0이어야 한다.

## 관련 파일

- `eval/label_gui.py` — GUI(HTML) 생성기. `eval/label_gui_template.html`이 템플릿.
- `eval/label_helper.py` — blob 추출(`extract_blobs`)·분할(`_split_blob`)·빌드(`build`).
- `eval/evaluate_detection.py` — F1 평가. `eval/gt/*.json`을 자동으로 모두 읽는다.
- GT 관례·경위: `DEVLOG.md` 9막, `NORM_STROKE_RESEARCH.md`.
