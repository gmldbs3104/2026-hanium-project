import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';

/// 상세환경설정 관련 API 서비스 (mypage_upgrade.md 3.4-1)
///
/// ★ 백엔드 연동 방법 ★
/// [resetHistory]가 부르는 [AppConfig.resetHistoryEndpoint]는 아직 백엔드에 없다
/// (2026-08-11 기준). 아래는 백엔드가 이렇게 구현되는 걸 가정하고 미리 연결해둔
/// 프론트 코드다 — 백엔드에 이 엔드포인트가 생기기 전까지는 실제 호출 시
/// 404(또는 연결 실패)로 실패한다:
///   DELETE /api/v1/user/history  (Authorization: Bearer {firebase_id_token})
///   - 계정 자체는 유지하고, 그 유저의 세션/점수 이력(CanvasAnalysisResult 등)만
///     전부 삭제한다 — REQ-009-7의 계정 삭제(auth.py, DELETE /api/v1/auth/account)와는
///     다른 엔드포인트다.
///   - 성공 시 200/204, 본문 없음.
class SettingsApiService {
  /// 학습 기록(세션·점수 이력) 전체 삭제. 계정 자체는 삭제하지 않는다.
  static Future<void> resetHistory({required String? idToken}) async {
    if (AppConfig.useMockApi) {
      await Future.delayed(AppConfig.mockDelay);
      return;
    }

    if (idToken == null) {
      throw ApiException('로그인이 필요합니다. 다시 로그인 후 시도해주세요.');
    }
    await ApiClient.delete(AppConfig.resetHistoryEndpoint, authToken: idToken);
  }
}
