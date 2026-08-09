import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/analytics_service.dart';
import '../../../core/app_theme.dart';
import '../../auth/providers/auth_controller.dart';
import '../../auth/providers/auth_state.dart';
import '../providers/mode_provider.dart';

/// 홈 화면 (메인 셸 탭 0)
///
/// SFR-002: 두 가지 분석 모드(연습/실전)로 진입. 모드 선택 이벤트는 Analytics에 로깅.
/// 학습 카테고리 카드에서 각 연습/실전 플로우로 진입한다.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  void _goPractice(BuildContext context, WidgetRef ref, AnalysisMode mode,
      String route) {
    ref.read(selectedModeProvider.notifier).state = mode;
    AnalyticsService.logModeSelected(mode.name);
    if (route == '/image-capture') {
      context.push(route);
    } else {
      context.go(route);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final name = authState is AuthAuthenticated
        ? (authState.user.name ?? authState.user.email)
        : '사용자';
    final initial = name.isNotEmpty ? name.substring(0, 1) : '유';

    return Container(
      color: Colors.white,
      child: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          children: [
            _Header(name: name, initial: initial, level: 'LV5', title: '손글씨 마스터'),
            const SizedBox(height: 20),
            _StreakBanner(
              days: 21,
              onStart: () =>
                  _goPractice(context, ref, AnalysisMode.canvas, '/character-practice'),
            ),
            const SizedBox(height: 28),
            const Text(
              '학습 카테고리',
              style: TextStyle(
                  fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.ink),
            ),
            const SizedBox(height: 14),
            _CategoryCard(
              title: '손글씨 기초',
              subtitle: '필기구 쥐는 올바른 자세',
              icon: Icons.menu_book_rounded,
              onTap: () => context.go('/basics'),
            ),
            const SizedBox(height: 12),
            _CategoryCard(
              title: '손글씨 연습',
              subtitle: '자음, 모음, 받침 글자 연습',
              icon: Icons.edit_rounded,
              onTap: () =>
                  _goPractice(context, ref, AnalysisMode.canvas, '/character-practice'),
            ),
            const SizedBox(height: 12),
            _CategoryCard(
              title: '문장 쓰기',
              subtitle: '짧은 문장부터 캘리그라피까지',
              icon: Icons.description_rounded,
              onTap: () =>
                  _goPractice(context, ref, AnalysisMode.canvas, '/sentence-practice'),
            ),
            const SizedBox(height: 12),
            _CategoryCard(
              title: '실전 모드',
              subtitle: 'AI분석을 통해 실전처럼 글쓰기',
              icon: Icons.assignment_rounded,
              onTap: () =>
                  _goPractice(context, ref, AnalysisMode.image, '/image-capture'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final String name;
  final String initial;
  final String level;
  final String title;
  const _Header(
      {required this.name,
      required this.initial,
      required this.level,
      required this.title});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('안녕하세요,',
                  style: TextStyle(fontSize: 14, color: AppTheme.inkMuted)),
              const SizedBox(height: 2),
              Text('$name님',
                  style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(level,
                style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: AppTheme.ink)),
            Text(title,
                style: const TextStyle(fontSize: 11, color: AppTheme.inkMuted)),
          ],
        ),
        const SizedBox(width: 10),
        CircleAvatar(
          radius: 20,
          backgroundColor: AppTheme.mint,
          child: Text(initial,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }
}

class _StreakBanner extends StatelessWidget {
  final int days;
  final VoidCallback onStart;
  const _StreakBanner({required this.days, required this.onStart});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.bannerStart, AppTheme.bannerEnd],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(AppTheme.radiusLg),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('놀라워요!',
                    style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF14503F))),
                const SizedBox(height: 8),
                Text(
                  '$days일동안 연속으로 출석하셨어요.\n의지가 대단하시네요! 곧 글쓰기 마스터!\n오늘의 글쓰기를 시작하러 가볼까요?',
                  style: const TextStyle(
                      fontSize: 12.5, height: 1.5, color: Color(0xFF2C6B57)),
                ),
                const SizedBox(height: 14),
                ElevatedButton(
                  onPressed: onStart,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.mintStrong,
                    foregroundColor: Colors.white,
                    elevation: 0,
                    padding:
                        const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(AppTheme.radiusMd)),
                  ),
                  child: const Text('지금 시작하기',
                      style: TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w700)),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text('D-$days',
                    style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: AppTheme.primaryDark)),
              ),
              const SizedBox(height: 10),
              const Icon(Icons.edit_rounded, color: Color(0xFF3E8A72), size: 28),
            ],
          ),
        ],
      ),
    );
  }
}

class _CategoryCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;
  const _CategoryCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppTheme.radiusMd),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          border: Border.all(color: AppTheme.line),
          boxShadow: AppTheme.cardShadow,
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: AppTheme.ink)),
                  const SizedBox(height: 4),
                  Text(subtitle,
                      style: const TextStyle(
                          fontSize: 13, color: AppTheme.inkMuted)),
                ],
              ),
            ),
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppTheme.mintSurface,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: AppTheme.primaryDark, size: 22),
            ),
          ],
        ),
      ),
    );
  }
}
