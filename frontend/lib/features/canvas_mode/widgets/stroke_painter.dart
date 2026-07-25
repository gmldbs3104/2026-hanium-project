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

  StrokePainter({
    required this.strokes,
    this.currentStroke,
    this.strokeWidth = 4.0,
    this.showGrid = false,
  });

  /// 격자 한 칸 간격(px)
  static const double _gridSpacing = 40.0;

  void _drawStroke(Canvas canvas, Stroke stroke) {
    if (stroke.points.isEmpty) return;

    final paint = Paint()
      ..color = Colors.black87
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
    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      Paint()..color = Colors.white,
    );

    if (showGrid) _drawGrid(canvas, size);

    for (final stroke in strokes) {
      _drawStroke(canvas, stroke);
    }
    if (currentStroke != null) {
      _drawStroke(canvas, currentStroke!);
    }
  }

  @override
  bool shouldRepaint(covariant StrokePainter oldDelegate) => true;
}
