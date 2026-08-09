import 'package:flutter/material.dart';

import '../../../shared/models/feedback_item.dart';

/// SFR-007 severity 시각 스타일 (색상 + REQ-007-6 색맹 보조 아이콘).
///
/// REQ-007-3: error(빨강) / warning(노랑) / good(초록) 색상 구분
/// REQ-007-6: 색상만으로 구분하기 어려운 사용자를 위해 severity마다 "형태가 뚜렷이 다른"
///            보조 아이콘(✓ / ! / ✕)을 색상과 함께 표시한다.
///
/// 캔버스 오버레이(CanvasCorrectionOverlayPainter)와 이미지 오버레이
/// (ImageBBoxOverlayPainter)가 동일한 색/아이콘 규칙을 쓰도록 이 헬퍼로 통일한다.
class SeverityStyle {
  SeverityStyle._();

  static Color color(FeedbackSeverity severity) {
    switch (severity) {
      case FeedbackSeverity.good:
        return const Color(0xFF34C759);
      case FeedbackSeverity.warning:
        return const Color(0xFFFF9500);
      case FeedbackSeverity.error:
        return const Color(0xFFFF3B30);
    }
  }

  /// REQ-007-6: severity마다 형태가 뚜렷이 다른 보조 아이콘.
  static IconData icon(FeedbackSeverity severity) {
    switch (severity) {
      case FeedbackSeverity.good:
        return Icons.check_rounded;
      case FeedbackSeverity.warning:
        return Icons.priority_high_rounded;
      case FeedbackSeverity.error:
        return Icons.close_rounded;
    }
  }

  /// REQ-007-6: 오버레이 박스 모서리에 [색상 원형 배지 + 흰색 아이콘]을 그린다.
  /// 색상(REQ-007-3)과 형태(아이콘)를 함께 제공해 색맹 사용자도 구분할 수 있게 한다.
  static void paintBadge(Canvas canvas, Offset center, FeedbackSeverity severity) {
    const radius = 9.0;
    final c = color(severity);

    canvas.drawCircle(center, radius, Paint()..color = c);
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    final iconData = icon(severity);
    final tp = TextPainter(
      textDirection: TextDirection.ltr,
      text: TextSpan(
        text: String.fromCharCode(iconData.codePoint),
        style: TextStyle(
          fontSize: 13,
          height: 1.0,
          fontFamily: iconData.fontFamily,
          package: iconData.fontPackage,
          color: Colors.white,
        ),
      ),
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }
}
