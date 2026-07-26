import '../../../shared/models/feedback_item.dart';

/// GET /api/v1/canvas/{canvas_session_id}/feedback 응답 (schemas/canvas.py CanvasFeedbackResponse)
class CanvasFeedbackResponse {
  final String canvasSessionId;
  final String mode; // 항상 "canvas"
  final int overallScore;
  final String achievementMessage;
  final List<FeedbackItem> feedbackItems;

  const CanvasFeedbackResponse({
    required this.canvasSessionId,
    required this.mode,
    required this.overallScore,
    required this.achievementMessage,
    required this.feedbackItems,
  });

  factory CanvasFeedbackResponse.fromJson(Map<String, dynamic> json) {
    return CanvasFeedbackResponse(
      canvasSessionId: json['canvas_session_id'] as String,
      mode: json['mode'] as String? ?? 'canvas',
      overallScore: json['overall_score'] as int,
      achievementMessage: json['achievement_message'] as String,
      feedbackItems: (json['feedback_items'] as List)
          .map((e) => FeedbackItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
