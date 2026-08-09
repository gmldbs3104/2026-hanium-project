import 'package:flutter/material.dart';

import '../models/stroke.dart';

/// 수집된 획들을 화면에 그려주는 Painter
/// REQ-003C-5: RepaintBoundary와 함께 사용하여 프레임 드롭 방지
///
/// SFR-003C Inputs의 캔버스 설정을 반영한다:
///  - [strokeWidth] 선 굵기 (가늘게 2.0 / 보통 4.0 / 굵게 7.0)
///  - [showGrid] 격자 표시 여부 (필기 보조선, 분석 대상 아님)
class StrokePainter extends CustomPainter {
  final List<Stroke> strokes;
  final Stroke? currentStroke;
  final double strokeWidth;
  final bool showGrid;

  /// SFR-003C 확장(UI 리디자인): 펜 색상, 옅은 가이드 글자, 기준 점선 표시
  final Color penColor;
  final String? guideText;
  final bool showBaseline;

  /// false면 흰 배경을 칠하지 않는다(뒤의 가이드 문장이 비쳐 보이도록).
  final bool fillBackground;

  StrokePainter({
    required this.strokes,
    this.currentStroke,
    this.strokeWidth = 4.0,
    this.showGrid = false,
    this.penColor = Colors.black87,
    this.guideText,
    this.showBaseline = false,
    this.fillBackground = true,
  });

  /// 격자 한 칸 간격(px)
  static const double _gridSpacing = 40.0;

  void _drawStroke(Canvas canvas, Stroke stroke) {
    if (stroke.points.isEmpty) return;

    final paint = Paint()
      ..color = penColor
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;

    final path = Path()..moveTo(stroke.points.first.x, stroke.points.first.y);
    for (final point in stroke.points.skip(1)) {
      path.lineTo(point.x, point.y);
    }
    canvas.drawPath(path, paint);
  }

  /// SFR-003C Inputs: 격자 표시. 필기 정렬을 돕는 보조선이며 획 데이터에는 포함되지 않는다.
  void _drawGrid(Canvas canvas, Size size) {
    final gridPaint = Paint()
      ..color = Colors.blueGrey.withValues(alpha: 0.15)
      ..strokeWidth = 1.0
      ..style = PaintingStyle.stroke;

    for (double x = _gridSpacing; x < size.width; x += _gridSpacing) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = _gridSpacing; y < size.height; y += _gridSpacing) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    // 캔버스 배경 (흰 배경 + 선택 시 격자)
    if (fillBackground) {
      canvas.drawRect(
        Rect.fromLTWH(0, 0, size.width, size.height),
        Paint()..color = Colors.white,
      );
    }

    if (showGrid) _drawGrid(canvas, size);
    if (showBaseline) _drawBaseline(canvas, size);
    if (guideText != null && guideText!.isNotEmpty) {
      _drawGuideText(canvas, size);
    }

    for (final stroke in strokes) {
      _drawStroke(canvas, stroke);
    }
    if (currentStroke != null) {
      _drawStroke(canvas, currentStroke!);
    }
  }

  /// 기준선(가로 점선) — 글자 정렬 보조. 분석 대상 아님.
  void _drawBaseline(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFFB9C0C9)
      ..strokeWidth = 1.2;
    const dash = 6.0, gap = 6.0;
    for (final ratio in [0.42, 0.62]) {
      final y = size.height * ratio;
      double x = 0;
      while (x < size.width) {
        canvas.drawLine(Offset(x, y), Offset(x + dash, y), paint);
        x += dash + gap;
      }
    }
  }

  /// 옅은 가이드 글자 (점선을 따라 연습할 기준 글자)
  void _drawGuideText(Canvas canvas, Size size) {
    final tp = TextPainter(
      text: TextSpan(
        text: guideText,
        style: TextStyle(
          fontSize: size.height * 0.34,
          fontWeight: FontWeight.w600,
          color: const Color(0xFFDCE1E7),
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(
      canvas,
      Offset((size.width - tp.width) / 2, (size.height - tp.height) / 2),
    );
  }

  @override
  bool shouldRepaint(covariant StrokePainter oldDelegate) => true;
}
