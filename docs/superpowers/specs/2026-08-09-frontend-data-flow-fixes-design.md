# 프론트 데이터 유실 수정 (DATA_FLOW.md §4의 4·5·6·7번) 설계

> 작성일: 2026-08-09
> 대상: `frontend/lib/features/image_mode/`, `frontend/lib/features/canvas_mode/`, `frontend/lib/features/feedback/`, `frontend/lib/shared/services/api_client.dart`
> 관련: [DATA_FLOW.md](../../../DATA_FLOW.md) §4 "반드시 고쳐야 하는 불일치" 4·5·6·7번 (프론트 담당 항목)
> 범위: 3번(캔버스 글자 미전달)·8~11번(§5, 백엔드 담당)은 이번 작업 범위 밖.

## 1. 배경

DATA_FLOW.md는 AI·백엔드·프론트 세 파트가 주고받는 값을 대조해, 백엔드가 이미 보내는 값을 프론트가 쓰지 않거나(유실), 프론트가 백엔드가 못 받는 형식으로 보내는(오류) 지점을 정리한 문서다. §4 표의 4·5·6·7번이 프론트 단독으로 고칠 수 있는 항목이며, 이번 작업은 이 네 항목을 순서대로 고친다.

## 2. 항목별 설계

### 2.1 (4번) 오버레이 배경을 원본 사진 → 전처리 이미지로 교체

**문제.** `/image/preprocess` 응답의 `preprocessed_image_base64`(이진화·deskew 완료된 흑백 이미지, `backend/app/schemas/image.py:30`)는 이후 모든 좌표(글자 bounding box)의 기준 이미지인데, 프론트가 이 필드를 아예 파싱하지 않고 원본 촬영 사진(`imageBytes`) 위에 오버레이를 그린다. 괘선지에서 반 글자 밀림이 생기는 원인.

**변경.**
- `ImagePreprocessResult`(`frontend/lib/features/image_mode/models/image_result.dart`)에 `preprocessedImageBase64`(nullable String) 필드 추가, `fromJson`에서 파싱.
- 같은 응답의 `retake_required`(bool?) 필드도 함께 파싱 (2.3절 참고).
- `image_capture_screen.dart` `_captureAndSend()`: `/feedback` 라우트로 넘기는 `extra` 맵의 오버레이용 이미지를 전처리 PNG(base64 디코드한 바이트)로 교체. 원본 촬영 바이트(`bytes`)는 더 이상 오버레이에 쓰지 않는다.
- `feedback_screen.dart` `_buildImageOverlay()`: 배경 이미지를 전처리 이미지로 교체. `sourceWidth/sourceHeight`는 이미 전처리 후 크기(`result.width/height`) 기준이라 변경 불필요 — 지금은 오히려 원본 사진 크기와 좌표계가 어긋나 있었다.

**폐기.** 원본 컬러 사진을 오버레이 배경으로 쓰는 경로는 삭제. 컬러 배경이 필요해지면 백엔드가 별도 필드를 추가해야 하므로 이번 범위 밖.

### 2.2 (5번) 캔버스 크기값 정수화

**문제.** `CanvasMetadata.width/height`가 `double`(`frontend/lib/features/canvas_mode/models/stroke.dart:38-39`)로 선언되어, `canvas_input_screen.dart`가 `LayoutBuilder`의 `constraints.maxWidth/maxHeight`(레이아웃 픽셀 실측값, 화면 밀도에 따라 소수)를 그대로 실어 보낸다. 화면 크기에 따라 제출 실패(422 등) 가능.

**변경.**
- `CanvasMetadata.width/height` 타입을 `int`로 변경.
- `canvas_input_screen.dart`에서 `CanvasMetadata` 생성 시점에 `constraints.maxWidth.round()` / `.round()`로 정수화. 오버레이 좌표 매핑에 쓰는 `_canvasSize`(`Size`, double)는 그대로 유지 — 서버 전송 값만 정수 캐스팅.
- 백엔드 스키마(`backend/app/schemas/canvas.py CanvasMetadata.width/height: float`)는 정수도 그대로 받으므로 백엔드 변경 없음.

### 2.3 (6번) 카메라 실패 시 더미 데이터 전송 제거

**문제.** `image_capture_screen.dart`는 카메라 초기화 실패·권한 거부로 `_cameraUnavailable == true`가 되어도 촬영 버튼을 누르면 100바이트 더미(`List<int>.filled(100, 0)`)를 그대로 `/image/preprocess`에 전송한다(`isRealCapture = false`일 때 `_validateImage` 검증도 건너뜀). 백엔드는 422로 응답.

**결정.** 더미 전송 경로를 완전히 제거하고 차단 UI로 대체한다 (디버그 전용 우회는 두지 않음).

**변경.**
- `_captureAndSend()`에서 더미 바이트 생성 분기, `isRealCapture` 플래그, `_validateImage` 우회 로직 삭제 — 이 함수에는 이제 실제 촬영 바이트만 들어온다.
- `_cameraUnavailable`(또는 초기화 예외) 상태일 때 촬영 버튼 비활성화 + 안내 문구 표시. 카메라가 아예 없는 경우와 권한 거부를 구분할 수 있으면 문구도 구분(권한 거부 시 "설정에서 카메라 권한을 허용해주세요" 등).
- `_buildPreview()`의 "카메라 없이도 흐름을 테스트할 수 있습니다" 안내 주석·UI 제거.

### 2.4 (7번) 서버 오류 사유를 화면에 표시

**문제.** `api_client.dart`의 모든 요청 메서드가 실패 응답에서 `response.body`를 읽지 않고 `"요청이 실패했습니다 (상태코드)"` 고정 문구로 `ApiException`을 던진다. FastAPI가 `{"detail": "..."}` 형태(또는 422 검증 오류 시 `{"detail": [{"msg": "...", ...}, ...]}` 배열)로 보내는 실제 사유가 전부 버려진다.

**변경.**
- `ApiException`에 `serverMessage`(String?, nullable) 필드 추가.
- `api_client.dart`의 공통 오류 처리 지점에서 `response.body`를 JSON 파싱해 `detail`을 꺼낸다: 문자열이면 그대로, 리스트(pydantic validation error)면 각 원소의 `msg`를 join. 파싱 실패·필드 없음이면 `serverMessage`는 null로 두고 기존 고정 문구(`message`)로 폴백.
- 호출부 3곳 — `image_capture_screen.dart`, `canvas_input_screen.dart`, `feedback_screen.dart`(`_onConfirm`, `_loadFeedback`) — 의 `ApiException` catch 블록에서 사용자에게 보여주는 문자열을 `e.serverMessage ?? e.message`로 교체. `feedback_screen.dart`의 `_loadFeedback()`은 현재 `catch (e)`로 뭉뚱그려 고정 문구만 보여주는데, `on ApiException catch (e)`를 별도로 잡아 사유를 노출하고 그 외 예외만 기존 고정 문구를 유지.

## 3. 이번 범위에서 제외한 것

- DATA_FLOW.md §4 3번(캔버스 글자 미전달)·§5 8~11번은 백엔드 담당이거나 이번 요청(4·5·6·7번) 범위 밖.
- `s3_image_url`(응답에 있으나 프론트 미사용)은 사용자에게 노출할 이유가 없는 저장소 참조값이라 그대로 둔다.
- 오버레이 배경을 "회전만 한 컬러 이미지"로 하는 대안(§6.1)은 백엔드가 그런 필드를 보내지 않으므로 이번 범위 밖.

## 4. 테스트 관점

- 이미지 모드: 괘선 있는 종이로 촬영 → 오버레이 박스가 전처리(이진화) 이미지 위에서 글자와 정확히 겹치는지 육안 확인.
- 캔버스 모드: 여러 화면 크기(에뮬레이터 해상도 변경)에서 제출 시 422 없이 성공하는지 확인, 전송 payload의 width/height가 정수인지 확인.
- 카메라 권한을 거부한 상태로 앱 실행 → 촬영 버튼이 비활성화되고 안내 문구가 뜨는지, 어떤 요청도 서버로 나가지 않는지 확인.
- 의도적으로 실패하는 요청(예: 잘못된 이미지 포맷 업로드)을 보내 화면에 백엔드 `detail` 문구가 그대로 노출되는지 확인.
