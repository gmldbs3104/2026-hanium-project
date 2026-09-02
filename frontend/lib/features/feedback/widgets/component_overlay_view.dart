import 'package:flutter/material.dart';

import '../models/component_overlay_item.dart';
import '../utils/canvas_coordinate_mapper.dart';

/// 성분(초·중·종성) 단위 교정 오버레이 (2026-09-01 신설).
///
/// 박스 단위를 음절 → 성분으로 내렸다. 채점 단위가 성분인데 박스가 음절이면
/// 빨간 박스를 봐도 무엇이 문제인지 알 수 없기 때문이다. 이제 **빨간 박스 자체가 답**이다.
///
/// 색은 두 가지뿐이다(사용자 결정).
///   · 🟢 초록 — 이 성분의 항목이 전부 통과
///   · 🔴 빨강 — 하나라도 오류
///
/// [redOnly]는 **문장 연습에서 켠다.** 긴 문장은 성분 박스가 45개까지 나오는데
/// (실측: '천 리 길도 한 걸음부터 시작된다는 마음으로' = 18글자 45성분) 전부 칠하면
/// 글씨가 안 보인다. 잘 쓴 곳은 비워 두고 **고칠 곳만** 눈에 띄게 한다.
/// 한 글자 연습은 최대 3개라 초록까지 그려 "다 맞았다"를 보여준다.
class ComponentOverlayView extends StatelessWidget {
  final Widget background;
  final double sourceWidth;
  final double sourceHeight;
  final List<ComponentOverlayItem> items;
  final bool redOnly;
  final bool showOverlay;
  final ValueChanged<ComponentOverlayItem>? onItemTap;

  const ComponentOverlayView({
    super.key,
    required this.background,
    required this.sourceWidth,
    required this.sourceHeight,
    required this.items,
    this.redOnly = false,
    this.showOverlay = true,
    this.onItemTap,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final mapper = CanvasCoordinateMapper(
          sourceWidth: sourceWidth,
          sourceHeight: sourceHeight,
          displayWidth: constraints.maxWidth,
          displayHeight: constraints.maxHeight,
        );
        return Stack(
          fit: StackFit.expand,
          children: [
            background,
            if (showOverlay)
              Positioned.fill(
                child: GestureDetector(
                  behavior: HitTestBehavior.translucent,
                  onTapUp: (d) => _handleTap(d.localPosition, mapper),
                  child: RepaintBoundary(
                    child: CustomPaint(
                      painter: ComponentOverlayPainter(
                        items: items,
                        mapper: mapper,
                        redOnly: redOnly,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  void _handleTap(Offset pos, CanvasCoordinateMapper mapper) {
    if (onItemTap == null) return;
    for (final item in items) {
      if (redOnly && item.ok) continue; // 안 그린 박스는 누를 수도 없어야 한다
      if (mapper.toDisplayRect(item.boundingBox).contains(pos)) {
        onItemTap!(item);
        return;
      }
    }
  }
}

class ComponentOverlayPainter extends CustomPainter {
  final List<ComponentOverlayItem> items;
  final CanvasCoordinateMapper mapper;
  final bool redOnly;

  /// 2색만 쓴다. 종전 3단계(초록/주황/빨강)는 주황이 "고쳐야 하나 말아야 하나"로
  /// 읽혀 애매했다. 색맹 보조 배지도 2종이면 훨씬 또렷하다(REQ-007-6).
  static const _green = Color(0xFF34C759);
  static const _red = Color(0xFFFF3B30);

  ComponentOverlayPainter({
    required this.items,
    required this.mapper,
    required this.redOnly,
  });

  @override
  void paint(Canvas canvas, Size size) {
    for (final item in items) {
      if (redOnly && item.ok) continue;

      final rect = mapper.toDisplayRect(item.boundingBox);
      final color = item.ok ? _green : _red;

      // 잘못 쓴 성분을 더 두껍게 그려, 색을 못 봐도 굵기로 구분되게 한다.
      canvas.drawRect(
        rect,
        Paint()
          ..color = color.withValues(alpha: 0.10)
          ..style = PaintingStyle.fill,
      );
      canvas.drawRect(
        rect,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = item.ok ? 1.6 : 2.6,
      );

      _paintBadge(canvas, rect.topLeft, item.ok);
    }
  }

  /// REQ-007-6: 색상 + 형태로 이중 표현. ✓(통과) / ✕(오류).
  void _paintBadge(Canvas canvas, Offset center, bool ok) {
    const radius = 9.0;
    final color = ok ? _green : _red;
    canvas.drawCircle(center, radius, Paint()..color = color);
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );
    final icon = ok ? Icons.check_rounded : Icons.close_rounded;
    final tp = TextPainter(
      textDirection: TextDirection.ltr,
      text: TextSpan(
        text: String.fromCharCode(icon.codePoint),
        style: TextStyle(
          fontSize: 13,
          height: 1.0,
          fontFamily: icon.fontFamily,
          package: icon.fontPackage,
          color: Colors.white,
        ),
      ),
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant ComponentOverlayPainter old) =>
      !identical(old.items, items) ||
      old.mapper != mapper ||
      old.redOnly != redOnly;
}
