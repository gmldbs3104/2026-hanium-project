import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/feedback/utils/severity_style.dart';
import 'package:frontend/shared/models/feedback_item.dart';

/// SFR-007 오버레이 severity 스타일 검증.
void main() {
  const severities = [
    FeedbackSeverity.good,
    FeedbackSeverity.warning,
    FeedbackSeverity.error,
  ];

  test('REQ-007-3: severity마다 색상이 서로 다르다', () {
    final colors = severities.map(SeverityStyle.color).toSet();
    expect(colors.length, 3);
  });

  test('REQ-007-6: severity마다 보조 아이콘(형태)이 서로 다르다', () {
    final iconCodes =
        severities.map((s) => SeverityStyle.icon(s).codePoint).toSet();
    expect(iconCodes.length, 3);
  });
}
