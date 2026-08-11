import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 로컬 전용 프로필 수정 값(닉네임 / 프로필 사진).
///
/// ⚠️ 백엔드에 프로필 수정 API가 없다(2026-08-11 기준, mypage_upgrade.md 3.2 참고).
/// 그래서 이 값은 이 기기의 SharedPreferences에만 저장되고 서버로 전송되지 않는다 —
/// 다른 기기에서 로그인하거나 앱을 재설치하면 유지되지 않는다. 화면에서는
/// AuthController의 UserProfile.name 대신 이 값이 있으면 그걸 우선 표시한다.
/// 나중에 백엔드에 PATCH /api/v1/auth/profile 같은 엔드포인트가 생기면, 이 provider의
/// 로컬 저장 대신 그 응답을 UserProfile에 반영하는 방식으로 바꿔야 한다.
class ProfileOverride {
  final String? nickname;
  final String? photoBase64; // 카메라로 찍은 JPEG bytes, base64 인코딩

  const ProfileOverride({this.nickname, this.photoBase64});
}

class ProfileOverrideNotifier extends Notifier<ProfileOverride> {
  static const _nicknameKey = 'profile_override_nickname';
  static const _photoKey = 'profile_override_photo_base64';

  @override
  ProfileOverride build() {
    // SharedPreferences 접근은 비동기라 build()는 우선 빈 값을 반환하고,
    // 로드가 끝나면 state를 갱신한다(짧은 순간 기본 프로필이 보였다가 바뀔 수 있음).
    _load();
    return const ProfileOverride();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    state = ProfileOverride(
      nickname: prefs.getString(_nicknameKey),
      photoBase64: prefs.getString(_photoKey),
    );
  }

  Future<void> setNickname(String nickname) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_nicknameKey, nickname);
    state = ProfileOverride(nickname: nickname, photoBase64: state.photoBase64);
  }

  Future<void> setPhoto(Uint8List bytes) async {
    final b64 = base64Encode(bytes);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_photoKey, b64);
    state = ProfileOverride(nickname: state.nickname, photoBase64: b64);
  }
}

final profileOverrideProvider =
    NotifierProvider<ProfileOverrideNotifier, ProfileOverride>(ProfileOverrideNotifier.new);
