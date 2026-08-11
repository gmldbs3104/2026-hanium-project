import 'package:flutter/material.dart';

import '../models/dashboard_response.dart';

/// 날짜별 평균 점수 추이를 보여주는 간단한 선 그래프.
/// 외부 차트 라이브러리 없이 CustomPainter로 직접 그린다 (프로젝트에 차트
/// 패키지가 없어서, 기존에 stroke/overlay를 그릴 때 쓴 방식과 통일했다).
///
/// [points]는 mode("canvas"|"image")가 섞여 있을 수 있다 — 이 위젯이 mode별로
/// 나눠서 [canvasColor]/[imageColor]로 각각의 선을 그린다(한쪽 데이터가 없으면
/// 그 계열만 생략). 예전엔 mode를 무시하고 한 가지 색으로 전부 이어 그렸었다.
class ScoreTrendChart extends StatelessWidget {
  final List<ScoreTrendPoint> points;
  final Color canvasColor;
  final Color imageColor;

  const ScoreTrendChart({
    super.key,
    required this.points,
    required this.canvasColor,
    required this.imageColor,
  });

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
          canvasColor: canvasColor,
          imageColor: imageColor,
        ),
      ),
    );
  }
}

class _ScoreTrendPainter extends CustomPainter {
  final List<ScoreTrendPoint> points;
  final Color canvasColor;
  final Color imageColor;

  _ScoreTrendPainter({
    required this.points,
    required this.canvasColor,
    required this.imageColor,
  });

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

    // 두 계열이 같은 날짜 축 위에 겹쳐 그려지도록, 인덱스가 아니라 실제 날짜값으로
    // x좌표를 계산한다(계열마다 날짜가 다를 수 있어서 인덱스 기반이면 어긋난다).
    final sortedDates = points.map((p) => p.date).toList()..sort();
    final minDate = sortedDates.first;
    final maxDate = sortedDates.last;
    final totalMs = maxDate.difference(minDate).inMilliseconds;

    double xFor(DateTime d) =>
        totalMs == 0 ? size.width / 2 : size.width * d.difference(minDate).inMilliseconds / totalMs;
    double yFor(double score) {
      final normalized = (score - _minScore) / (_maxScore - _minScore);
      return chartHeight * (1 - normalized.clamp(0.0, 1.0));
    }

    final canvasSeries = points.where((p) => p.mode == 'canvas').toList()
      ..sort((a, b) => a.date.compareTo(b.date));
    final imageSeries = points.where((p) => p.mode == 'image').toList()
      ..sort((a, b) => a.date.compareTo(b.date));

    _drawSeries(canvas, canvasSeries, canvasColor, chartHeight, xFor, yFor);
    _drawSeries(canvas, imageSeries, imageColor, chartHeight, xFor, yFor);

    _drawDateLabel(canvas, minDate, Offset(0, chartHeight + 4), TextAlign.left);
    _drawDateLabel(canvas, maxDate, Offset(size.width, chartHeight + 4), TextAlign.right);
  }

  void _drawSeries(
    Canvas canvas,
    List<ScoreTrendPoint> series,
    Color color,
    double chartHeight,
    double Function(DateTime) xFor,
    double Function(double) yFor,
  ) {
    if (series.isEmpty) return;

    if (series.length == 1) {
      canvas.drawCircle(
        Offset(xFor(series.first.date), yFor(series.first.avgScore)),
        4,
        Paint()..color = color,
      );
      return;
    }

    final path = Path();
    for (var i = 0; i < series.length; i++) {
      final x = xFor(series[i].date);
      final y = yFor(series[i].avgScore);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }

    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round,
    );

    // 각 데이터 포인트에 작은 점을 찍어 두 계열이 겹칠 때도 구분이 되도록 한다.
    for (final p in series) {
      canvas.drawCircle(Offset(xFor(p.date), yFor(p.avgScore)), 2.5, Paint()..color = color);
    }
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
    return !identical(oldDelegate.points, points) ||
        oldDelegate.canvasColor != canvasColor ||
        oldDelegate.imageColor != imageColor;
  }
}
