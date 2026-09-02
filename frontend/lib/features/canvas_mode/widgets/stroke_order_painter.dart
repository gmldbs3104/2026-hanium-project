import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../data/stroke_order_data.dart';

/// 획순 가이드 페인터.
///
/// 1) 연습 글자를 **명조체(serif)** 글자로 연하게 렌더링하고,
/// 2) 각 획의 시작점에 순서 번호(①②③…)만 얹는다. (화살표는 표시하지 않음)
///
/// 글자(명조체)와 순서 번호는 같은 정사각 박스에 매핑되어 서로 정렬된다.
///
/// ⚠️ 이 박스는 **크기 채점의 기준**이기도 하다. 서버가 "표준만큼 크게 썼는가"를
/// 판정하려면 사용자가 본 가이드 영역을 알아야 하므로, 같은 값을 guide_box로
/// 함께 보낸다(canvas_api_service.analyze). 그래서 계산을 여기 한 곳에 두고
/// 페인터와 전송이 같은 함수를 부른다 — 두 벌로 두면 조용히 어긋난다.
Rect strokeGuideBox(Size size) {
  final s = math.min(size.width, size.height) * 0.88;
  return Rect.fromLTWH((size.width - s) / 2, (size.height - s) / 2, s, s);
}

class StrokeOrderGuidePainter extends CustomPainter {
  final String char;
  final List<GuideStroke> strokes;
  final Color glyphColor;
  final Color markerColor;

  StrokeOrderGuidePainter(
    this.char,
    this.strokes, {
    this.glyphColor = const Color(0xFFAFDBCB),
    this.markerColor = const Color(0xFF23A896),
  });

  @override
  void paint(Canvas canvas, Size size) {
    // 글자·화살표 공통 박스 (정사각, 여백 포함) — 채점 기준과 같은 값
    final box = strokeGuideBox(size);
    final s = box.width;
    final boxLeft = box.left;
    final boxTop = box.top;
    Offset m(Offset e) => Offset(boxLeft + e.dx * s, boxTop + e.dy * s);

    // 1) 명조체 글자 — 박스 높이에 맞춰 스케일(한글 글리프 잉크가 박스를 채우도록)
    _paintGlyph(canvas, s, boxLeft, boxTop);

    if (strokes.isEmpty) return;

    // 2) 획 시작점의 순서 번호만 표시 (화살표 없음)
    for (var i = 0; i < strokes.length; i++) {
      _number(canvas, m(strokes[i].labelPos), i + 1, s);
    }
  }

  void _paintGlyph(Canvas canvas, double s, double boxLeft, double boxTop) {
    if (char.isEmpty) return;
    const base = 100.0;
    final tp = TextPainter(
      text: TextSpan(
        text: char,
        style: TextStyle(
          fontFamily: 'serif', // 명조체(브라우저/OS serif → 바탕/명조)
          fontWeight: FontWeight.w500,
          fontSize: base,
          color: glyphColor,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    if (tp.height <= 0) return;
    final scale = s / tp.height; // 줄 높이를 박스에 맞춤 → 글리프 잉크가 박스를 채움
    canvas.save();
    canvas.translate(boxLeft + (s - tp.width * scale) / 2, boxTop);
    canvas.scale(scale);
    tp.paint(canvas, Offset.zero);
    canvas.restore();
  }

  void _number(Canvas canvas, Offset c, int n, double s) {
    final r = math.max(9.0, s * 0.036);
    // 부드러운 그림자
    canvas.drawCircle(
      c.translate(0, 1.5),
      r,
      Paint()
        ..color = Colors.black.withValues(alpha: 0.12)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.5),
    );
    canvas.drawCircle(c, r, Paint()..color = markerColor);
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4,
    );
    final tp = TextPainter(
      text: TextSpan(
        text: '$n',
        style: TextStyle(
          color: Colors.white,
          fontSize: r * 1.05,
          fontWeight: FontWeight.w700,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, c - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant StrokeOrderGuidePainter oldDelegate) =>
      oldDelegate.char != char || oldDelegate.strokes != strokes;
}
