import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/app_theme.dart';
import '../../auth/providers/auth_controller.dart';
import '../../dashboard/models/dashboard_response.dart';
import '../../dashboard/services/dashboard_api_service.dart';
import '../../dashboard/widgets/score_trend_chart.dart';

/// 나의 글씨 분석 (메인 셸 탭 2)
///
/// 기존 대시보드 백엔드(GET /api/v1/dashboard)를 그대로 사용한다.
/// 연속 출석 배지는 백엔드 스키마에 없어 표시용 고정값이다.
class AnalysisScreen extends ConsumerStatefulWidget {
  const AnalysisScreen({super.key});

  @override
  ConsumerState<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends ConsumerState<AnalysisScreen> {
  DashboardModeFilter _mode = DashboardModeFilter.canvas;
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
        mode: _mode,
        idToken: idToken,
      );
      if (mounted) setState(() => _data = data);
    } catch (_) {
      if (mounted) setState(() => _error = '분석 데이터를 불러오지 못했습니다.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppTheme.scaffold,
      child: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 16, 20, 12),
              child: Text('나의 글씨 분석',
                  style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ),
            Expanded(child: _buildBody()),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return _ErrorRetry(message: _error!, onRetry: _load);
    }
    final data = _data!;
    return LayoutBuilder(builder: (context, c) {
      final wide = c.maxWidth >= 720;
      final left = _leftColumn(data);
      final right = _rightColumn(data);
      return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        child: wide
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: Column(children: left)),
                  const SizedBox(width: 16),
                  Expanded(child: Column(children: right)),
                ],
              )
            : Column(children: [...left, ...right]),
      );
    });
  }

  List<Widget> _leftColumn(DashboardResponse data) {
    return [
      const _StreakCard(days: 21),
      const SizedBox(height: 12),
      _ModeToggle(
        mode: _mode,
        onChanged: (m) {
          setState(() => _mode = m);
          _load();
        },
      ),
      const SizedBox(height: 12),
      _WeakCharsCard(items: data.weakItems),
      const SizedBox(height: 12),
    ];
  }

  List<Widget> _rightColumn(DashboardResponse data) {
    final s = data.periodSummary;
    return [
      _AvgScoreCard(
          avg: s.avgScore.round(), delta: s.improvementRate.round()),
      const SizedBox(height: 12),
      _GrowthCard(points: data.scoreTrend),
      const SizedBox(height: 12),
    ];
  }
}

class _StreakCard extends StatelessWidget {
  final int days;
  const _StreakCard({required this.days});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.primaryColor, Color(0xFF5FCBA9)],
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
                const Row(
                  children: [
                    Icon(Icons.local_fire_department_rounded,
                        color: Colors.white, size: 18),
                    SizedBox(width: 6),
                    Text('연속 출석',
                        style: TextStyle(color: Colors.white, fontSize: 13)),
                  ],
                ),
                const SizedBox(height: 8),
                Text('$days 일',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 30,
                        fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                const Text('계속 이 페이스를 유지해요! 🎉',
                    style:
                        TextStyle(color: Colors.white70, fontSize: 12)),
              ],
            ),
          ),
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.track_changes_rounded,
                color: Colors.white, size: 30),
          ),
        ],
      ),
    );
  }
}

class _ModeToggle extends StatelessWidget {
  final DashboardModeFilter mode;
  final ValueChanged<DashboardModeFilter> onChanged;
  const _ModeToggle({required this.mode, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    Widget seg(String label, DashboardModeFilter m) {
      final selected = mode == m;
      return Expanded(
        child: GestureDetector(
          onTap: () => onChanged(m),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: selected ? AppTheme.mint : Colors.transparent,
              borderRadius: BorderRadius.circular(AppTheme.radiusSm),
            ),
            child: Text(label,
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: selected ? Colors.white : AppTheme.inkMuted)),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: AppTheme.line),
      ),
      child: Row(
        children: [
          seg('글씨 연습', DashboardModeFilter.canvas),
          seg('실전 연습', DashboardModeFilter.image),
        ],
      ),
    );
  }
}

class _WeakCharsCard extends StatelessWidget {
  final List<WeakItem> items;
  const _WeakCharsCard({required this.items});

  @override
  Widget build(BuildContext context) {
    final top = items.take(4).toList();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: AppTheme.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.bookmark_rounded,
                  color: AppTheme.amberText, size: 18),
              SizedBox(width: 6),
              Text('추가 연습이 필요한 글자',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ],
          ),
          const SizedBox(height: 4),
          const Text('AI가 분석한 취약 글자 TOP 4',
              style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
          const SizedBox(height: 12),
          if (top.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text('아직 취약 글자 데이터가 없어요.',
                  style: TextStyle(fontSize: 13, color: AppTheme.inkMuted)),
            )
          else
            ...top.map((w) => _WeakCharRow(item: w)),
        ],
      ),
    );
  }
}

class _WeakCharRow extends StatelessWidget {
  final WeakItem item;
  const _WeakCharRow({required this.item});

  @override
  Widget build(BuildContext context) {
    // item.item 예: "됨 받침 불균형" → 첫 글자 뱃지 + 나머지 설명 분리(가능할 때)
    final parts = item.item.split(' ');
    final glyph = parts.first;
    final desc = parts.length > 1 ? parts.sublist(1).join(' ') : item.mode;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFFCF6EE),
        borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(glyph,
                style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.ink)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(desc,
                    style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.ink)),
                const SizedBox(height: 2),
                Text('현재 점수: ${item.avgScore.round()}점',
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.inkMuted)),
              ],
            ),
          ),
          ElevatedButton(
            onPressed: () {},
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.mint,
              foregroundColor: Colors.white,
              elevation: 0,
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20)),
            ),
            child: const Text('연습', style: TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }
}

class _AvgScoreCard extends StatelessWidget {
  final int avg;
  final int delta;
  const _AvgScoreCard({required this.avg, required this.delta});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: AppTheme.line),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('최근 10일 평균 점수',
                    style:
                        TextStyle(fontSize: 13, color: AppTheme.inkMuted)),
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.baseline,
                  textBaseline: TextBaseline.alphabetic,
                  children: [
                    Text('$avg',
                        style: const TextStyle(
                            fontSize: 30,
                            fontWeight: FontWeight.w800,
                            color: AppTheme.ink)),
                    const SizedBox(width: 2),
                    const Text('점',
                        style: TextStyle(
                            fontSize: 14, color: AppTheme.inkMuted)),
                  ],
                ),
              ],
            ),
          ),
          _DeltaBadge(delta: delta),
        ],
      ),
    );
  }
}

class _DeltaBadge extends StatelessWidget {
  final int delta;
  const _DeltaBadge({required this.delta});

  @override
  Widget build(BuildContext context) {
    final up = delta >= 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppTheme.mintSurface,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(up ? Icons.trending_up_rounded : Icons.trending_down_rounded,
              size: 14, color: AppTheme.primaryDark),
          const SizedBox(width: 4),
          Text('${up ? '+' : ''}$delta',
              style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: AppTheme.primaryDark)),
        ],
      ),
    );
  }
}

class _GrowthCard extends StatelessWidget {
  final List<ScoreTrendPoint> points;
  const _GrowthCard({required this.points});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: AppTheme.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              _Bar(),
              SizedBox(width: 8),
              Text('성장 그래프',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ],
          ),
          const SizedBox(height: 4),
          const Text('최근 10일간의 점수 변화',
              style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
          const SizedBox(height: 12),
          if (points.isEmpty)
            const SizedBox(
              height: 120,
              child: Center(
                child: Text('데이터가 아직 없어요.',
                    style:
                        TextStyle(fontSize: 13, color: AppTheme.inkMuted)),
              ),
            )
          else
            ScoreTrendChart(points: points),
          const SizedBox(height: 10),
          const Row(
            children: [
              _LegendDot(color: AppTheme.mint, label: '글씨 연습'),
              SizedBox(width: 16),
              _LegendDot(color: AppTheme.primaryColor, label: '실전 연습'),
            ],
          ),
        ],
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 4,
      height: 16,
      decoration: BoxDecoration(
        color: AppTheme.primaryColor,
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendDot({required this.color, required this.label});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label,
            style: const TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
      ],
    );
  }
}

class _ErrorRetry extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorRetry({required this.message, required this.onRetry});
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.error_outline, color: AppTheme.errorColor, size: 40),
          const SizedBox(height: 8),
          Text(message,
              style: const TextStyle(color: AppTheme.errorColor)),
          const SizedBox(height: 16),
          OutlinedButton(onPressed: onRetry, child: const Text('다시 시도')),
        ],
      ),
    );
  }
}
