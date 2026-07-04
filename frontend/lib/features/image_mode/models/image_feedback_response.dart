import '../../../shared/models/feedback_item.dart';

/// GET /api/v1/image/{image_session_id}/feedback 응답 (schemas/image.py ImageFeedbackResponse)
///
/// ⚠️ 현재 백엔드는 feedback_items를 문자 단위(char_id)가 아니라
/// target_id="global" 하나로만 내려준다 (routes/image.py 참고).
class ImageFeedbackResponse {
  final String imageSessionId;
  final String mode; // 항상 "image"
  final int overallScore;
  final String achievementMessage;
  final List<FeedbackItem> feedbackItems;

  const ImageFeedbackResponse({
    required this.imageSessionId,
    required this.mode,
    required this.overallScore,
    required this.achievementMessage,
    required this.feedbackItems,
  });

  factory ImageFeedbackResponse.fromJson(Map<String, dynamic> json) {
    return ImageFeedbackResponse(
      imageSessionId: json['image_session_id'] as String,
      mode: json['mode'] as String? ?? 'image',
      overallScore: json['overall_score'] as int,
      achievementMessage: json['achievement_message'] as String,
      feedbackItems: (json['feedback_items'] as List)
          .map((e) => FeedbackItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
