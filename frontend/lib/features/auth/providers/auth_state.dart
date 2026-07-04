/// 로그인 제공자 종류
enum AuthProviderType { google, kakao }

extension AuthProviderTypeValue on AuthProviderType {
  /// backend LoginRequest.provider 문자열 값 ("google" | "kakao")
  String get value => name;
}

/// 사용자 프로필
/// (backend/app/schemas/user.py UserOut 스키마와 1:1 대응)
class UserProfile {
  final String id;
  final String email;
  final String? name;
  final String? profileImageUrl;
  final String provider;

  const UserProfile({
    required this.id,
    required this.email,
    required this.provider,
    this.name,
    this.profileImageUrl,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] as String,
      email: json['email'] as String,
      name: json['name'] as String?,
      profileImageUrl: json['profile_image_url'] as String?,
      provider: json['provider'] as String,
    );
  }
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
