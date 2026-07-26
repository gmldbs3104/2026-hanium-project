/// GET /api/v1/dashboard 응답 모델
/// (requirement.md SFR-008 Outputs 스키마 기준)
///
/// {
///   period_summary: {...},
///   weak_items: [...],
///   score_trend: [...],
///   recommended_exercises: [...]
/// }
class DashboardResponse {
  final PeriodSummary periodSummary;
  final List<WeakItem> weakItems;
  final List<ScoreTrendPoint> scoreTrend;
  final List<RecommendedExercise> recommendedExercises;

  const DashboardResponse({
    required this.periodSummary,
    required this.weakItems,
    required this.scoreTrend,
    required this.recommendedExercises,
  });

  /// REQ-008-5: 교정 세션 이력이 하나도 없는 신규 사용자
  bool get isEmpty => periodSummary.totalSessions == 0;

  factory DashboardResponse.fromJson(Map<String, dynamic> json) {
    return DashboardResponse(
      periodSummary: PeriodSummary.fromJson(json['period_summary'] as Map<String, dynamic>),
      weakItems: (json['weak_items'] as List)
          .map((e) => WeakItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      scoreTrend: (json['score_trend'] as List)
          .map((e) => ScoreTrendPoint.fromJson(e as Map<String, dynamic>))
          .toList(),
      recommendedExercises: (json['recommended_exercises'] as List)
          .map((e) => RecommendedExercise.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// {total_sessions, avg_score, improvement_rate(%), canvas_sessions, image_sessions}
class PeriodSummary {
  final int totalSessions;
  final double avgScore;
  final double improvementRate;
  final int canvasSessions;
  final int imageSessions;

  const PeriodSummary({
    required this.totalSessions,
    required this.avgScore,
    required this.improvementRate,
    required this.canvasSessions,
    required this.imageSessions,
  });

  factory PeriodSummary.fromJson(Map<String, dynamic> json) {
    return PeriodSummary(
      totalSessions: json['total_sessions'] as int,
      avgScore: (json['avg_score'] as num).toDouble(),
      improvementRate: (json['improvement_rate'] as num).toDouble(),
      canvasSessions: json['canvas_sessions'] as int,
      imageSessions: json['image_sessions'] as int,
    );
  }
}

/// {item, avg_score, frequency, mode} — REQ-008-3: 최근 30일 기준 하위 10개
class WeakItem {
  final String item;
  final double avgScore;
  final int frequency;
  final String mode; // "canvas" | "image"

  const WeakItem({
    required this.item,
    required this.avgScore,
    required this.frequency,
    required this.mode,
  });

  factory WeakItem.fromJson(Map<String, dynamic> json) {
    return WeakItem(
      item: json['item'] as String,
      avgScore: (json['avg_score'] as num).toDouble(),
      frequency: json['frequency'] as int,
      mode: json['mode'] as String,
    );
  }
}

/// {date, avg_score, mode} — 날짜별 평균 점수 추이
class ScoreTrendPoint {
  final DateTime date;
  final double avgScore;
  final String mode;

  const ScoreTrendPoint({
    required this.date,
    required this.avgScore,
    required this.mode,
  });

  factory ScoreTrendPoint.fromJson(Map<String, dynamic> json) {
    return ScoreTrendPoint(
      date: DateTime.parse(json['date'] as String),
      avgScore: (json['avg_score'] as num).toDouble(),
      mode: json['mode'] as String,
    );
  }
}

/// {text, target_items[], difficulty, mode} — REQ-008-4: 3~5개, 난이도순
class RecommendedExercise {
  final String text;
  final List<String> targetItems;
  final String difficulty; // 서버 값 그대로 보관 (예: "easy" | "medium" | "hard")
  final String mode;

  const RecommendedExercise({
    required this.text,
    required this.targetItems,
    required this.difficulty,
    required this.mode,
  });

  factory RecommendedExercise.fromJson(Map<String, dynamic> json) {
    return RecommendedExercise(
      text: json['text'] as String,
      targetItems: (json['target_items'] as List).map((e) => e as String).toList(),
      difficulty: json['difficulty'] as String,
      mode: json['mode'] as String,
    );
  }
}

/// 조회 기간 필터 (SFR-008 Inputs: period)
enum DashboardPeriod { week, month, all }

extension DashboardPeriodValue on DashboardPeriod {
  String get value => name;

  String get label {
    switch (this) {
      case DashboardPeriod.week:
        return '이번 주';
      case DashboardPeriod.month:
        return '이번 달';
      case DashboardPeriod.all:
        return '전체';
    }
  }
}

/// 모드 필터 (SFR-008 Inputs: mode)
enum DashboardModeFilter { canvas, image, all }

extension DashboardModeFilterValue on DashboardModeFilter {
  String get value => name;

  String get label {
    switch (this) {
      case DashboardModeFilter.canvas:
        return '글씨 연습';
      case DashboardModeFilter.image:
        return '실전 모드';
      case DashboardModeFilter.all:
        return '전체';
    }
  }
}
