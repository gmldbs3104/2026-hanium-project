# 피드백 응답 신규 필드 계약 (AI 분석 · 점수 카드)

`/feedback` 결과 화면 리디자인(목업 2단 레이아웃)에 맞춰, 프론트엔드가 **캔버스/이미지 피드백 응답에서 3개 필드를 추가로 읽도록** 준비되었습니다. 백엔드가 이 필드들을 내려주면 화면이 자동으로 채워집니다.

- 대상 엔드포인트
  - `GET /api/v1/canvas/{canvas_session_id}/feedback`
  - `GET /api/v1/image/{image_session_id}/feedback`
- 프론트 파서: `WeakHabit.listFromJson()`, `CanvasFeedbackResponse.fromJson()`, `ImageFeedbackResponse.fromJson()`
- **모두 선택(optional) 필드입니다.** 응답에 없으면 프론트가 안전한 기본값으로 처리합니다(앱이 깨지지 않음). 현재 이 필드들이 없을 때 화면은 "AI 취약 습관 분석을 준비 중이에요."를 표시합니다.

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
