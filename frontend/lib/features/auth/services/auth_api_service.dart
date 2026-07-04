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
