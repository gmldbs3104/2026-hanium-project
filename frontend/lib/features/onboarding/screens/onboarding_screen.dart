import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../providers/onboarding_provider.dart';

/// 온보딩2 — 연습 목표(복수 선택)
///
/// 순수 클라이언트 화면(백엔드 호출 없음). 선택 값은 onboarding_provider에 저장한다.
/// 교정 기준 폰트는 명조체로 고정이라 선택 UI가 없다.
class OnboardingScreen extends ConsumerWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final goals = ref.watch(selectedGoalsProvider);
    final canStart = goals.isNotEmpty;

    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '어떤 목표로 손글씨를\n연습하시나요?',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        height: 1.3,
                        color: AppTheme.ink,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text('복수 선택 가능합니다',
                        style: TextStyle(fontSize: 13, color: AppTheme.inkMuted)),
                    const SizedBox(height: 18),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: PracticeGoal.values.map((g) {
                        final selected = goals.contains(g);
                        return _GoalChip(
                          label: g.label,
                          selected: selected,
                          onTap: () {
                            final next = {...goals};
                            selected ? next.remove(g) : next.add(g);
                            ref.read(selectedGoalsProvider.notifier).state = next;
                          },
                        );
                      }).toList(),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
              child: MintButton(
                label: '시작하기',
                onPressed: canStart
                    ? () {
                        ref.read(onboardingCompletedProvider.notifier).state = true;
                        context.go('/main');
                      }
                    : null,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GoalChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _GoalChip(
      {required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(24),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 11),
        decoration: BoxDecoration(
          color: selected ? AppTheme.mintSurface : Colors.white,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: selected ? AppTheme.primaryColor : AppTheme.line,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 14,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: selected ? AppTheme.primaryDark : AppTheme.ink,
          ),
        ),
      ),
    );
  }
}

