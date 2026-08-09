import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/canvas_mode/models/char_group.dart';
import 'package:frontend/features/feedback/models/canvas_correction_overlay_item.dart';
import 'package:frontend/features/feedback/models/image_bbox_overlay_item.dart';
import 'package:frontend/features/image_mode/models/detected_char.dart';
import 'package:frontend/shared/models/bounding_box.dart';
import 'package:frontend/shared/models/feedback_item.dart';

/// 오버레이 항목 병합/severity 로직 검증.
/// 백엔드가 bounding_box(group/detect)와 severity(feedback)를 서로 다른 응답으로
/// 주기 때문에 클라이언트가 char_id 기준으로 조인한다.
void main() {
  const box = BoundingBox(x: 0, y: 0, width: 10, height: 10);

  group('feedbackSeverityFromString', () {
    test('문자열을 enum으로 매핑하고, 미상값은 warning으로 처리한다', () {
      expect(feedbackSeverityFromString('good'), FeedbackSeverity.good);
      expect(feedbackSeverityFromString('warning'), FeedbackSeverity.warning);
      expect(feedbackSeverityFromString('error'), FeedbackSeverity.error);
      expect(feedbackSeverityFromString('unknown'), FeedbackSeverity.warning);
    });
  });

  group('CanvasCorrectionOverlayItem.merge', () {
    test('char_id로 group과 feedback을 조인하고, 피드백 없는 문자는 good으로 간주한다', () {
      final items = CanvasCorrectionOverlayItem.merge(
        charGroups: const [
          CharGroup(
              charId: 'c1',
              boundingBox: box,
              strokeCount: 2,
              confidence: 0.9,
              lowConfidence: false),
          CharGroup(
              charId: 'c2',
              boundingBox: box,
              strokeCount: 3,
              confidence: 0.8,
              lowConfidence: false),
        ],
        feedbackItems: const [
          FeedbackItem(targetId: 'c1', feedbackMessage: 'm', severity: 'error'),
        ],
      );

      expect(items.length, 2);
      expect(items[0].feedback, isNotNull);
      expect(items[0].severity, FeedbackSeverity.error);
      // c2는 매칭되는 피드백이 없음 → good
      expect(items[1].feedback, isNull);
      expect(items[1].severity, FeedbackSeverity.good);
    });
  });

  group('ImageBBoxOverlayItem.merge', () {
    test('target_id 불일치 시 severity는 null, confidence는 그대로 전달된다', () {
      final items = ImageBBoxOverlayItem.merge(
        detectedChars: const [
          DetectedChar(charId: 'd1', boundingBox: box, confidence: 0.42),
        ],
        // 현재 백엔드는 문자 단위가 아니라 target_id="global"만 내려줌 → d1과 매칭 안 됨
        feedbackItems: const [
          FeedbackItem(
              targetId: 'global', feedbackMessage: 'm', severity: 'good'),
        ],
      );

      expect(items.single.severity, isNull);
      expect(items.single.confidence, 0.42);
    });

    test('char_id가 일치하면 severity가 매핑된다', () {
      final items = ImageBBoxOverlayItem.merge(
        detectedChars: const [
          DetectedChar(charId: 'd1', boundingBox: box),
        ],
        feedbackItems: const [
          FeedbackItem(
              targetId: 'd1', feedbackMessage: 'm', severity: 'warning'),
        ],
      );

      expect(items.single.severity, FeedbackSeverity.warning);
    });
  });
}
