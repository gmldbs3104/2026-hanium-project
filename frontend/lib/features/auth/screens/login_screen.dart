import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../onboarding/providers/onboarding_provider.dart';
import '../providers/auth_controller.dart';
import '../providers/auth_state.dart';

/// 온보딩 / 로그인 화면
///
/// SFR-001 (사용자 인증 및 계정 관리) 대응
/// REQ-001-4: 인증 실패 시 사용자에게 명확한 오류 메시지를 표시
class LoginScreen extends ConsumerWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);

    // 로그인 성공 시: 온보딩 미완료면 온보딩으로, 완료면 메인으로 이동
    ref.listen<AuthState>(authControllerProvider, (previous, next) {
      if (next is AuthAuthenticated) {
        final done = ref.read(onboardingCompletedProvider);
        context.go(done ? '/main' : '/onboarding');
      }
    });

    final isLoading = authState is AuthLoading;

    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(flex: 3),
              // ── 브랜드 헤더 ──
              const Text(
                'AI 손글씨 교정',
                style: TextStyle(
                  fontSize: 40,
                  fontWeight: FontWeight.w800,
                  color: AppTheme.ink,
                  letterSpacing: -0.5,
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                'AI 기술로 손글씨를 분석하고\n개인 맞춤형 교정을 제공합니다',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.5,
                  color: AppTheme.inkMuted,
                ),
              ),
              const Spacer(flex: 2),

              if (authState is AuthError) ...[
                _ErrorBanner(message: authState.message),
                const SizedBox(height: 16),
              ],

              if (isLoading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: CircularProgressIndicator()),
                )
              else ...[
                _SocialLoginButton(
                  label: 'Google 계정으로 시작하기',
                  icon: Icons.public,
                  backgroundColor: Colors.white,
                  foregroundColor: AppTheme.ink,
                  borderColor: AppTheme.line,
                  onPressed: () =>
                      ref.read(authControllerProvider.notifier).signInWithGoogle(),
                ),
                const SizedBox(height: 12),
                _SocialLoginButton(
                  label: '카카오 계정으로 시작하기',
                  icon: Icons.chat_bubble,
                  backgroundColor: AppTheme.kakaoYellow,
                  foregroundColor: const Color(0xFF3A1D1D),
                  onPressed: () =>
                      ref.read(authControllerProvider.notifier).signInWithKakao(),
                ),
                const SizedBox(height: 12),
                _SocialLoginButton(
                  label: 'Apple 계정으로 시작하기',
                  icon: Icons.apple,
                  backgroundColor: AppTheme.appleNavy,
                  foregroundColor: Colors.white,
                  onPressed: () =>
                      ref.read(authControllerProvider.notifier).signInWithApple(),
                ),
              ],

              const Spacer(flex: 1),
              const Padding(
                padding: EdgeInsets.only(bottom: 12),
                child: Text(
                  '계속 진행하면 서비스 이용약관 및 개인정보 처리방침에\n동의하는 것으로 간주됩니다',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, height: 1.5, color: AppTheme.inkFaint),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SocialLoginButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color backgroundColor;
  final Color foregroundColor;
  final Color? borderColor;
  final VoidCallback onPressed;

  const _SocialLoginButton({
    required this.label,
    required this.icon,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.onPressed,
    this.borderColor,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 54,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: backgroundColor,
          foregroundColor: foregroundColor,
          elevation: 0,
          side: borderColor != null ? BorderSide(color: borderColor!) : BorderSide.none,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 20, color: foregroundColor),
            const SizedBox(width: 10),
            Text(
              label,
              style: TextStyle(
                  color: foregroundColor,
                  fontSize: 15,
                  fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFDECEC),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFF5C2C2)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppTheme.errorColor, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message,
                style: const TextStyle(color: AppTheme.errorColor, fontSize: 13)),
          ),
        ],
      ),
    );
  }
}
