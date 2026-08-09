import '../../../shared/models/bounding_box.dart';
import '../../../shared/models/feedback_item.dart';
import '../../image_mode/models/detected_char.dart';

/// 화면에서 실제로 그릴 이미지 bbox 오버레이 1개 항목.
///
/// ⚠️ 현재 백엔드(app/api/v1/routes/image.py)는 이미지 모드 피드백을
/// 문자 단위가 아니라 target_id="global" 로만 내려준다 (캔버스 모드와 다름).
/// 그래서 지금은 대부분의 항목에서 [feedback]이 null이 된다 — 이 경우
/// 중립 색상으로 "탐지된 영역"만 표시하고, severity 색상 구분은
/// 백엔드가 문자 단위 피드백을 지원하기 시작하면 자동으로 적용된다.
class ImageBBoxOverlayItem {
  final String charId;
  final BoundingBox boundingBox;
  final FeedbackItem? feedback;

  /// DetectedChar.confidence 그대로 전달.
  /// severity가 없을 때(feedback == null) 색상 힌트로 보조 사용.
  final double? confidence;

  const ImageBBoxOverlayItem({
    required this.charId,
    required this.boundingBox,
    this.feedback,
    this.confidence,
  });

  FeedbackSeverity? get severity =>
      feedback != null ? feedbackSeverityFromString(feedback!.severity) : null;

  static List<ImageBBoxOverlayItem> merge({
    required List<DetectedChar> detectedChars,
    required List<FeedbackItem> feedbackItems,
  }) {
    final feedbackByCharId = {for (final f in feedbackItems) f.targetId: f};

    return detectedChars
        .map((c) => ImageBBoxOverlayItem(
              charId: c.charId,
              boundingBox: c.boundingBox,
              feedback: feedbackByCharId[c.charId], // 현재는 대부분 null (위 설명 참고)
              confidence: c.confidence,
            ))
        .toList();
  }
}
