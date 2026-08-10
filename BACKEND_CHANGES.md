# 백엔드 수정 내역 (2026-08-09~10 세션)

> 이 세션에서 백엔드 코드가 바뀐 곳은 **딱 2개 파일**이다. 둘 다 커밋 `98fae71`
> (DATA_FLOW.md §5 8·10번 연결)에서 바뀌었고, **기존 필드를 건드리지 않고 새 필드만
> 추가**했다 — 하위 호환 유지, 기존 클라이언트가 깨질 일 없음.

## 1. `backend/app/schemas/image.py`

응답 스키마에 필드 2개 추가.

| 스키마 | 추가된 필드 | 의미 |
|---|---|---|
| `ImagePreprocessResponse` | `preservation_mode: Optional[bool] = None` | `True`면 연한 글씨 보존 모드(잉크 재구성 시 `gentle_stretch` 적용) — 비침이 획과 함께 남을 수 있다. `False`면 비침 제거 모드 |
| `ImageAnalysisResponse` | `spacing_uniformity_score: Optional[int] = None` | 자간 균등성 점수 (AI가 5지표 중 하나로 이미 채점하지만 기존엔 응답에 없었음) |
| `ImageAnalysisResponse` | `line_spacing_uniformity_score: Optional[int] = None` | 행간 균등성 점수 (위와 동일한 이유) |

두 점수 필드는 글자/행 수가 부족해 AI가 측정을 생략한 경우 `None`이 온다(예: 3행 미만이면
행간 평가 자체가 생략됨).

## 2. `backend/app/api/v1/routes/image.py`

위 새 필드들을 실제로 채워서 응답에 넣는 로직.

- **`_metric_score()` 헬퍼 함수 신설** — AI의 `analyze_size_angle()`이 반환하는
  `metrics["spacing_uniformity"]` / `metrics["line_spacing_uniformity"]`는 측정 성공 시
  `{"score": ...}`, 측정 생략 시 `{"skipped": "사유"}` 형태라 이 둘을 분기해서 점수만 뽑거나
  `None`을 반환한다.
- **`POST /image/preprocess`** — `preservation_mode`를 `pre["applied_filters"]`
  (AI 전처리 어댑터가 이미 반환하던 값, `preprocess_image_full()`) 안에 `"gentle_stretch"`가
  포함돼 있는지로 판정해서 응답에 추가.
- **`POST /image/{id}/analyze`** — `_metric_score()`로 자간·행간 점수를 뽑아
  `ImageAnalysisResponse`와 세션 캐시(`session_data["analysis_results"]`, `/feedback`
  엔드포인트가 참조)에 함께 저장.

## 범위 밖 (참고)

- DB 컬럼 추가·Alembic 마이그레이션은 하지 않았다 — 이번엔 API 응답 레벨까지만 연결했고,
  대시보드에 자간·행간 점수를 누적하려면 `ImageAnalysisResult` 모델에 컬럼을 추가하는
  별도 작업이 필요하다.
- 캔버스 모드(§8 A·B·C·E·F: 획순 스텁, 필압·속도, 교정 플래그, 자간·크기 기준 통일)는
  이번 세션에서 백엔드를 건드리지 않았다 — `analyze-detail` 라우트를 AI의
  `analyze_canvas_writing()`로 통째로 갈아끼워야 하는 별도 규모의 작업이라 DATA_FLOW.md
  §8에 조사 결과만 남기고 보류했다.

## 관련 문서

- [DATA_FLOW.md](DATA_FLOW.md) §5 (8·9·10번), §8
