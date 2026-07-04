import 'package:flutter/material.dart';

import '../models/dashboard_response.dart';

/// 날짜별 평균 점수 추이를 보여주는 간단한 선 그래프.
/// 외부 차트 라이브러리 없이 CustomPainter로 직접 그린다 (프로젝트에 차트
/// 패키지가 없어서, 기존에 stroke/overlay를 그릴 때 쓴 방식과 통일했다).
class ScoreTrendChart extends StatelessWidget {
  final List<ScoreTrendPoint> points;

  const ScoreTrendChart({super.key, required this.points});

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) {
      return const SizedBox.shrink();
    }

    return SizedBox(
      height: 160,
      child: CustomPaint(
        painter: _ScoreTrendPainter(
          points: points,
          lineColor: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }
}

class _ScoreTrendPainter extends CustomPainter {
  final List<ScoreTrendPoint> points;
  final Color lineColor;

  _ScoreTrendPainter({required this.points, required this.lineColor});

  static const double _minScore = 0;
  static const double _maxScore = 100;
  static const double _bottomAxisHeight = 20;

  @override
  void paint(Canvas canvas, Size size) {
    final chartHeight = size.height - _bottomAxisHeight;

    // 배경 가이드라인 (0, 50, 100점)
    final gridPaint = Paint()
      ..color = Colors.grey.shade200
      ..strokeWidth = 1;
    for (final ratio in [0.0, 0.5, 1.0]) {
      final y = chartHeight * (1 - ratio);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    if (points.length < 2) {
      _drawSinglePoint(canvas, size, chartHeight);
      return;
    }

    final stepX = size.width / (points.length - 1);
    final path = Path();
    final fillPath = Path();

    for (var i = 0; i < points.length; i++) {
      final x = stepX * i;
      final normalized = (points[i].avgScore - _minScore) / (_maxScore - _minScore);
      final y = chartHeight * (1 - normalized.clamp(0.0, 1.0));

      if (i == 0) {
        path.moveTo(x, y);
        fillPath.moveTo(x, chartHeight);
        fillPath.lineTo(x, y);
      } else {
        path.lineTo(x, y);
        fillPath.lineTo(x, y);
      }

      if (i == points.length - 1) {
        fillPath.lineTo(x, chartHeight);
        fillPath.close();
      }
    }

    canvas.drawPath(
      fillPath,
      Paint()
        ..color = lineColor.withValues(alpha: 0.08)
        ..style = PaintingStyle.fill,
    );

    canvas.drawPath(
      path,
      Paint()
        ..color = lineColor
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round,
    );

    // 시작/끝 날짜 라벨
    _drawDateLabel(canvas, points.first.date, Offset(0, chartHeight + 4), TextAlign.left);
    _drawDateLabel(
      canvas,
      points.last.date,
      Offset(size.width, chartHeight + 4),
      TextAlign.right,
    );
  }

  void _drawSinglePoint(Canvas canvas, Size size, double chartHeight) {
    final normalized = (points.first.avgScore - _minScore) / (_maxScore - _minScore);
    final y = chartHeight * (1 - normalized.clamp(0.0, 1.0));
    canvas.drawCircle(Offset(size.width / 2, y), 4, Paint()..color = lineColor);
  }

  void _drawDateLabel(Canvas canvas, DateTime date, Offset anchor, TextAlign align) {
    final text = '${date.month}/${date.day}';
    final textPainter = TextPainter(
      text: TextSpan(text: text, style: TextStyle(fontSize: 10, color: Colors.grey.shade600)),
      textDirection: TextDirection.ltr,
    )..layout();

    final dx = align == TextAlign.left ? anchor.dx : anchor.dx - textPainter.width;
    textPainter.paint(canvas, Offset(dx, anchor.dy));
  }

  @override
  bool shouldRepaint(covariant _ScoreTrendPainter oldDelegate) {
    return !identical(oldDelegate.points, points) || oldDelegate.lineColor != lineColor;
  }
}
