import '../../canvas_mode/models/canvas_char_analysis.dart';
import '../models/component_overlay_item.dart';

/// 우측 "취약한 습관" 카드에 쓸 캔버스 줄 묶음 (2026-10-08 축 재설계).
///
/// 캔버스 위에는 박스만 그리고, 사유 글자는 전부 이 카드에 쓴다. 문제 글자마다
/// **정확히 한 줄**이어야 한다 — 문장의 거부 글자는 글자 박스가 있으므로 박스 줄로만
/// 나오고, 박스가 없는 낱자·한 글자의 거부만 [refused]로 따로 안내한다.
class CanvasHabitLines {
  /// 박스가 없는 거부 글자(자모음·한 글자) 안내 — "다시 써 주세요(…)"
  final List<String> refused;

  /// 빨간 박스마다 한 줄. 성분 박스는 `초성 "ㄱ" — …`, 문장의 글자 박스는 `원 — …`.
  final List<String> boxes;

  /// 박스에 실리지 않은 글자 단위 사유. 같은 사유가 여러 글자면 묶어 `— N자`.
  final List<String> chars;

  const CanvasHabitLines({
    required this.refused,
    required this.boxes,
    required this.chars,
  });

  bool get isEmpty => refused.isEmpty && boxes.isEmpty && chars.isEmpty;
}

/// 빨간 박스 한 줄. 문장의 글자 박스(role '글자')는 목표 글자만 앞에 둔다.
String boxLine(ComponentOverlayItem c) {
  final reasons = c.failedItems.join(', ');
  return c.role == '글자' ? '${c.jamo} — $reasons' : '${c.role} "${c.jamo}" — $reasons';
}

CanvasHabitLines canvasHabitLines(Iterable<CanvasCharAnalysis> analyses) {
  final list = analyses.toList();

  final refused = <String>[];
  for (final a in list) {
    final hasBoxes = a.componentBoxes != null && a.componentBoxes!.isNotEmpty;
    if (!a.scorable && !hasBoxes) {
      refused.add(a.corrections.isNotEmpty
          ? a.corrections.first
          : '목표 글자와 달라 채점할 수 없어요. 다시 써 주세요.');
    }
  }

  final boxes = ComponentOverlayItem.fromAnalyses(list)
      .where((c) => !c.ok)
      .map(boxLine)
      .toList();

  final counts = <String, int>{};
  for (final a in list) {
    for (final f in a.failuresNotOnBoxes) {
      counts[f] = (counts[f] ?? 0) + 1;
    }
  }
  final chars = counts.entries
      .map((e) => e.value > 1 ? '${e.key} — ${e.value}자' : e.key)
      .toList();

  return CanvasHabitLines(refused: refused, boxes: boxes, chars: chars);
}
