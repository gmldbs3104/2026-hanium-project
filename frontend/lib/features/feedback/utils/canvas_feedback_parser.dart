import '../../../shared/models/feedback_item.dart';

/// backend `feedback_generator.py`의 `generate_canvas_feedback()`는 획순/자간/크기
/// 피드백 문장을 공백으로 이어붙인 문자열 하나를 `feedback_message`로 주고, severity는
/// 그 문자의 종합 점수 기준 하나뿐이다(부분별 색이 없다). 각 부분을 따로 색칠하려면
/// 프론트가 문장 단위로 다시 나눠서 색을 매겨야 한다.
///
/// ⚠️ 처음엔 정확한 문구 전체("표준 획순을 다시 확인해보세요" 등)를 통째로 매칭하는
/// 방식으로 만들었는데, 실제 문구가 조금만 달라도(예: "획순을 확인해보세요") 통째로
/// 실패해서 항상 폴백(한 덩어리)으로 빠졌다. 그래서 **키워드 기반**으로 다시 만들었다 —
/// 문장에 어떤 단어가 들어있는지만 보고 주제(획순/자간/크기)와 심각도를 판단하므로
/// 백엔드 문구가 조금 바뀌어도 잘 버틴다:
///   - 새 주제 시작: "획순" 포함 → 획순 / "자간" 포함 → 자간 /
///     "글자"+("크기" 또는 "%") 포함 → 크기 / 그 외는 새 주제로 보지 않고
///     직전 주제에 이어붙인다(예: "글자를 더 가깝게 써보세요"는 자간 설명의 연속문).
///   - 심각도: "오류" 포함 → error(빨강) / "적절"·"정확"·"균일"·"좋습" 포함 → good(초록) /
///     그 외(기준을 벗어남을 설명하는 문장) → warning(주황).
///     한 그룹에 여러 문장이 있으면 그중 가장 심각한 색을 그룹 전체 색으로 쓴다.
List<({String text, FeedbackSeverity severity})> parseCanvasFeedbackParts(String message) {
  final sentences = _splitSentences(message);
  if (sentences.isEmpty) return const [];

  final groups = <({String topic, List<String> sentences, List<FeedbackSeverity> severities})>[];

  for (final s in sentences) {
    final newTopic = _newTopicFor(s);
    final severity = _severityOf(s);

    if (newTopic != null && (groups.isEmpty || groups.last.topic != newTopic)) {
      groups.add((topic: newTopic, sentences: [s], severities: [severity]));
    } else if (groups.isNotEmpty) {
      groups.last.sentences.add(s);
      groups.last.severities.add(severity);
    } else {
      groups.add((topic: 'other', sentences: [s], severities: [severity]));
    }
  }

  return groups
      .map((g) => (text: g.sentences.join(' '), severity: g.severities.reduce(_worse)))
      .toList();
}

/// ". "(마침표+공백)로 문장을 나누고, 분리 과정에서 사라진 마침표를 다시 붙인다.
/// "26.4%"/"8.0px"처럼 공백 없는 소수점은 마침표 뒤에 공백이 없어 분리되지 않는다.
List<String> _splitSentences(String message) {
  final result = <String>[];
  for (final raw in message.trim().split('. ')) {
    var s = raw.trim();
    if (s.isEmpty) continue;
    if (!s.endsWith('.')) s = '$s.';
    result.add(s);
  }
  return result;
}

String? _newTopicFor(String s) {
  if (s.contains('획순')) return 'stroke';
  if (s.contains('자간')) return 'spacing';
  if (s.contains('글자') && (s.contains('크기') || s.contains('%'))) return 'size';
  return null;
}

FeedbackSeverity _severityOf(String s) {
  if (s.contains('오류')) return FeedbackSeverity.error;
  if (s.contains('적절') || s.contains('정확') || s.contains('균일') || s.contains('좋습')) {
    return FeedbackSeverity.good;
  }
  return FeedbackSeverity.warning;
}

FeedbackSeverity _worse(FeedbackSeverity a, FeedbackSeverity b) {
  const rank = {FeedbackSeverity.good: 0, FeedbackSeverity.warning: 1, FeedbackSeverity.error: 2};
  return rank[a]! >= rank[b]! ? a : b;
}
