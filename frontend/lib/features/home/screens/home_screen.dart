import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
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

    // ===== Firebase Analytics 연동 시 (현재는 mock 로그) =====
    // FirebaseAnalytics.instance.logEvent(
    //   name: 'mode_selected',
    //   parameters: {'mode': mode.name},
    // );
    debugPrint('[Analytics] mode_selected: ${mode.name}');

    if (mode == AnalysisMode.canvas) {
      context.go('/canvas');
    } else {
      context.go('/image-capture');
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 손글씨 교정'),
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart_rounded),
            tooltip: '학습 대시보드',
            onPressed: () => context.go('/dashboard'),
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
