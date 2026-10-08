import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/canvas_mode/models/canvas_char_analysis.dart';

CanvasCharAnalysis _analysis({
  List<String> failedItems = const [],
  List<Map<String, dynamic>>? boxes,
  List<String> flags = const [],
  bool scorable = true,
}) {
  return CanvasCharAnalysis.fromJson({
    'char_id': 'char_0',
    'failed_items': failedItems,
    'component_boxes': boxes,
    'correction_flags': flags,
    'scorable': scorable,
    'speed_profile': {'mean_speed_px_per_ms': 0.5},
    'overall_score': scorable ? 80 : null,
  });
}

Map<String, dynamic> _box(String role, List<String> failed) => {
      'block': 0,
      'jamo': 'ㄱ',
      'role': role,
      'box': {'x': 0, 'y': 0, 'width': 10, 'height': 10},
      'ok': failed.isEmpty,
      'failed_items': failed,
    };

void main() {
  group('failuresNotOnBoxes', () {
    test('박스가 없는 낱자는 사유 전부가 글자 단위다', () {
      final a = _analysis(failedItems: ['획순(2획 순서 틀림)', '기울기(1획 기울어짐)']);
      expect(a.failuresNotOnBoxes, ['획순(2획 순서 틀림)', '기울기(1획 기울어짐)']);
    });

    test('박스에 실린 항목은 빼고, 자간처럼 박스에 없는 항목만 남긴다', () {
      final a = _analysis(
        failedItems: ['획순(2획 순서 틀림)', '자간(너무 넓음)'],
        boxes: [
          _box('초성', ['획순(1획 순서 틀림)']),
          _box('중성', []),
        ],
      );
      expect(a.failuresNotOnBoxes, ['자간(너무 넓음)']);
    });

    test('사유가 전부 박스에 실렸으면 비어 있다', () {
      final a = _analysis(
        failedItems: ['성분비율(초성 \'ㄱ\' 너무 큼)'],
        boxes: [
          _box('초성', ['성분비율(너무 큼)']),
        ],
      );
      expect(a.failuresNotOnBoxes, isEmpty);
    });

    test('채점을 거부한 글자는 사유를 내지 않는다', () {
      final a = _analysis(failedItems: ['자간(너무 넓음)'], scorable: false);
      expect(a.failuresNotOnBoxes, isEmpty);
    });
  });

  group('axes', () {
    test('축 점수를 읽고, 미측정은 null로 둔다', () {
      final a = CanvasCharAnalysis.fromJson({
        'char_id': 'char_0',
        'axes': {
          '획순': {'score': 100, 'reasons': <String>[]},
          '모양': {'score': 70, 'reasons': ['1획 기울어짐']},
          '짜임새': {'score': null, 'reasons': <String>[]},
          '배치': {'score': null, 'reasons': <String>[]},
        },
        'speed_profile': {'mean_speed_px_per_ms': 0.5},
        'overall_score': 85,
        'correction_flags': <String>[],
      });
      expect(a.axisScore('획순'), 100);
      expect(a.axisScore('모양'), 70);
      expect(a.axisScore('짜임새'), isNull);
      expect(a.axisScore('없는축'), isNull);
    });

    test('axes가 없는 응답(구버전 서버)도 파싱된다', () {
      final a = _analysis();
      expect(a.axes, isEmpty);
      expect(a.axisScore('획순'), isNull);
    });
  });

  group('displayFlags', () {
    test('기록용 진단값(콜론이 든 플래그)은 화면에 내지 않는다', () {
      final a = _analysis(flags: [
        'unscorable',
        'unscorable:shape_mismatch',
        'match_dist:0.455/0.455',
        'ink_gap:0.226',
      ]);
      expect(a.displayFlags, ['unscorable']);
    });

    test('화면에 나가는 플래그는 모두 한글 라벨이 있다', () {
      // ai/canvas/canvas_quality_analyzer.py가 correction_flags에 넣는 코드 전부.
      const flags = [
        'size_large',
        'size_small',
        'spacing_too_narrow',
        'spacing_too_wide',
        'stroke_order_error',
        'stroke_direction_error',
        'stroke_tilt_error',
        'char_rotation_error',
        'corner_rounded',
        'component_balance_error',
        'position_off',
        'shape_off',
        'unscorable',
      ];
      for (final f in flags) {
        expect(CanvasCharAnalysis.flagLabel(f), isNot(f), reason: f);
      }
    });
  });
}
