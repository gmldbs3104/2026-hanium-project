# 피드백 응답 신규 필드 계약 (AI 분석 · 점수 카드)

`/feedback` 결과 화면 리디자인(목업 2단 레이아웃)에 맞춰, 프론트엔드가 **캔버스/이미지 피드백 응답에서 3개 필드를 추가로 읽도록** 준비되었습니다. 백엔드가 이 필드들을 내려주면 화면이 자동으로 채워집니다.

- 대상 엔드포인트
  - `GET /api/v1/canvas/{canvas_session_id}/feedback`
  - `GET /api/v1/image/{image_session_id}/feedback`
- 프론트 파서: `WeakHabit.listFromJson()`, `CanvasFeedbackResponse.fromJson()`, `ImageFeedbackResponse.fromJson()`
- **모두 선택(optional) 필드입니다.** 응답에 없으면 프론트가 안전한 기본값으로 처리합니다(앱이 깨지지 않음).

> ### ⚠️ 갱신 2026-09-02 — 폴백 동작이 바뀌었습니다
>
> `weak_habits`는 여전히 **백엔드 스키마에 없어 항상 빈 배열**입니다. 종전에는 그래서
> 우측 카드가 늘 "AI 취약 습관 분석을 준비 중이에요."만 띄웠는데, 지금은 **이미 있는
> 판정 결과로 카드를 채웁니다.** 이 계약이 구현되면 그 위에 얹히므로 이 문서는 유효합니다.
>
> 현재 카드가 그리는 것(위에서부터 순서대로):
> 1. `weak_habits`가 있으면 → 배지 목록 (이 계약)
> 2. **빨간 박스가 있으면** → 그 사유 목록 — 캔버스는 성분 단위(`component_boxes`),
>    이미지는 글자 단위(`char_boxes`)
> 3. **80점 미만 항목이 있으면** → `feedback_items`의 경고 문구 **(이미지 모드만)**
> 4. 둘 다 없으면 → "모든 항목이 기준을 잘 지켰어요! 훌륭해요 🎉"
> 5. 아무것도 못 쟀으면 → "AI 취약 습관 분석을 준비 중이에요."
>
> 2와 3은 **함께** 표시됩니다. 자간·행간은 글자 하나에 귀속되지 않아 박스를 안 치므로,
> 박스만 보고 판단하면 자간이 60점이어도 "훌륭해요"가 떴습니다(2026-09-02 사용자 지적).
>
> ### ⚠️ `feedback_items`의 의미가 두 모드에서 다릅니다
>
> | 모드 | `target_id` | 한 항목이 뜻하는 것 | `severity` 기준 |
> |---|---|---|---|
> | 캔버스 | `char_id` | **글자 하나**의 종합 평 | 그 글자의 **종합 점수**(80/50) |
> | 이미지 | `"global"` | **채점 항목 하나**(크기·기울기·줄정렬·자간·행간) | 그 **항목 점수 80점** |
>
> 그래서 위 3번은 **이미지 모드에서만** 씁니다. 캔버스 것을 섞으면 "종합 82점이라 good인데
> 성분 박스는 빨강"이라는 불일치가 되살아납니다(2026-09-01에 고친 것).
> 이미지 모드는 항상 **6문장**이 나갑니다 — 종합 1(`achievement_message`) + 항목 5.

## 추가할 응답 필드

| 필드 | 타입 | 기본값(없을 때) | 화면 표시 위치 |
|---|---|---|---|
| `weak_habits` | array of object | `[]` (빈 패널 안내문) | 우측 하단 "AI 분석: 취약한 습관" 배지 |
| `target_score` | int | `90` | 우측 상단 점수 카드 "목표: N점" + 진행바 |
| `score_trend` | int (부호 있음) | `null` (추세 배지 숨김) | 점수 카드 우상단 ↗/↘ 배지 |

### `weak_habits` 항목 스키마

```json
{
  "label": "선 이탈",       // (필수) 화면에 표시할 습관 이름
  "count": 3,               // (선택) 감지 횟수 → 배지에 "3회"로 표시, 없으면 횟수 생략
  "severity": "warning"     // (선택) "warning" | "error", 기본 "warning"
}
```

### 전체 응답 예시 (canvas)

```json
{
  "canvas_session_id": "abc123",
  "mode": "canvas",
  "overall_score": 45,
  "achievement_message": "좋아요! 조금만 더 연습하면 완벽해질 거예요.",
  "feedback_items": [ /* 기존과 동일 */ ],

  "weak_habits": [
    { "label": "선 이탈", "count": 3, "severity": "warning" },
    { "label": "좌상향 기울기 심함", "count": 2, "severity": "warning" },
    { "label": "밸런스 불균형", "count": 6, "severity": "error" }
  ],
  "target_score": 90,
  "score_trend": 5
}
```

`score_trend`는 직전 시도 대비 점수 변화량입니다(예: `+5`면 ↗ +5, `-3`이면 ↘ -3). 계산할 이력이 없으면 필드를 생략하거나 `null`로 두면 됩니다.

## 백엔드 작업 메모

- `schemas/canvas.py`의 `CanvasFeedbackResponse`, `schemas/image.py`의 `ImageFeedbackResponse`에 위 3개 필드를 optional로 추가.
- `weak_habits`는 SFR-005C/005I 분석 결과(획순 오류·자간·크기·기울기·줄 정렬 등)를 카테고리+횟수로 집계해 생성하면 됩니다. (현재 프론트는 `feedback_items`에서 이를 직접 유도하지 않습니다 — 백엔드 집계 결과를 그대로 신뢰합니다.)
- `target_score`는 사용자 목표/기본값(90) 중 택. `score_trend`는 직전 세션 점수와의 차이.

> 필드 이름은 snake_case 기준이며, 프론트는 하위호환으로 `weakHabits`(camelCase)도 함께 인식합니다.
