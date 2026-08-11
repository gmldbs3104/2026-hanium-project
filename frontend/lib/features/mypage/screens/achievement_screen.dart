import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/app_theme.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../../auth/providers/auth_controller.dart';
import '../../dashboard/models/dashboard_response.dart';
import '../../dashboard/services/dashboard_api_service.dart';
import '../../dashboard/utils/improvement_rate_format.dart';
import '../utils/level_title.dart';

/// 나의 성취도 (mypage_upgrade.md 3.1)
///
/// 지금은 "학습 기록(요약)"만 구현한다 — GET /api/v1/dashboard를 그대로 재사용하므로
/// 백엔드 변경 없이 가능하다(report_screen.dart와 동일한 데이터 소스).
/// 배지·개별 세션 목록은 백엔드에 카탈로그/조회 API가 없어서 이번 범위에서 제외했다
/// (mypage_upgrade.md 3.1 표 참고) — 아래 "배지" 카드는 빈 상태 안내만 보여준다.
class AchievementScreen extends ConsumerStatefulWidget {
  const AchievementScreen({super.key});

  @override
  ConsumerState<AchievementScreen> createState() => _AchievementScreenState();
}

class _AchievementScreenState extends ConsumerState<AchievementScreen> {
  bool _isLoading = true;
  String? _error;
  DashboardResponse? _data;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final idToken =
          await ref.read(authControllerProvider.notifier).getCurrentIdToken();
      final data = await DashboardApiService.fetch(
        period: DashboardPeriod.all,
        mode: DashboardModeFilter.all,
        idToken: idToken,
      );
      if (mounted) setState(() => _data = data);
    } catch (_) {
      if (mounted) setState(() => _error = '성취도를 불러오지 못했습니다.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.scaffold,
      appBar: AppBar(
        leading: const BackButton(),
        title: const Text('나의 성취도'),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, color: AppTheme.errorColor, size: 40),
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: AppTheme.errorColor)),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: _load, child: const Text('다시 시도')),
          ],
        ),
      );
    }

    final data = _data!;
    final s = data.periodSummary;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _LevelStreakCard(level: data.level, streakDays: data.streakDays),
        const SizedBox(height: 16),
        _LevelTierCard(level: data.level, totalSessions: s.totalSessions),
        const SizedBox(height: 16),
        HaneumCard(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('학습 기록 요약',
                  style: TextStyle(
                      fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.ink)),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(child: _StatTile(value: '${s.totalSessions}', label: '총 연습 세션')),
                  Expanded(child: _StatTile(value: s.avgScore.round().toString(), label: '평균 점수')),
                  Expanded(
                      child: _StatTile(
                          value: formatImprovementRate(s.improvementRate), label: '향상률')),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(child: _StatTile(value: '${s.canvasSessions}', label: '글씨 연습')),
                  Expanded(child: _StatTile(value: '${s.imageSessions}', label: '실전 모드')),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        if (data.weakItems.isNotEmpty) ...[
          HaneumCard(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('자주 발견된 습관',
                    style: TextStyle(
                        fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.ink)),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: data.weakItems
                      .take(6)
                      .map((w) => HabitBadge(label: w.item, count: '${w.frequency}회'))
                      .toList(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        const HaneumCard(
          padding: EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.workspace_premium_outlined, size: 18, color: AppTheme.inkFaint),
                  SizedBox(width: 6),
                  Text('배지',
                      style: TextStyle(
                          fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.ink)),
                ],
              ),
              SizedBox(height: 10),
              Text(
                '배지 기능은 준비 중이에요. 곧 만나보실 수 있어요!',
                style: TextStyle(fontSize: 12.5, color: AppTheme.inkFaint),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _LevelStreakCard extends StatelessWidget {
  final int level;
  final int streakDays;
  const _LevelStreakCard({required this.level, required this.streakDays});

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
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('LV.$level ${levelTitle(level)}',
                    style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF14503F))),
                const SizedBox(height: 6),
                Text('$streakDays일 연속 연습 중',
                    style: const TextStyle(fontSize: 13, color: Color(0xFF2C6B57))),
              ],
            ),
          ),
          const Icon(Icons.local_fire_department_rounded,
              color: Color(0xFF3E8A72), size: 36),
        ],
      ),
    );
  }
}

/// 현재 레벨이 어느 구간에 있는지 + 다음 레벨까지 남은 세션 수를 보여준다.
class _LevelTierCard extends StatelessWidget {
  final int level;
  final int totalSessions;
  const _LevelTierCard({required this.level, required this.totalSessions});

  @override
  Widget build(BuildContext context) {
    final remaining = sessionsUntilNextLevel(level, totalSessions);
    return HaneumCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('레벨 안내',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.ink)),
          const SizedBox(height: 4),
          Text(
            remaining == 0 ? '다음 레벨 조건을 채웠어요!' : '다음 레벨까지 연습 세션 $remaining개 남았어요.',
            style: const TextStyle(fontSize: 12, color: AppTheme.inkMuted),
          ),
          const SizedBox(height: 14),
          ...levelTiers.map((tier) {
            final isCurrent = level >= tier.minLevel &&
                (levelTiers.indexOf(tier) == levelTiers.length - 1 ||
                    level < levelTiers[levelTiers.indexOf(tier) + 1].minLevel);
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isCurrent ? AppTheme.primaryColor : AppTheme.line,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text('Lv.${tier.minLevel}+',
                      style: TextStyle(
                          fontSize: 12.5,
                          fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
                          color: isCurrent ? AppTheme.ink : AppTheme.inkFaint)),
                  const SizedBox(width: 8),
                  Text(tier.title,
                      style: TextStyle(
                          fontSize: 12.5,
                          fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
                          color: isCurrent ? AppTheme.primaryDark : AppTheme.inkFaint)),
                  if (isCurrent) ...[
                    const SizedBox(width: 6),
                    const Text('← 현재',
                        style: TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w700, color: AppTheme.primaryColor)),
                  ],
                ],
              ),
            );
          }),
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
      margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        color: AppTheme.mintSurface,
        borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      ),
      child: Column(
        children: [
          Text(value,
              style: const TextStyle(
                  fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.primaryDark)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.inkMuted)),
        ],
      ),
    );
  }
}
