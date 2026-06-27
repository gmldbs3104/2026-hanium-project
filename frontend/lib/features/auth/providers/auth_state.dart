/// 로그인 제공자 종류
enum AuthProviderType { google, kakao }

/// 사용자 프로필 (SFR-001 Outputs 기준: UID, 이름, 이메일, 프로필 이미지 URL)
class UserProfile {
  final String uid;
  final String name;
  final String email;
  final String? photoUrl;

  const UserProfile({
    required this.uid,
    required this.name,
    required this.email,
    this.photoUrl,
  });
}

/// 인증 상태 (로그인 전 / 로딩 중 / 로그인 완료 / 에러)
sealed class AuthState {
  const AuthState();
}

class AuthInitial extends AuthState {
  const AuthInitial();
}

class AuthLoading extends AuthState {
  const AuthLoading();
}

class AuthAuthenticated extends AuthState {
  final UserProfile user;
  const AuthAuthenticated(this.user);
}

class AuthError extends AuthState {
  final String message;
  const AuthError(this.message);
}
