# frontend (Flutter 프론트엔드 - 오늘 작업분)

2026 한이음 - AI 손글씨 교정 플랫폼의 Flutter 프론트엔드입니다.
오늘(작업일) 기준으로 아래 세 가지가 구현되어 있습니다.

1. 로그인 화면 (UI 완성, 실제 Firebase 연동은 주석 처리 / 현재는 mock 로그인)
2. 메인 화면 + 캔버스/이미지 모드 분기 라우팅
3. API 연결 (mock 모드, 백엔드 준비되면 설정 한 줄만 바꾸면 전환됨) + 기본 UI 연결

---

## 1. 실행 전 준비 (최초 1회만)

이 폴더에는 Dart 코드(`lib/`)와 `pubspec.yaml`만 들어있고,
Android/iOS 네이티브 프로젝트 폴더(`android/`, `ios/`)는 포함되어 있지 않습니다.
(용량이 크고, Flutter SDK 버전에 따라 달라지는 파일이라 직접 생성하는 게 더 안전합니다)

아래 순서로 한 번만 실행하면 됩니다.

```bash
# 1. 이 폴더로 이동
cd frontend

# 2. Flutter가 설치되어 있는지 확인 (3.x 버전 권장)
flutter --version

# 3. android/, ios/ 등 네이티브 프로젝트 폴더 생성
#    (이미 있는 lib/, pubspec.yaml은 덮어쓰지 않습니다)
flutter create . --project-name frontend --org com.hanium

# 4. 패키지 설치
flutter pub get
```

> Flutter가 설치되어 있지 않다면: https://docs.flutter.dev/get-started/install 참고
> `flutter doctor` 명령으로 설치 상태를 점검할 수 있습니다.

## 2. 실행

```bash
# 연결된 기기/에뮬레이터 확인
flutter devices

# 실행 (예: 첫 번째 기기에서)
flutter run
```

- **카메라(실전 모드)는 실제 기기 또는 카메라가 있는 에뮬레이터에서만 정상 동작**합니다.
  카메라가 없는 환경(예: 데스크톱 Chrome 등)에서는 자동으로 "카메라 사용 불가" 안내가 뜨고,
  mock 데이터로 화면 흐름(분석 → 결과 화면)만 계속 테스트할 수 있게 처리되어 있습니다.
- 로그인 화면에서 Google/카카오 버튼을 누르면 실제 인증 없이 **mock 계정으로 즉시 로그인**됩니다.

## 3. 폴더 구조

```
lib/
  core/                    # 앱 전역 설정 (API 주소, 테마)
    app_config.dart        # ★ 백엔드 연동 시 가장 먼저 볼 파일
    app_theme.dart
  features/
    auth/                  # 로그인 (SFR-001)
    home/                  # 메인 화면, 모드 분기 (SFR-002)
    canvas_mode/            # 캔버스 모드 전용 (SFR-003C) - 이미지 모드와 코드 공유 없음
    image_mode/             # 이미지 모드 전용 (SFR-003I) - 캔버스 모드와 코드 공유 없음
    feedback/               # 분석 결과 화면 (SFR-007, 1차 버전)
  shared/
    router/app_router.dart  # go_router 설정 + 로그인 가드
    services/api_client.dart # 실제 HTTP 통신 담당 (백엔드 붙을 때 이 클래스를 통해 통신)
  main.dart
```

## 4. 백엔드 연동 시 바꿔야 할 부분 (★ 중요)

`lib/core/app_config.dart` 파일 하나만 수정하면 됩니다.

```dart
static const bool useMockApi = true;   // → false 로 변경
static const String apiBaseUrl = 'http://localhost:8000'; // → 실제 서버 주소로 변경
```

각 기능별 서비스 파일(`canvas_api_service.dart`, `image_api_service.dart`)은
`useMockApi` 값에 따라 자동으로 mock ↔ 실제 API 호출을 전환하도록 이미 분기되어 있어서,
**다른 코드는 수정할 필요가 없습니다.**

소셜 로그인(Google/Kakao) 실제 연동 코드는
`lib/features/auth/providers/auth_controller.dart` 안에 주석으로 미리 작성되어 있습니다.
Firebase 프로젝트 설정 후 `pubspec.yaml`의 firebase 관련 패키지 주석을 해제하고,
주석 처리된 코드 블록을 활성화하면 됩니다.

## 5. 알려진 제약 / TODO

- 카카오 로그인은 백엔드의 Firebase Custom Token 발급 엔드포인트가 필요합니다 (협의 필요).
- 대시보드(SFR-008), 교정 오버레이 렌더링(SFR-007 상세), 데이터 저장(SFR-009)은
  다음 작업 범위입니다. 현재는 라우팅 자리만 잡아둔 placeholder 화면입니다.
