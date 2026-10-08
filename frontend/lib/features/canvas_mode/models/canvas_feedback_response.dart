import '../../../shared/models/feedback_item.dart';
import '../../../shared/models/weak_habit.dart';

/// GET /api/v1/canvas/{canvas_session_id}/feedback 응답 (schemas/canvas.py CanvasFeedbackResponse)
class CanvasFeedbackResponse {
  final String canvasSessionId;
  final String mode; // 항상 "canvas"
  /// ⚠️ **채점 불가면 null**이다(0점 아님). 목표 글자와 달라 점수를 매기지 않은 경우로,
  /// 화면은 숫자 대신 "채점 불가"를 보여줘야 한다(2026-09-17).
  final int? overallScore;
  final String achievementMessage;
  final List<FeedbackItem> feedbackItems;

  /// AI 분석: 취약한 습관 (백엔드 신규 필드 `weak_habits`, 없으면 빈 리스트)
  final List<WeakHabit> weakHabits;

  /// 목표 점수 (백엔드 신규 필드 `target_score`, 없으면 90 기본)
  final int targetScore;

  /// 직전 대비 점수 변화량 (백엔드 신규 필드 `score_trend`, 없으면 null → 추세 배지 미표시)
  final int? scoreTrend;

  const CanvasFeedbackResponse({
    required this.canvasSessionId,
    required this.mode,
    this.overallScore,
    required this.achievementMessage,
    required this.feedbackItems,
    this.weakHabits = const [],
    this.targetScore = 90,
    this.scoreTrend,
  });

  factory CanvasFeedbackResponse.fromJson(Map<String, dynamic> json) {
    return CanvasFeedbackResponse(
      canvasSessionId: json['canvas_session_id'] as String,
      mode: json['mode'] as String? ?? 'canvas',
      overallScore: (json['overall_score'] as num?)?.toInt(),
      achievementMessage: json['achievement_message'] as String,
      feedbackItems: (json['feedback_items'] as List)
          .map((e) => FeedbackItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      // 아래 3개는 백엔드 연동 예정 — 없으면 기본값으로 안전 처리한다.
      weakHabits: WeakHabit.listFromJson(json),
      targetScore: (json['target_score'] as num?)?.toInt() ?? 90,
      scoreTrend: (json['score_trend'] as num?)?.toInt(),
    );
  }
}
