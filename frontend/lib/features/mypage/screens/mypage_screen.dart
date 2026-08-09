import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../auth/providers/auth_controller.dart';
import '../../auth/providers/auth_state.dart';

/// 마이페이지 (메인 셸 탭 3)
///
/// 프로필/통계 + 학습 진행·계정 설정·고객 지원 메뉴.
/// 로그아웃/계정 삭제는 기존 AuthController 로직을 그대로 사용한다(백엔드 연동 유지).
class MyPageScreen extends ConsumerWidget {
  const MyPageScreen({super.key});

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('로그아웃'),
        content: const Text('로그아웃하시겠어요?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false), child: const Text('취소')),
          TextButton(
              onPressed: () => Navigator.pop(c, true),
              child: const Text('로그아웃')),
        ],
      ),
    );
    if (ok == true) {
      await ref.read(authControllerProvider.notifier).signOut();
      if (context.mounted) context.go('/login');
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final name = authState is AuthAuthenticated
        ? (authState.user.name ?? authState.user.email)
        : '사용자';

    return Container(
      color: AppTheme.scaffold,
      child: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 16, 20, 12),
              child: Text('마이페이지',
                  style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ),
            _ProfileHeader(name: name),
            const SizedBox(height: 12),
            _MenuSection(
              title: '학습 진행 상황',
              items: [
                _MenuItem(
                    icon: Icons.workspace_premium_rounded,
                    title: '나의 성취도',
                    subtitle: '배지와 학습 기록 보기',
                    onTap: () {}),
              ],
            ),
            _MenuSection(
              title: '계정 설정',
              items: [
                _MenuItem(
                    icon: Icons.person_outline_rounded,
                    title: '프로필 관리',
                    onTap: () {}),
                _MenuItem(
                    icon: Icons.notifications_none_rounded,
                    title: '알림 설정',
                    onTap: () {}),
                _MenuItem(
                    icon: Icons.tune_rounded,
                    title: '상세환경설정',
                    onTap: () => context.push('/settings')),
              ],
            ),
            _MenuSection(
              title: '고객 지원',
              items: [
                _MenuItem(
                    icon: Icons.help_outline_rounded,
                    title: '자주 묻는 질문',
                    onTap: () {}),
                _MenuItem(
                    icon: Icons.chat_outlined,
                    title: '문의하기',
                    onTap: () {}),
              ],
            ),
            _MenuSection(
              items: [
                _MenuItem(title: '이용약관', onTap: () {}),
                _MenuItem(title: '개인정보 처리방침', onTap: () {}),
                const _MenuItem(
                    title: '앱 버전', trailingText: '1.0.0', showChevron: false),
              ],
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: OutlinedButton.icon(
                onPressed: () => _confirmSignOut(context, ref),
                icon: const Icon(Icons.logout_rounded, size: 18),
                label: const Text('로그아웃'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppTheme.errorColor,
                  side: const BorderSide(color: AppTheme.line),
                  minimumSize: const Size.fromHeight(48),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppTheme.radiusMd)),
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 8, 20, 28),
              child: Column(
                children: [
                  Text('한이음 · AI 손글씨 교정 앱',
                      style:
                          TextStyle(fontSize: 11, color: AppTheme.inkFaint)),
                  SizedBox(height: 2),
                  Text('© 2026 한이음. All rights reserved.',
                      style:
                          TextStyle(fontSize: 11, color: AppTheme.inkFaint)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  final String name;
  const _ProfileHeader({required this.name});

  @override
  Widget build(BuildContext context) {
    final initial = name.isNotEmpty ? name.substring(0, 1) : '유';
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.primaryColor, Color(0xFF57C9A6)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(AppTheme.radiusLg),
      ),
      child: Column(
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 26,
                backgroundColor: Colors.white,
                child: Text(initial,
                    style: const TextStyle(
                        color: AppTheme.primaryDark,
                        fontWeight: FontWeight.bold,
                        fontSize: 20)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.bold)),
                    const SizedBox(height: 2),
                    const Text('손글씨 마스터 Lv.5',
                        style:
                            TextStyle(color: Colors.white70, fontSize: 12)),
                  ],
                ),
              ),
              OutlinedButton(
                onPressed: () {},
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Colors.white70),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20)),
                ),
                child: const Text('편집', style: TextStyle(fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 18),
          const Row(
            children: [
              Expanded(child: _StatTile(value: '24', label: '연습 시간')),
              Expanded(child: _StatTile(value: '18', label: '완료한 레슨')),
              Expanded(child: _StatTile(value: '92%', label: '정확도')),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final String value;
  final String label;
  const _StatTile({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      ),
      child: Column(
        children: [
          Text(value,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 2),
          Text(label,
              style: const TextStyle(color: Colors.white70, fontSize: 11)),
        ],
      ),
    );
  }
}

class _MenuSection extends StatelessWidget {
  final String? title;
  final List<_MenuItem> items;
  const _MenuSection({this.title, required this.items});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title != null) ...[
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 8),
              child: Text(title!,
                  style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.inkMuted)),
            ),
          ],
          Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(AppTheme.radiusMd),
              border: Border.all(color: AppTheme.line),
            ),
            child: Column(
              children: [
                for (var i = 0; i < items.length; i++) ...[
                  items[i],
                  if (i != items.length - 1)
                    const Divider(height: 1, color: AppTheme.line, indent: 16, endIndent: 16),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData? icon;
  final String title;
  final String? subtitle;
  final String? trailingText;
  final bool showChevron;
  final VoidCallback? onTap;
  const _MenuItem({
    required this.title,
    this.icon,
    this.subtitle,
    this.trailingText,
    this.showChevron = true,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppTheme.radiusMd),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            if (icon != null) ...[
              Icon(icon, size: 20, color: AppTheme.primaryDark),
              const SizedBox(width: 12),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: AppTheme.ink)),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(subtitle!,
                        style: const TextStyle(
                            fontSize: 12, color: AppTheme.inkMuted)),
                  ],
                ],
              ),
            ),
            if (trailingText != null)
              Text(trailingText!,
                  style: const TextStyle(
                      fontSize: 13, color: AppTheme.inkFaint)),
            if (showChevron)
              const Icon(Icons.chevron_right_rounded,
                  color: AppTheme.inkFaint, size: 20),
          ],
        ),
      ),
    );
  }
}
