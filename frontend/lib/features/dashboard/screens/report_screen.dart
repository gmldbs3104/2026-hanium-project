import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../../auth/providers/auth_controller.dart';
import '../models/dashboard_response.dart';
import '../services/dashboard_api_service.dart';
import '../utils/improvement_rate_format.dart';

/// 나의 학습 리포트 (결과창)
///
/// 기존 대시보드 백엔드(GET /api/v1/dashboard)를 그대로 사용한다.
/// 목표 점수(90) 등 일부 표기는 표시용 상수다.
class ReportScreen extends ConsumerStatefulWidget {
  const ReportScreen({super.key});

  @override
  ConsumerState<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends ConsumerState<ReportScreen> {
  bool _isLoading = true;
  String? _error;
  DashboardResponse? _data;
  static const int _goal = 90;

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
        period: DashboardPeriod.week,
        mode: DashboardModeFilter.all,
        idToken: idToken,
      );
      if (mounted) setState(() => _data = data);
    } catch (_) {
      if (mounted) setState(() => _error = '리포트를 불러오지 못했습니다.');
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
        title: const Text('나의 학습 리포트'),
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
            const Icon(Icons.error_outline,
                color: AppTheme.errorColor, size: 40),
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
    final recent = data.scoreTrend.length > 7
        ? data.scoreTrend.sublist(data.scoreTrend.length - 7)
        : data.scoreTrend;
    final weekAvg = recent.isEmpty
        ? 0.0
        : recent.map((e) => e.avgScore).reduce((a, b) => a + b) /
            recent.length;

    final left = [
      _ScoreCard(
          score: s.avgScore.round(),
          improvementRate: s.improvementRate,
          goal: _goal),
      const SizedBox(height: 16),
      _WeeklyBarCard(points: recent, weekAvg: weekAvg),
    ];
    final right = [
      _WeakHabitCard(items: data.weakItems),
      const SizedBox(height: 16),
      _RecommendCard(
        exercise: data.recommendedExercises.isNotEmpty
            ? data.recommendedExercises.first
            : null,
        onPractice: () => context.go('/sentence-practice'),
      ),
    ];

    return LayoutBuilder(builder: (context, c) {
      final wide = c.maxWidth >= 720;
      return SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: wide
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: Column(children: left)),
                  const SizedBox(width: 16),
                  Expanded(child: Column(children: right)),
                ],
              )
            : Column(children: [...left, const SizedBox(height: 16), ...right]),
      );
    });
  }
}

class _ScoreCard extends StatelessWidget {
  final int score;
  final double improvementRate;
  final int goal;
  const _ScoreCard(
      {required this.score, required this.improvementRate, required this.goal});

  @override
  Widget build(BuildContext context) {
    final ratio = (score / goal).clamp(0.0, 1.0);
    final up = improvementRate >= 0;
    return HaneumCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('현재 가독성 점수',
                  style: TextStyle(fontSize: 13, color: AppTheme.inkMuted)),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppTheme.mintSurface,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(up ? Icons.trending_up_rounded : Icons.trending_down_rounded,
                        size: 13, color: AppTheme.primaryDark),
                    const SizedBox(width: 3),
                    Text(formatImprovementRate(improvementRate),
                        style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.primaryDark)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text('$score',
                  style: const TextStyle(
                      fontSize: 36,
                      fontWeight: FontWeight.w800,
                      color: AppTheme.ink)),
              const SizedBox(width: 2),
              const Text('점',
                  style: TextStyle(fontSize: 15, color: AppTheme.inkMuted)),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: ratio,
              minHeight: 8,
              backgroundColor: AppTheme.line,
              valueColor:
                  const AlwaysStoppedAnimation(AppTheme.primaryColor),
            ),
          ),
          const SizedBox(height: 6),
          Text('목표: $goal점',
              style: const TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        ],
      ),
    );
  }
}

class _WeeklyBarCard extends StatelessWidget {
  final List<ScoreTrendPoint> points;
  final double weekAvg;
  const _WeeklyBarCard({required this.points, required this.weekAvg});

  static const _weekdays = ['월', '화', '수', '목', '금', '토', '일'];

  @override
  Widget build(BuildContext context) {
    return HaneumCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              _AccentBar(),
              SizedBox(width: 8),
              Text('주간 교정 점수 변화',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 150,
            child: points.isEmpty
                ? const Center(
                    child: Text('데이터가 아직 없어요.',
                        style: TextStyle(
                            fontSize: 13, color: AppTheme.inkMuted)),
                  )
                : Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: List.generate(points.length, (i) {
                      final v = points[i].avgScore.clamp(0, 100).toDouble();
                      final label = i < _weekdays.length
                          ? _weekdays[i]
                          : '${points[i].date.day}';
                      return Expanded(
                        child: _BarColumn(value: v, label: label),
                      );
                    }),
                  ),
          ),
          const SizedBox(height: 8),
          Center(
            child: Text('이번 주 평균 점수: ${weekAvg.toStringAsFixed(1)}점',
                style:
                    const TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
          ),
        ],
      ),
    );
  }
}

class _BarColumn extends StatelessWidget {
  final double value; // 0~100
  final String label;
  const _BarColumn({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Expanded(
          child: FractionallySizedBox(
            alignment: Alignment.bottomCenter,
            heightFactor: (value / 100).clamp(0.04, 1.0),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 5),
              decoration: const BoxDecoration(
                color: AppTheme.mint,
                borderRadius: BorderRadius.vertical(
                    top: Radius.circular(6)),
              ),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(label,
            style: const TextStyle(fontSize: 11, color: AppTheme.inkFaint)),
      ],
    );
  }
}

class _WeakHabitCard extends StatelessWidget {
  final List<WeakItem> items;
  const _WeakHabitCard({required this.items});

  @override
  Widget build(BuildContext context) {
    final top = items.take(3).toList();
    return HaneumCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.error_outline_rounded,
                  size: 18, color: AppTheme.amberText),
              SizedBox(width: 6),
              Text('AI 분석: 취약한 습관',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ],
          ),
          const SizedBox(height: 14),
          if (top.isEmpty)
            const Text('아직 분석할 습관 데이터가 없어요.',
                style: TextStyle(fontSize: 13, color: AppTheme.inkMuted))
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: top
                  .map((w) => HabitBadge(
                      label: w.item, count: '${w.frequency}회'))
                  .toList(),
            ),
          const SizedBox(height: 14),
          const Text('최근 7일간 가장 자주 발견된 오류를 분석했습니다',
              style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        ],
      ),
    );
  }
}

class _RecommendCard extends StatelessWidget {
  final RecommendedExercise? exercise;
  final VoidCallback onPractice;
  const _RecommendCard({required this.exercise, required this.onPractice});

  @override
  Widget build(BuildContext context) {
    final text = exercise?.text ?? '받침이 많은 문장';
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppTheme.mintSurface,
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('맞춤형 연습 예문 추천',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.ink)),
          const SizedBox(height: 10),
          Text.rich(
            TextSpan(
              style: const TextStyle(
                  fontSize: 13, height: 1.5, color: AppTheme.ink),
              children: [
                const TextSpan(text: '분석된 습관을 바탕으로 '),
                TextSpan(
                    text: "'$text'",
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                const TextSpan(
                    text: ' 연습을 추천합니다.\n이 연습을 통해 자음 크기와 균형을 개선할 수 있습니다.'),
              ],
            ),
          ),
          const SizedBox(height: 16),
          MintButton(
            label: '추천 예문 연습하기',
            height: 48,
            onPressed: onPractice,
          ),
        ],
      ),
    );
  }
}

class _AccentBar extends StatelessWidget {
  const _AccentBar();
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
