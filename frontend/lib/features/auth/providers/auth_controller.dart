import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';

import '../../../core/app_config.dart';
import '../services/auth_api_service.dart';
import 'auth_state.dart';

/// 인증 상태를 관리하는 Riverpod Notifier
///
/// SFR-001 (사용자 인증 및 계정 관리) 대응
///
/// 실제 흐름 (backend/app/api/v1/routes/auth.py 기준):
///  1. Firebase Auth로 로그인해서 Firebase ID Token을 얻는다 (Google/Kakao 공통)
///  2. 그 id_token을 POST /api/v1/auth/login 으로 백엔드에 전달해 유저 프로필을 받는다
///  3. 백엔드는 JWT를 별도로 발급하지 않으므로, 이후 인증 요청에는 Firebase가 발급한
///     id_token을 그대로 사용한다 (만료 시 Firebase SDK가 자동 갱신)
///
/// [AppConfig.useMockApi] 가 true인 동안은 Firebase 호출 자체를 건너뛰고
/// [AuthApiService]의 mock 응답으로 즉시 로그인 처리한다.
/// (Firebase 프로젝트 설정 없이도 화면 흐름을 테스트할 수 있도록 하기 위함)
class AuthController extends Notifier<AuthState> {
  final GoogleSignIn _googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);

  @override
  AuthState build() => const AuthInitial();

  Future<void> signInWithGoogle() async {
    state = const AuthLoading();
    try {
      if (AppConfig.useMockApi) {
        final user = await AuthApiService.login(
          provider: AuthProviderType.google,
          idToken: 'mock-id-token',
        );
        state = AuthAuthenticated(user);
        return;
      }

      // ===== 실제 Firebase + Google 로그인 =====
      final googleUser = await _googleSignIn.signIn();
      if (googleUser == null) {
        state = const AuthInitial(); // 사용자가 로그인 취소
        return;
      }
      final googleAuth = await googleUser.authentication;
      final credential = GoogleAuthProvider.credential(
        accessToken: googleAuth.accessToken,
        idToken: googleAuth.idToken,
      );
      final userCredential = await FirebaseAuth.instance.signInWithCredential(credential);
      final firebaseIdToken = await userCredential.user!.getIdToken();

      final user = await AuthApiService.login(
        provider: AuthProviderType.google,
        idToken: firebaseIdToken!,
      );
      state = AuthAuthenticated(user);
    } catch (e) {
      state = const AuthError('Google 로그인에 실패했습니다. 다시 시도해주세요.');
    }
  }

  Future<void> signInWithKakao() async {
    state = const AuthLoading();
    try {
      if (AppConfig.useMockApi) {
        final user = await AuthApiService.login(
          provider: AuthProviderType.kakao,
          idToken: 'mock-id-token',
        );
        state = AuthAuthenticated(user);
        return;
      }

      // ===== 실제 Kakao 로그인 =====
      // ⚠️ TODO (백엔드 협의 필요): Firebase는 Kakao를 기본 제공자로 지원하지 않는다.
      // 카카오 로그인 후 Firebase ID Token을 얻으려면, 백엔드에 카카오 access_token을
      // 보내 Firebase Custom Token을 발급받는 엔드포인트가 필요한데 현재 백엔드에는
      // 없다 (auth.py는 /login 하나뿐, provider="kakao"여도 id_token 필드를 그대로 받음).
      // 백엔드에 예: POST /api/v1/auth/kakao/custom-token 같은 엔드포인트 추가 후
      // 아래를 구현해야 한다.
      //
      // final kakaoToken = await UserApi.instance.loginWithKakaoTalk();
      // final customTokenResponse = await ApiClient.post(
      //   '/api/v1/auth/kakao/custom-token',
      //   {'access_token': kakaoToken.accessToken},
      // );
      // final userCredential = await FirebaseAuth.instance
      //     .signInWithCustomToken(customTokenResponse['custom_token']);
      // final firebaseIdToken = await userCredential.user!.getIdToken();
      // final user = await AuthApiService.login(
      //   provider: AuthProviderType.kakao,
      //   idToken: firebaseIdToken!,
      // );
      // state = AuthAuthenticated(user);

      throw UnimplementedError('백엔드에 Kakao → Firebase Custom Token 발급 엔드포인트가 필요합니다.');
    } catch (e) {
      state = const AuthError('카카오 로그인에 실패했습니다. 다시 시도해주세요.');
    }
  }

  Future<void> signOut() async {
    if (!AppConfig.useMockApi) {
      await FirebaseAuth.instance.signOut();
      await _googleSignIn.signOut();
    }
    state = const AuthInitial();
  }

  /// 현재 Firebase ID Token 조회 (다른 인증 필요 API 호출 시 사용)
  /// mock 모드에서는 항상 null.
  Future<String?> getCurrentIdToken() async {
    if (AppConfig.useMockApi) return 'mock-id-token';
    return FirebaseAuth.instance.currentUser?.getIdToken();
  }

  /// 에러 상태를 초기 상태로 되돌림 (에러 메시지 닫기 등에서 사용)
  void clearError() {
    if (state is AuthError) {
      state = const AuthInitial();
    }
  }
}

final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);

/// 현재 로그인 여부만 간단히 확인하기 위한 파생 Provider (라우터 가드에서 사용)
final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(authControllerProvider) is AuthAuthenticated;
});
