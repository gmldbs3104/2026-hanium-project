/// 앱 전역 환경 설정
///
/// ★ 백엔드 연동 시 이 파일만 수정하면 됩니다 ★
///
/// [useMockApi] = true 로 두고 모든 API 응답을 가짜(mock) 데이터로 대체합니다.
/// 백엔드 팀이 엔드포인트를 완성하면 [useMockApi]를 false로, [apiBaseUrl]을
/// 실제 서버 주소로 바꾸면 됩니다.
class AppConfig {
  AppConfig._();

  static const bool useMockApi = false;

  static const String apiBaseUrl = 'http://localhost:8000';

  /// API 엔드포인트 모음
  /// (backend/app/api/v1/routes/*.py 실제 코드 기준, 2026-07 확인)
  static const String canvasAnalyzeEndpoint = '/api/v1/canvas/analyze';
  static const String imagePreprocessEndpoint = '/api/v1/image/preprocess';
  static const String dashboardEndpoint = '/api/v1/dashboard';

  // ---- 로그인 (SFR-001) ----
  // 백엔드는 Firebase ID Token 검증만 수행하고, 자체 JWT는 발급하지 않는다.
  // (backend/app/api/v1/routes/auth.py, app/core/firebase.py 참고)
  // 이후 인증이 필요한 모든 요청은 Firebase ID Token을 그대로
  // Authorization: Bearer {firebase_id_token} 헤더로 보낸다.
  static const String authLoginEndpoint = '/api/v1/auth/login';
  // REQ-009-7: 계정 삭제 요청 (HTTP DELETE, 인증 필요).
  // ⚠️ 백엔드 미구현 — 실제 데이터(DB 레코드/S3 이미지/Firebase 사용자) 영구 삭제는
  //    백엔드가 수행하며, 엔드포인트 경로·응답 스펙은 협의 필요 (임시로 REST 관례를 따름).
  static const String authDeleteAccountEndpoint = '/api/v1/auth/account';

  // 상세환경설정 "데이터 초기화" (mypage_upgrade.md 3.4-1, HTTP DELETE, 인증 필요).
  // ⚠️ 백엔드 미구현 — 계정은 유지한 채 세션/점수 이력 등 학습 기록만 지우는 엔드포인트가
  //    아직 없다(계정 삭제 API와는 다름). 경로는 REST 관례를 따른 임시값이라 백엔드와
  //    협의 후 확정 필요 (settings_api_service.dart 참고).
  static const String resetHistoryEndpoint = '/api/v1/user/history';

  // ---- 캔버스 모드 파이프라인 (SFR-003C ~ SFR-007) ----
  static String canvasGroupEndpoint(String sessionId) =>
      '/api/v1/canvas/$sessionId/group';
  static String canvasAnalyzeDetailEndpoint(String sessionId) =>
      '/api/v1/canvas/$sessionId/analyze-detail';
  static String canvasFeedbackEndpoint(String sessionId) =>
      '/api/v1/canvas/$sessionId/feedback';
  // SFR-009: 학습 결과 저장 확인 (피드백 화면 "학습 기록 저장" 탭 시 트리거)
  static String canvasConfirmEndpoint(String sessionId) =>
      '/api/v1/canvas/$sessionId/confirm';

  // ---- 이미지 모드 파이프라인 (SFR-003I ~ SFR-007) ----
  static String imageDetectEndpoint(String sessionId) =>
      '/api/v1/image/$sessionId/detect';
  static String imageAnalyzeEndpoint(String sessionId) =>
      '/api/v1/image/$sessionId/analyze';
  static String imageFeedbackEndpoint(String sessionId) =>
      '/api/v1/image/$sessionId/feedback';
  // SFR-009: 학습 결과 저장 확인 (save_image 동의 여부 포함)
  static String imageConfirmEndpoint(String sessionId) =>
      '/api/v1/image/$sessionId/confirm';

  /// mock 응답 지연 시간
  static const Duration mockDelay = Duration(milliseconds: 800);
}
