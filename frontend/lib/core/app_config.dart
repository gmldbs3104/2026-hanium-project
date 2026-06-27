/// 앱 전역 환경 설정
///
/// ★ 백엔드 연동 시 이 파일만 수정하면 됩니다 ★
///
/// 지금은 백엔드 API가 아직 구현되지 않은 상태라
/// [useMockApi] = true 로 두고 모든 API 응답을 가짜(mock) 데이터로 대체합니다.
///
/// 백엔드 팀이 엔드포인트를 완성하면:
///   1. [useMockApi] 를 false 로 변경
///   2. [apiBaseUrl] 을 실제 서버 주소로 변경
/// 이 두 가지만 바꾸면 모든 화면이 실제 서버와 통신하도록 전환됩니다.
/// (서비스 레이어 호출부 코드는 변경할 필요가 없습니다.)
class AppConfig {
  AppConfig._();

  /// 백엔드가 준비되지 않은 동안 true.
  /// true 인 경우 모든 ApiService 호출은 가짜 응답을 반환합니다.
  static const bool useMockApi = true;

  /// 백엔드 서버 주소
  /// requirement 문서 기준 FastAPI 서버, 로컬 실행 시 기본 포트 8000
  /// 실제 배포 주소가 정해지면 이 값을 변경하세요.
  static const String apiBaseUrl = 'http://localhost:8000';

  /// API 엔드포인트 모음 (requirement 2차 문서 기준)
  static const String canvasAnalyzeEndpoint = '/api/v1/canvas/analyze';
  static const String imagePreprocessEndpoint = '/api/v1/image/preprocess';
  static const String authVerifyEndpoint = '/api/v1/auth/verify';
  static const String dashboardEndpoint = '/api/v1/dashboard';

  /// mock 응답 지연 시간 (실제 네트워크 호출처럼 로딩 UI를 테스트하기 위함)
  static const Duration mockDelay = Duration(milliseconds: 800);
}
