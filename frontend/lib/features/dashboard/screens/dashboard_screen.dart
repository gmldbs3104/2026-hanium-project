import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../auth/providers/auth_controller.dart';
import '../models/dashboard_response.dart';
import '../services/dashboard_api_service.dart';
import '../widgets/score_trend_chart.dart';

/// 학습 관리 대시보드 화면 (SFR-008)
///
/// REQ-008-1: 로딩 3초 이내 (mock은 AppConfig.mockDelay로 시뮬레이션)
/// REQ-008-2: 캔버스/이미지 통합 집계 + 모드별 필터링
/// REQ-008-3: 취약 항목 상위 10개 (최근 30일 기준 — 실제 집계는 백엔드 담당)
/// REQ-008-4: 맞춤 연습 예문 3~5개, 난이도순
/// REQ-008-5: 이력 없는 신규 사용자는 온보딩 안내
class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  DashboardPeriod _period = DashboardPeriod.month;
  DashboardModeFilter _modeFilter = DashboardModeFilter.all;

  bool _isLoading = true;
  String? _errorMessage;
  DashboardResponse? _data;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      // GET /api/v1/dashboard는 인증이 필요한 엔드포인트 (SFR-008 Inputs 참고)
      final idToken = await ref.read(authControllerProvider.notifier).getCurrentIdToken();

      final data = await DashboardApiService.fetch(
        period: _period,
        mode: _modeFilter,
        idToken: idToken,
      );

      if (mounted) setState(() => _data = data);
    } catch (e) {
      if (mounted) setState(() => _errorMessage = '대시보드를 불러오지 못했습니다. 다시 시도해주세요.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _onFilterChanged({DashboardPeriod? period, DashboardModeFilter? mode}) {
    setState(() {
      if (period != null) _period = period;
      if (mode != null) _modeFilter = mode;
    });
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          tooltip: '홈으로',
          onPressed: () => context.go('/home'),
        ),
        title: const Text('학습 대시보드'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            _buildFilterBar(),
            const Divider(height: 1),
            Expanded(child: _buildBody(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildFilterBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: _FilterChipRow<DashboardPeriod>(
              values: DashboardPeriod.values,
              selected: _period,
              labelOf: (v) => v.label,
              onSelected: (v) => _onFilterChanged(period: v),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _FilterChipRow<DashboardModeFilter>(
              values: DashboardModeFilter.values,
              selected: _modeFilter,
              labelOf: (v) => v.label,
              onSelected: (v) => _onFilterChanged(mode: v),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return _buildErrorState();
    }

    final data = _data!;
    if (data.isEmpty) {
      return _buildEmptyState();
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildSummaryCards(context, data.periodSummary),
        const SizedBox(height: 24),
        _buildSectionTitle('점수 추이'),
        const SizedBox(height: 8),
        ScoreTrendChart(
          points: data.scoreTrend,
          canvasColor: AppTheme.primaryColor,
          imageColor: const Color(0xFF3B82F6),
        ),
        const SizedBox(height: 24),
        _buildSectionTitle('취약 항목 TOP ${data.weakItems.length}'),
        const SizedBox(height: 8),
        ...data.weakItems.map(_buildWeakItemRow),
        const SizedBox(height: 24),
        _buildSectionTitle('맞춤 연습 예문'),
        const SizedBox(height: 8),
        ...data.recommendedExercises.map(_buildExerciseCard),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold));
  }

  Widget _buildSummaryCards(BuildContext context, PeriodSummary summary) {
    final improving = summary.improvementRate >= 0;

    return Row(
      children: [
        Expanded(
          child: _SummaryCard(
            label: '총 학습 횟수',
            value: '${summary.totalSessions}회',
            sub: '연습 ${summary.canvasSessions} · 실전 ${summary.imageSessions}',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _SummaryCard(
            label: '평균 점수',
            value: summary.avgScore.toStringAsFixed(1),
            sub: null,
            trailingIcon: Icon(
              improving ? Icons.trending_up_rounded : Icons.trending_down_rounded,
              size: 16,
              color: improving ? Colors.green : Colors.red,
            ),
            trailingText:
                '${improving ? '+' : ''}${summary.improvementRate.toStringAsFixed(1)}%',
            trailingColor: improving ? Colors.green : Colors.red,
          ),
        ),
      ],
    );
  }

  Widget _buildWeakItemRow(WeakItem item) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Row(
        children: [
          _ModeBadge(mode: item.mode),
          const SizedBox(width: 10),
          Expanded(
            child: Text(item.item, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Text(
            '${item.avgScore.toStringAsFixed(0)}점',
            style: TextStyle(color: Colors.red.shade400, fontWeight: FontWeight.bold),
          ),
          const SizedBox(width: 6),
          Text('· ${item.frequency}회', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
        ],
      ),
    );
  }

  Widget _buildExerciseCard(RecommendedExercise exercise) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _ModeBadge(mode: exercise.mode),
              const SizedBox(width: 8),
              _DifficultyBadge(difficulty: exercise.difficulty),
            ],
          ),
          const SizedBox(height: 8),
          Text(exercise.text, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            children: exercise.targetItems
                .map((t) => Chip(
                      label: Text(t, style: const TextStyle(fontSize: 11)),
                      padding: EdgeInsets.zero,
                      visualDensity: VisualDensity.compact,
                      backgroundColor: Colors.grey.shade200,
                    ))
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.insights_rounded, size: 48, color: Colors.grey.shade300),
            const SizedBox(height: 12),
            const Text(
              '아직 학습 이력이 없어요',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            Text(
              '글씨 연습이나 실전 모드로 한 번 교정을 받아보시면\n여기에 통계와 추이가 표시됩니다.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, color: Colors.red.shade300, size: 40),
            const SizedBox(height: 8),
            Text(_errorMessage!, style: TextStyle(color: Colors.red.shade700)),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: _load, child: const Text('다시 시도')),
          ],
        ),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final String label;
  final String value;
  final String? sub;
  final Widget? trailingIcon;
  final String? trailingText;
  final Color? trailingColor;

  const _SummaryCard({
    required this.label,
    required this.value,
    this.sub,
    this.trailingIcon,
    this.trailingText,
    this.trailingColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          const SizedBox(height: 6),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
              if (trailingIcon != null) ...[
                const SizedBox(width: 6),
                Padding(padding: const EdgeInsets.only(bottom: 3), child: trailingIcon),
              ],
              if (trailingText != null) ...[
                const SizedBox(width: 2),
                Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: Text(
                    trailingText!,
                    style: TextStyle(fontSize: 12, color: trailingColor, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ],
          ),
          if (sub != null) ...[
            const SizedBox(height: 4),
            Text(sub!, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
          ],
        ],
      ),
    );
  }
}

class _ModeBadge extends StatelessWidget {
  final String mode; // "canvas" | "image"
  const _ModeBadge({required this.mode});

  @override
  Widget build(BuildContext context) {
    final isCanvas = mode == 'canvas';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: (isCanvas ? Colors.indigo : Colors.teal).withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        isCanvas ? '연습' : '실전',
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.bold,
          color: isCanvas ? Colors.indigo : Colors.teal,
        ),
      ),
    );
  }
}

class _DifficultyBadge extends StatelessWidget {
  final String difficulty; // "easy" | "medium" | "hard"
  const _DifficultyBadge({required this.difficulty});

  @override
  Widget build(BuildContext context) {
    final label = switch (difficulty) {
      'easy' => '쉬움',
      'hard' => '어려움',
      _ => '보통',
    };
    final color = switch (difficulty) {
      'easy' => Colors.green,
      'hard' => Colors.red,
      _ => Colors.orange,
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: color)),
    );
  }
}

class _FilterChipRow<T> extends StatelessWidget {
  final List<T> values;
  final T selected;
  final String Function(T) labelOf;
  final ValueChanged<T> onSelected;

  const _FilterChipRow({
    required this.values,
    required this.selected,
    required this.labelOf,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: values
            .map((v) => Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    label: Text(labelOf(v), style: const TextStyle(fontSize: 12)),
                    selected: v == selected,
                    onSelected: (_) => onSelected(v),
                    visualDensity: VisualDensity.compact,
                  ),
                ))
            .toList(),
      ),
    );
  }
}
