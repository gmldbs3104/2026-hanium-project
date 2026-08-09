import '../../../shared/models/feedback_item.dart';
import '../../../shared/models/weak_habit.dart';

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

  /// AI 분석: 취약한 습관 (백엔드 신규 필드 `weak_habits`, 없으면 빈 리스트)
  final List<WeakHabit> weakHabits;

  /// 목표 점수 (백엔드 신규 필드 `target_score`, 없으면 90 기본)
  final int targetScore;

  /// 직전 대비 점수 변화량 (백엔드 신규 필드 `score_trend`, 없으면 null → 추세 배지 미표시)
  final int? scoreTrend;

  const ImageFeedbackResponse({
    required this.imageSessionId,
    required this.mode,
    required this.overallScore,
    required this.achievementMessage,
    required this.feedbackItems,
    this.weakHabits = const [],
    this.targetScore = 90,
    this.scoreTrend,
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
      // 아래 3개는 백엔드 연동 예정 — 없으면 기본값으로 안전 처리한다.
      weakHabits: WeakHabit.listFromJson(json),
      targetScore: (json['target_score'] as num?)?.toInt() ?? 90,
      scoreTrend: (json['score_trend'] as num?)?.toInt(),
    );
  }
}
