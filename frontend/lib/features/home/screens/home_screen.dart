import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/analytics_service.dart';
import '../../../core/app_theme.dart';
import '../../../core/theme_provider.dart';
import '../../auth/providers/auth_controller.dart';
import '../../auth/providers/auth_state.dart';
import '../providers/mode_provider.dart';

/// 메인 화면 - 모드 분기 (SFR-002)
///
/// REQ-002-1: 두 가지 모드를 명확히 구분하여 표시
/// REQ-002-2: 모드 선택 후 화면 전환은 500ms 이내 완료
/// REQ-002-3: 두 모드는 서로 다른 독립된 파이프라인으로 연결 (로직 공유 X)
/// Side Effect: 모드 선택 이벤트가 Firebase Analytics에 로깅됨 (현재는 로그 출력으로 대체)
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  void _selectMode(BuildContext context, WidgetRef ref, AnalysisMode mode) {
    ref.read(selectedModeProvider.notifier).state = mode;

    // SFR-002 Side Effect: 모드 선택 이벤트를 Firebase Analytics에 로깅.
    // (mock 모드에서는 AnalyticsService 내부에서 debugPrint로 대체됨)
    AnalyticsService.logModeSelected(mode.name);

    if (mode == AnalysisMode.canvas) {
      context.go('/canvas');
    } else {
      context.go('/image-capture');
    }
  }

  /// SFR-001: 로그아웃. signOut()이 인증 상태를 초기화하면 라우터 가드가
  /// 자동으로 /login 으로 되돌리므로 별도 화면 이동은 필요 없다.
  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final shouldSignOut = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('로그아웃'),
        content: const Text('로그아웃하시겠어요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('로그아웃'),
          ),
        ],
      ),
    );

    if (shouldSignOut == true) {
      await ref.read(authControllerProvider.notifier).signOut();
    }
  }

  /// REQ-009-7: 계정 삭제 진입점. 되돌릴 수 없는 작업이므로 명시적 경고 후 진행한다.
  /// 실제 데이터 삭제는 백엔드가 수행하며, 성공 시 라우터 가드가 /login 으로 되돌린다.
  Future<void> _confirmDeleteAccount(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('계정 삭제'),
        content: const Text(
          '계정을 삭제하면 학습 기록과 저장된 이미지를 포함한 모든 데이터가 삭제되며, '
          '이 작업은 되돌릴 수 없습니다.\n\n정말 삭제하시겠어요?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: TextButton.styleFrom(foregroundColor: AppTheme.errorColor),
            child: const Text('삭제'),
          ),
        ],
      ),
    );

    if (confirmed != true || !context.mounted) return;

    // context가 삭제 성공 시 /login 으로 사라질 수 있으므로 messenger를 미리 확보한다.
    final messenger = ScaffoldMessenger.of(context);
    final success = await ref.read(authControllerProvider.notifier).deleteAccount();

    messenger.showSnackBar(
      SnackBar(
        content: Text(
          success ? '계정이 삭제되었습니다.' : '계정 삭제에 실패했습니다. 잠시 후 다시 시도해주세요.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final userLabel =
        authState is AuthAuthenticated ? (authState.user.name ?? authState.user.email) : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 손글씨 교정'),
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart_rounded),
            tooltip: '학습 대시보드',
            onPressed: () => context.go('/dashboard'),
          ),
          // SFR-007 Inputs: 테마(light/dark) 선택
          PopupMenuButton<ThemeMode>(
            icon: const Icon(Icons.brightness_6_rounded),
            tooltip: '테마',
            initialValue: ref.watch(themeModeProvider),
            onSelected: (mode) =>
                ref.read(themeModeProvider.notifier).state = mode,
            itemBuilder: (context) => const [
              PopupMenuItem(value: ThemeMode.system, child: Text('시스템 설정')),
              PopupMenuItem(value: ThemeMode.light, child: Text('라이트')),
              PopupMenuItem(value: ThemeMode.dark, child: Text('다크')),
            ],
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.account_circle_rounded),
            tooltip: '계정',
            onSelected: (value) {
              if (value == 'logout') _confirmSignOut(context, ref);
              if (value == 'delete_account') _confirmDeleteAccount(context, ref);
            },
            itemBuilder: (context) => [
              if (userLabel != null)
                PopupMenuItem<String>(
                  enabled: false,
                  child: Text(
                    userLabel,
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
                  ),
                ),
              if (userLabel != null) const PopupMenuDivider(),
              const PopupMenuItem<String>(
                value: 'logout',
                child: Row(
                  children: [
                    Icon(Icons.logout_rounded, size: 20),
                    SizedBox(width: 12),
                    Text('로그아웃'),
                  ],
                ),
              ),
              const PopupMenuItem<String>(
                value: 'delete_account',
                child: Row(
                  children: [
                    Icon(Icons.delete_forever_rounded, size: 20, color: AppTheme.errorColor),
                    SizedBox(width: 12),
                    Text('계정 삭제', style: TextStyle(color: AppTheme.errorColor)),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '오늘은 어떤 모드로\n글씨를 교정해볼까요?',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, height: 1.3),
              ),
              const SizedBox(height: 24),
              Expanded(
                child: Row(
                  children: [
                    Expanded(
                      child: _ModeCard(
                        title: '글씨 연습',
                        subtitle: '캔버스에 직접 필기하며\n획순·자간·크기를 분석합니다',
                        icon: Icons.draw_rounded,
                        color: AppTheme.canvasModeColor,
                        onTap: () => _selectMode(context, ref, AnalysisMode.canvas),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: _ModeCard(
                        title: '실전 모드',
                        subtitle: '사진을 촬영해\n크기 균일성·기울기를 분석합니다',
                        icon: Icons.camera_alt_rounded,
                        color: AppTheme.imageModeColor,
                        onTap: () => _selectMode(context, ref, AnalysisMode.image),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _ModeCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color.withValues(alpha: 0.08),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 28),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: color.withValues(alpha: 0.25)),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                child: Icon(icon, size: 32, color: Colors.white),
              ),
              const SizedBox(height: 16),
              Text(
                title,
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: color),
              ),
              const SizedBox(height: 8),
              Text(
                subtitle,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: Colors.grey.shade700, height: 1.4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
