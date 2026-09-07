import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/canvas_mode/models/char_group.dart';
import 'package:frontend/features/feedback/models/canvas_correction_overlay_item.dart';
import 'package:frontend/features/feedback/models/image_bbox_overlay_item.dart';
import 'package:frontend/features/image_mode/models/detected_char.dart';
import 'package:frontend/features/image_mode/models/image_char_box.dart';
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
    test('서버가 ok:true로 판정한 글자는 초록(ok)으로 표시한다', () {
      final items = ImageBBoxOverlayItem.merge(
        detectedChars: const [
          DetectedChar(charId: 'd1', boundingBox: box, confidence: 0.42),
        ],
        charBoxes: const [
          ImageCharBox(charId: 'd1', boundingBox: box, ok: true, failedItems: []),
        ],
      );

      expect(items.single.ok, isTrue);
      expect(items.single.confidence, 0.42);
    });

    test('서버가 ok:false로 판정한 글자는 failedItems와 함께 빨강으로 표시한다', () {
      final items = ImageBBoxOverlayItem.merge(
        detectedChars: const [
          DetectedChar(charId: 'd1', boundingBox: box),
        ],
        charBoxes: const [
          ImageCharBox(
              charId: 'd1', boundingBox: box, ok: false, failedItems: ['크기(너무 큼)']),
        ],
      );

      expect(items.single.ok, isFalse);
      expect(items.single.failedItems, ['크기(너무 큼)']);
      expect(items.single.message, contains('크기(너무 큼)'));
    });

    test('서버 판정이 없는 글자(구버전 응답 등)는 안 잰 것을 감점하지 않고 통과로 둔다', () {
      final items = ImageBBoxOverlayItem.merge(
        detectedChars: const [
          DetectedChar(charId: 'd1', boundingBox: box),
        ],
        charBoxes: const [],
      );

      expect(items.single.ok, isTrue);
    });
  });
}
