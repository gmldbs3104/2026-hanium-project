/// backend CanvasFeedbackResponse.feedback_items / ImageFeedbackResponse.feedback_items 공통 구조
/// (schemas/canvas.py FeedbackItem, schemas/image.py ImageFeedbackItem — 필드 동일)
class FeedbackItem {
  /// 캔버스 모드: char_id / 이미지 모드: 현재는 "global"만 사용 (백엔드 아직 문자 단위 미지원)
  final String targetId;
  final String feedbackMessage;

  /// "good" | "warning" | "error"
  final String severity;

  const FeedbackItem({
    required this.targetId,
    required this.feedbackMessage,
    required this.severity,
  });

  factory FeedbackItem.fromJson(Map<String, dynamic> json) {
    return FeedbackItem(
      targetId: json['target_id'] as String,
      feedbackMessage: json['feedback_message'] as String,
      severity: json['severity'] as String,
    );
  }
}

/// severity 문자열 -> 렌더링 색상/스타일 헬퍼
enum FeedbackSeverity { good, warning, error }

FeedbackSeverity feedbackSeverityFromString(String value) {
  switch (value) {
    case 'good':
      return FeedbackSeverity.good;
    case 'warning':
      return FeedbackSeverity.warning;
    case 'error':
      return FeedbackSeverity.error;
    default:
      return FeedbackSeverity.warning;
  }
}
