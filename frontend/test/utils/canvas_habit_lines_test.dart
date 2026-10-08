import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/canvas_mode/models/canvas_char_analysis.dart';
import 'package:frontend/features/feedback/utils/canvas_habit_lines.dart';

/// 우측 "취약한 습관" 카드의 캔버스 줄 — 문제 글자마다 정확히 한 줄, 중복 없음.
CanvasCharAnalysis _char({
  required String id,
  int? score,
  bool scorable = true,
  List<String> failedItems = const [],
  List<Map<String, dynamic>>? boxes,
  List<String> corrections = const [],
}) {
  return CanvasCharAnalysis.fromJson({
    'char_id': id,
    'overall_score': score,
    'scorable': scorable,
    'failed_items': failedItems,
    'component_boxes': boxes,
    'corrections': corrections,
    'speed_profile': {'mean_speed_px_per_ms': 0.5},
    'correction_flags': <String>[],
  });
}

Map<String, dynamic> _box(String role, String jamo, List<String> failed) => {
      'block': 0,
      'jamo': jamo,
      'role': role,
      'box': {'x': 0, 'y': 0, 'width': 10, 'height': 10},
      'ok': failed.isEmpty,
      'failed_items': failed,
    };

void main() {
  test('문장: 거부 글자는 글자 박스 줄 하나로만 나온다(두 줄 중복 금지)', () {
    final lines = canvasHabitLines([
      _char(id: 'char_0', score: 100, boxes: [_box('글자', '각', [])]),
      _char(
        id: 'char_1',
        score: 0,
        scorable: false,
        failedItems: ['다시 써 주세요(목표 글자와 다름)'],
        corrections: ['다시 써 주세요(목표 글자와 다름)'],
        boxes: [_box('글자', '간', ['다시 써 주세요(목표 글자와 다름)'])],
      ),
      _char(
        id: 'char_2',
        score: 70,
        failedItems: ['배치(앞 글자와 너무 좁음)'],
        boxes: [_box('글자', '달', ['배치(앞 글자와 너무 좁음)'])],
      ),
    ]);
    expect(lines.refused, isEmpty);
    expect(lines.boxes, ['간 — 다시 써 주세요(목표 글자와 다름)', '달 — 배치(앞 글자와 너무 좁음)']);
    expect(lines.chars, isEmpty);
    expect(lines.isEmpty, isFalse);
  });

  test('자모음: 박스가 없는 거부 글자는 안내 한 줄', () {
    final lines = canvasHabitLines([
      _char(id: 'char_0', scorable: false, corrections: ['다시 써 주세요(목표 글자와 다름)']),
    ]);
    expect(lines.refused, ['다시 써 주세요(목표 글자와 다름)']);
    expect(lines.boxes, isEmpty);
    expect(lines.chars, isEmpty);
  });

  test('자모음: 박스가 없으면 축 사유가 글자 단위 줄로 나온다', () {
    final lines = canvasHabitLines([
      _char(id: 'char_0', score: 70, failedItems: ['획순(1획 반대로 그음)']),
    ]);
    expect(lines.chars, ['획순(1획 반대로 그음)']);
    expect(lines.boxes, isEmpty);
  });

  test('한 글자: 성분 박스는 자리 이름을 붙이고, 박스에 없는 사유만 글자 줄로', () {
    final lines = canvasHabitLines([
      _char(
        id: 'char_0',
        score: 70,
        failedItems: ['짜임새(종성 \'ㄱ\' 너무 큼)'],
        boxes: [
          _box('초성', 'ㄱ', []),
          _box('중성', 'ㅏ', []),
          _box('종성', 'ㄱ', ['짜임새(너무 큼)']),
        ],
      ),
    ]);
    expect(lines.boxes, ['종성 "ㄱ" — 짜임새(너무 큼)']);
    expect(lines.chars, isEmpty);
  });

  test('모두 통과면 비어 있다', () {
    final lines = canvasHabitLines([
      _char(id: 'char_0', score: 100, boxes: [_box('글자', '각', [])]),
    ]);
    expect(lines.isEmpty, isTrue);
  });
}
