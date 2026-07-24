import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
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
        await _loginWithBackend(AuthProviderType.google, idToken: 'mock-id-token');
        return;
      }

      // ===== 실제 Firebase + Google 로그인 =====
      final googleUser = await _googleSignIn.signIn();
      if (googleUser == null) {
        // 사용자가 계정 선택 창을 닫아 취소함 → 에러가 아니므로 조용히 초기 상태로
        state = const AuthInitial();
        return;
      }
      final googleAuth = await googleUser.authentication;
      final credential = GoogleAuthProvider.credential(
        accessToken: googleAuth.accessToken,
        idToken: googleAuth.idToken,
      );
      final userCredential = await FirebaseAuth.instance.signInWithCredential(credential);

      // REQ-001-1/2: Firebase ID Token 확보. 강제 언랩 대신 null을 명시적으로 처리한다.
      final firebaseIdToken = await userCredential.user?.getIdToken();
      if (firebaseIdToken == null) {
        state = const AuthError('로그인 토큰을 발급받지 못했습니다. 잠시 후 다시 시도해주세요.');
        return;
      }

      await _loginWithBackend(AuthProviderType.google, idToken: firebaseIdToken);
    } on PlatformException catch (e) {
      // google_sign_in 플러그인이 던지는 예외 (취소는 에러로 취급하지 않음)
      if (_isCancellation(e)) {
        state = const AuthInitial();
        return;
      }
      debugPrint('[Auth] Google sign-in PlatformException(${e.code}): ${e.message}');
      state = AuthError(_googleSignInErrorMessage(e));
    } on FirebaseAuthException catch (e) {
      // Firebase 자격 증명 교환 단계에서 발생하는 예외
      debugPrint('[Auth] Google sign-in FirebaseAuthException(${e.code}): ${e.message}');
      state = AuthError(_firebaseAuthErrorMessage(e));
    } catch (e, st) {
      // 그 외 예상치 못한 예외 — 원인을 로그로 남기고 일반 메시지로 안내
      debugPrint('[Auth] Google sign-in unexpected error: $e\n$st');
      state = const AuthError('Google 로그인에 실패했습니다. 다시 시도해주세요.');
    }
  }

  Future<void> signInWithKakao() async {
    state = const AuthLoading();
    try {
      if (AppConfig.useMockApi) {
        await _loginWithBackend(AuthProviderType.kakao, idToken: 'mock-id-token');
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

  /// REQ-009-7: 계정 삭제. 백엔드에 삭제 요청을 보낸 뒤 로컬 세션을 정리한다.
  /// 실제 데이터(DB/S3/Firebase 사용자) 삭제는 백엔드가 수행한다.
  ///
  /// ⚠️ 진행 중 [AuthLoading]으로 바꾸지 않는다 — 라우터 가드가 인증 상태를
  ///    "로그인 안 됨"으로 보고 삭제 완료 전에 /login 으로 튕겨버리기 때문이다.
  ///    로딩 표시는 UI(다이얼로그)에서 처리하고, 여기서는 성공 시에만 상태를 바꾼다.
  /// 성공하면 [AuthInitial]로 전환되어 라우터가 자동으로 /login 으로 되돌린다.
  /// 반환값: 삭제 성공 여부 (실패 시 인증 상태를 유지해 사용자가 홈에 남도록 함).
  Future<bool> deleteAccount() async {
    try {
      final idToken = await getCurrentIdToken();
      await AuthApiService.deleteAccount(idToken: idToken);

      // 실연동 시 로컬 소셜 로그인 세션도 정리 (Firebase 사용자 자체 삭제는 백엔드 Admin SDK 담당)
      if (!AppConfig.useMockApi) {
        await _googleSignIn.signOut();
      }

      state = const AuthInitial();
      return true;
    } catch (e, st) {
      debugPrint('[Auth] deleteAccount error: $e\n$st');
      return false;
    }
  }

  /// 에러 상태를 초기 상태로 되돌림 (에러 메시지 닫기 등에서 사용)
  void clearError() {
    if (state is AuthError) {
      state = const AuthInitial();
    }
  }

  /// Firebase ID Token을 백엔드(/api/v1/auth/login)에 전달해 유저 프로필을 받고
  /// 인증 완료 상태로 전환한다. mock/실연동, Google/Kakao 공통 경로.
  Future<void> _loginWithBackend(
    AuthProviderType provider, {
    required String idToken,
  }) async {
    final user = await AuthApiService.login(provider: provider, idToken: idToken);
    state = AuthAuthenticated(user);
  }

  /// google_sign_in이 던지는 "사용자 취소" 계열 예외인지 판별한다.
  /// (취소는 실패가 아니므로 에러 배너를 띄우지 않고 초기 상태로 되돌린다)
  bool _isCancellation(PlatformException e) {
    const cancelCodes = {'sign_in_canceled', 'sign_in_cancelled', 'canceled', 'cancelled'};
    return cancelCodes.contains(e.code);
  }

  /// google_sign_in PlatformException → 사용자용 한국어 메시지 (REQ-001-4)
  String _googleSignInErrorMessage(PlatformException e) {
    switch (e.code) {
      case 'network_error':
        return '인터넷 연결을 확인한 뒤 다시 시도해주세요.';
      case 'sign_in_failed':
        return 'Google 로그인에 실패했습니다. 다시 시도해주세요.';
      default:
        return 'Google 로그인에 실패했습니다. 다시 시도해주세요.';
    }
  }

  /// FirebaseAuthException → 사용자용 한국어 메시지 (REQ-001-4)
  String _firebaseAuthErrorMessage(FirebaseAuthException e) {
    switch (e.code) {
      case 'network-request-failed':
        return '인터넷 연결을 확인한 뒤 다시 시도해주세요.';
      case 'account-exists-with-different-credential':
        return '이미 다른 방법으로 가입된 이메일입니다. 기존 로그인 방법으로 시도해주세요.';
      case 'invalid-credential':
        return '인증 정보가 만료되었거나 올바르지 않습니다. 다시 시도해주세요.';
      case 'user-disabled':
        return '사용이 중지된 계정입니다. 관리자에게 문의해주세요.';
      default:
        return '로그인 처리 중 문제가 발생했습니다. 다시 시도해주세요.';
    }
  }
}

final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);

/// 현재 로그인 여부만 간단히 확인하기 위한 파생 Provider (라우터 가드에서 사용)
final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(authControllerProvider) is AuthAuthenticated;
});
