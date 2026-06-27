import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'auth_state.dart';

/// 인증 상태를 관리하는 Riverpod Notifier
///
/// SFR-001 (사용자 인증 및 계정 관리) 대응
///
/// 지금은 백엔드/Firebase 연동 전이라 [signInWithGoogle], [signInWithKakao]
/// 모두 가짜 사용자 정보로 즉시 로그인 성공 처리합니다.
/// 실제 연동 코드는 각 메서드 하단에 주석으로 남겨두었으니,
/// firebase_core / firebase_auth / google_sign_in 패키지를
/// pubspec.yaml 에서 주석 해제한 뒤 교체하면 됩니다.
class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthInitial();

  Future<void> signInWithGoogle() async {
    state = const AuthLoading();
    try {
      // ===== Mock 처리 (현재 사용 중) =====
      await Future.delayed(const Duration(milliseconds: 600));
      state = const AuthAuthenticated(
        UserProfile(
          uid: 'mock-google-uid-001',
          name: '테스트 사용자',
          email: 'test.user@gmail.com',
          photoUrl: null,
        ),
      );

      // ===== 실제 Firebase 연동 코드 (백엔드/Firebase 준비되면 위 mock 블록 삭제하고 주석 해제) =====
      //
      // final googleUser = await GoogleSignIn().signIn();
      // if (googleUser == null) {
      //   state = const AuthInitial(); // 사용자가 로그인 취소
      //   return;
      // }
      // final googleAuth = await googleUser.authentication;
      // final credential = GoogleAuthProvider.credential(
      //   accessToken: googleAuth.accessToken,
      //   idToken: googleAuth.idToken,
      // );
      // final userCredential =
      //     await FirebaseAuth.instance.signInWithCredential(credential);
      // final idToken = await userCredential.user!.getIdToken();
      //
      // // 백엔드 검증: requirement Action ④
      // // await ApiClient.post(AppConfig.authVerifyEndpoint, {'id_token': idToken});
      //
      // final firebaseUser = userCredential.user!;
      // state = AuthAuthenticated(
      //   UserProfile(
      //     uid: firebaseUser.uid,
      //     name: firebaseUser.displayName ?? '사용자',
      //     email: firebaseUser.email ?? '',
      //     photoUrl: firebaseUser.photoURL,
      //   ),
      // );
    } catch (e) {
      state = AuthError('Google 로그인에 실패했습니다. 다시 시도해주세요.');
    }
  }

  Future<void> signInWithKakao() async {
    state = const AuthLoading();
    try {
      // ===== Mock 처리 (현재 사용 중) =====
      await Future.delayed(const Duration(milliseconds: 600));
      state = const AuthAuthenticated(
        UserProfile(
          uid: 'mock-kakao-uid-001',
          name: '테스트 사용자(Kakao)',
          email: 'test.user@kakao.com',
          photoUrl: null,
        ),
      );

      // ===== 실제 Kakao + Firebase Custom Token 연동 코드 =====
      // (Kakao는 Firebase 기본 제공자가 아니므로 백엔드에서 커스텀 토큰을
      //  발급받아 교환하는 흐름이 필요합니다 - 백엔드 팀과 엔드포인트 협의 필요)
      //
      // final kakaoToken = await UserApi.instance.loginWithKakaoTalk();
      // final kakaoUser = await UserApi.instance.me();
      //
      // // 백엔드에 카카오 액세스 토큰을 보내 Firebase Custom Token을 받아온다
      // final response = await ApiClient.post('/api/v1/auth/kakao-custom-token', {
      //   'kakao_access_token': kakaoToken.accessToken,
      // });
      // final customToken = response['custom_token'];
      // final userCredential =
      //     await FirebaseAuth.instance.signInWithCustomToken(customToken);
      //
      // state = AuthAuthenticated(
      //   UserProfile(
      //     uid: userCredential.user!.uid,
      //     name: kakaoUser.kakaoAccount?.profile?.nickname ?? '사용자',
      //     email: kakaoUser.kakaoAccount?.email ?? '',
      //     photoUrl: kakaoUser.kakaoAccount?.profile?.profileImageUrl,
      //   ),
      // );
    } catch (e) {
      state = AuthError('카카오 로그인에 실패했습니다. 다시 시도해주세요.');
    }
  }

  void signOut() {
    state = const AuthInitial();
    // 실제 연동 시: FirebaseAuth.instance.signOut(); 등 추가
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
