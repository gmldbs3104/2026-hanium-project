import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../../auth/providers/auth_controller.dart';
import '../../auth/providers/auth_state.dart';
import '../providers/profile_override_provider.dart';
import 'profile_photo_capture_screen.dart';

/// 프로필 관리 — 닉네임 · 프로필 사진 수정 (mypage_upgrade.md 3.2)
///
/// 비밀번호 수정은 포함하지 않는다 — 이 앱은 소셜 로그인(Google/Kakao/Apple) 전용이라
/// 바꿀 수 있는 비밀번호 자체가 없다(auth_controller.dart 참고). 저장은
/// [profileOverrideProvider]를 통해 이 기기에만 로컬로 남는다(백엔드 프로필 수정 API가
/// 없어서 서버 동기화는 아직 불가 — mypage_upgrade.md 3.2 참고).
class ProfileEditScreen extends ConsumerStatefulWidget {
  const ProfileEditScreen({super.key});

  @override
  ConsumerState<ProfileEditScreen> createState() => _ProfileEditScreenState();
}

class _ProfileEditScreenState extends ConsumerState<ProfileEditScreen> {
  late final TextEditingController _nicknameController;
  Uint8List? _pendingPhotoBytes; // 촬영했지만 아직 "저장" 누르기 전

  @override
  void initState() {
    super.initState();
    final authState = ref.read(authControllerProvider);
    final override = ref.read(profileOverrideProvider);
    final fallbackName = authState is AuthAuthenticated
        ? (authState.user.name ?? authState.user.email)
        : '사용자';
    _nicknameController = TextEditingController(text: override.nickname ?? fallbackName);
  }

  @override
  void dispose() {
    _nicknameController.dispose();
    super.dispose();
  }

  Future<void> _pickPhoto() async {
    final bytes = await Navigator.of(context).push<Uint8List>(
      MaterialPageRoute(builder: (_) => const ProfilePhotoCaptureScreen()),
    );
    if (bytes != null && mounted) setState(() => _pendingPhotoBytes = bytes);
  }

  Future<void> _save() async {
    final notifier = ref.read(profileOverrideProvider.notifier);
    final nickname = _nicknameController.text.trim();
    if (nickname.isNotEmpty) {
      await notifier.setNickname(nickname);
    }
    if (_pendingPhotoBytes != null) {
      await notifier.setPhoto(_pendingPhotoBytes!);
    }
    if (!mounted) return;
    context.pop();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final email = authState is AuthAuthenticated ? authState.user.email : '';
    final override = ref.watch(profileOverrideProvider);

    ImageProvider? avatarImage;
    if (_pendingPhotoBytes != null) {
      avatarImage = MemoryImage(_pendingPhotoBytes!);
    } else if (override.photoBase64 != null) {
      avatarImage = MemoryImage(base64Decode(override.photoBase64!));
    }
    final initial =
        _nicknameController.text.isNotEmpty ? _nicknameController.text.substring(0, 1) : '유';

    return Scaffold(
      backgroundColor: AppTheme.scaffold,
      appBar: AppBar(
        leading: const BackButton(),
        title: const Text('프로필 관리'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Center(
            child: Stack(
              children: [
                CircleAvatar(
                  radius: 48,
                  backgroundColor: AppTheme.mint,
                  backgroundImage: avatarImage,
                  child: avatarImage == null
                      ? Text(initial,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 32, fontWeight: FontWeight.bold))
                      : null,
                ),
                Positioned(
                  right: 0,
                  bottom: 0,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20),
                    onTap: _pickPhoto,
                    child: Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: AppTheme.primaryColor,
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                      ),
                      child: const Icon(Icons.camera_alt_rounded, size: 16, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const Text('닉네임',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.ink)),
          const SizedBox(height: 8),
          TextField(
            controller: _nicknameController,
            maxLength: 20,
            decoration: InputDecoration(
              hintText: '닉네임을 입력하세요',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppTheme.radiusSm)),
            ),
          ),
          const SizedBox(height: 8),
          Text('이메일: $email',
              style: const TextStyle(fontSize: 12, color: AppTheme.inkFaint)),
          const SizedBox(height: 28),
          MintButton(label: '저장', onPressed: _save),
        ],
      ),
    );
  }
}
