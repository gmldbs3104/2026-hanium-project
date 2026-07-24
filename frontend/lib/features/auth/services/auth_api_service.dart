import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../providers/auth_state.dart';

/// 로그인 API 서비스 (SFR-001, backend/app/api/v1/routes/auth.py 기준)
///
/// 백엔드는 Firebase ID Token을 검증해 유저를 upsert하고 프로필만 돌려준다.
/// 자체 JWT를 발급하지 않으므로, 이후 인증이 필요한 요청은 Firebase가 발급한
/// id_token을 그대로 Authorization 헤더에 담아 보낸다 (토큰 갱신도 Firebase SDK가 처리).
///
/// canvas_api_service.dart / image_api_service.dart 와 동일한 패턴:
/// [AppConfig.useMockApi] 가 true인 동안은 mock 응답으로 화면 흐름을 테스트한다.
class AuthApiService {
  /// POST /api/v1/auth/login
  static Future<UserProfile> login({
    required AuthProviderType provider,
    required String idToken,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockLogin(provider);
    }

    final response = await ApiClient.post(
      AppConfig.authLoginEndpoint,
      {
        'provider': provider.value,
        'id_token': idToken,
      },
    );
    return UserProfile.fromJson(response);
  }

  /// DELETE /api/v1/auth/account (REQ-009-7)
  ///
  /// 계정 삭제 요청을 백엔드에 보낸다. 실제 데이터(DB 레코드/S3 이미지/Firebase 사용자)의
  /// 영구 삭제는 백엔드가 수행하며(30일 이내), 프론트는 요청 트리거와 로컬 세션 정리만 담당한다.
  /// 인증 필요: Firebase ID Token을 Authorization 헤더로 전달.
  static Future<void> deleteAccount({required String? idToken}) async {
    if (AppConfig.useMockApi) {
      await Future.delayed(AppConfig.mockDelay);
      return;
    }

    if (idToken == null) {
      throw ApiException('로그인이 필요합니다. 다시 로그인 후 시도해주세요.');
    }
    await ApiClient.delete(AppConfig.authDeleteAccountEndpoint, authToken: idToken);
  }

  /// ===== Mock 구현 =====
  static Future<UserProfile> _mockLogin(AuthProviderType provider) async {
    await Future.delayed(AppConfig.mockDelay);

    return UserProfile(
      id: 'mock-${provider.value}-user-id',
      email: 'test.user@${provider.value}.com',
      name: provider == AuthProviderType.google ? '테스트 사용자' : '테스트 사용자(Kakao)',
      profileImageUrl: null,
      provider: provider.value,
    );
  }
}
