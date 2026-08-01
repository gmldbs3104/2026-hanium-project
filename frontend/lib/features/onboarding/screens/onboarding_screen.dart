import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../providers/onboarding_provider.dart';

/// 온보딩2 — 연습 목표(복수 선택) + 교정 기준 폰트 선택
///
/// 순수 클라이언트 화면(백엔드 호출 없음). 선택 값은 onboarding_provider에 저장한다.
class OnboardingScreen extends ConsumerWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final goals = ref.watch(selectedGoalsProvider);
    final font = ref.watch(selectedFontProvider);
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
                    const SizedBox(height: 32),
                    const Text(
                      '교정 기준 폰트를\n선택하세요',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        height: 1.3,
                        color: AppTheme.ink,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text('AI가 이 폰트를 기준으로 교정합니다',
                        style: TextStyle(fontSize: 13, color: AppTheme.inkMuted)),
                    const SizedBox(height: 16),
                    _FontGrid(
                      selected: font,
                      onSelect: (f) =>
                          ref.read(selectedFontProvider.notifier).state = f,
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

class _FontGrid extends StatelessWidget {
  final CorrectionFont selected;
  final ValueChanged<CorrectionFont> onSelect;
  const _FontGrid({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: CorrectionFont.values.map((f) {
        return SizedBox(
          width: (MediaQuery.of(context).size.width - 24 * 2 - 12) / 2,
          child: _FontCard(
            font: f,
            selected: selected == f,
            onTap: () => onSelect(f),
          ),
        );
      }).toList(),
    );
  }
}

class _FontCard extends StatelessWidget {
  final CorrectionFont font;
  final bool selected;
  final VoidCallback onTap;
  const _FontCard(
      {required this.font, required this.selected, required this.onTap});

  TextStyle get _previewStyle => switch (font) {
        CorrectionFont.gothic => const TextStyle(
            fontSize: 20, fontWeight: FontWeight.w700, color: AppTheme.ink),
        CorrectionFont.myeongjo => const TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w600,
            fontFamily: 'serif',
            color: AppTheme.ink),
        CorrectionFont.round => const TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w500,
            letterSpacing: 0.5,
            color: AppTheme.ink),
      };

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppTheme.radiusMd),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: selected ? AppTheme.mintSurface : Colors.white,
          borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          border: Border.all(
            color: selected ? AppTheme.primaryColor : AppTheme.line,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(font.label,
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.inkMuted)),
                _RadioDot(selected: selected),
              ],
            ),
            const SizedBox(height: 8),
            Text('안녕하세요', style: _previewStyle),
          ],
        ),
      ),
    );
  }
}

class _RadioDot extends StatelessWidget {
  final bool selected;
  const _RadioDot({required this.selected});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: selected ? AppTheme.primaryColor : AppTheme.inkFaint,
          width: 2,
        ),
        color: selected ? AppTheme.primaryColor : Colors.transparent,
      ),
      child: selected
          ? const Icon(Icons.circle, size: 8, color: Colors.white)
          : null,
    );
  }
}
