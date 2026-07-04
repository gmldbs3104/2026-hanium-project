import '../../../shared/models/bounding_box.dart';
import '../../../shared/models/feedback_item.dart';
import '../../canvas_mode/models/char_group.dart';

/// 화면에서 실제로 그릴 교정 오버레이 1개 항목.
///
/// 백엔드가 bounding_box(POST /group)와 severity/message(GET /feedback)를
/// 서로 다른 응답으로 나눠서 주기 때문에, char_id == target_id 기준으로
/// 클라이언트에서 두 응답을 조인해서 만든다.
class CanvasCorrectionOverlayItem {
  final String charId;
  final BoundingBox boundingBox;
  final FeedbackItem? feedback; // null이면 해당 문자에 대한 피드백이 없음(=good으로 간주 가능)

  const CanvasCorrectionOverlayItem({
    required this.charId,
    required this.boundingBox,
    this.feedback,
  });

  FeedbackSeverity get severity =>
      feedback != null ? feedbackSeverityFromString(feedback!.severity) : FeedbackSeverity.good;

  /// [charGroups] (POST /api/v1/canvas/{id}/group 응답) 과
  /// [feedbackItems] (GET /api/v1/canvas/{id}/feedback 응답) 을 char_id 기준으로 조인
  static List<CanvasCorrectionOverlayItem> merge({
    required List<CharGroup> charGroups,
    required List<FeedbackItem> feedbackItems,
  }) {
    final feedbackByCharId = {for (final f in feedbackItems) f.targetId: f};

    return charGroups
        .map((group) => CanvasCorrectionOverlayItem(
              charId: group.charId,
              boundingBox: group.boundingBox,
              feedback: feedbackByCharId[group.charId],
            ))
        .toList();
  }
}
