import 'package:flutter/material.dart';
import '../../../shared/models/feedback_item.dart';
import '../models/canvas_correction_overlay_item.dart';
import '../utils/canvas_coordinate_mapper.dart';
import '../utils/severity_style.dart';

/// SFR-007: 캔버스 스냅샷(재렌더링된 스트로크) 위에 교정 오버레이를 렌더링하는 위젯.
///
/// [background]는 실제 PNG가 아니라, 같은 크기로 다시 그린 StrokePainter 등을
/// 넘기면 된다 (REQ-003C-6: 서버로 PNG를 보내지 않으므로 서버 스냅샷이 없음).
///
/// 사용 예:
/// ```dart
/// CanvasCorrectionOverlayView(
///   background: CustomPaint(painter: StrokePainter(strokes)), // 기존 획 재렌더링
///   sourceWidth: metadata.width,
///   sourceHeight: metadata.height,
///   items: CanvasCorrectionOverlayItem.merge(
///     charGroups: groupResponse.charGroups,
///     feedbackItems: feedbackResponse.feedbackItems,
///   ),
///   onItemTap: (item) => showFeedbackSheet(context, item),
/// )
/// ```
class CanvasCorrectionOverlayView extends StatelessWidget {
  final Widget background;
  final double sourceWidth;
  final double sourceHeight;
  final List<CanvasCorrectionOverlayItem> items;
  final ValueChanged<CanvasCorrectionOverlayItem>? onItemTap;
  final bool showOverlay;

  const CanvasCorrectionOverlayView({
    super.key,
    required this.background,
    required this.sourceWidth,
    required this.sourceHeight,
    required this.items,
    this.onItemTap,
    this.showOverlay = true,
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
                  onTapUp: (details) => _handleTap(details.localPosition, mapper),
                  child: CustomPaint(
                    painter: CanvasCorrectionOverlayPainter(items: items, mapper: mapper),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  void _handleTap(Offset localPosition, CanvasCoordinateMapper mapper) {
    if (onItemTap == null) return;

    // 겹치는 항목이 있으면 면적이 가장 작은 항목 우선 선택
    CanvasCorrectionOverlayItem? hit;
    double smallestArea = double.infinity;

    for (final item in items) {
      final rect = mapper.toDisplayRect(item.boundingBox);
      if (rect.contains(localPosition)) {
        final area = rect.width * rect.height;
        if (area < smallestArea) {
          smallestArea = area;
          hit = item;
        }
      }
    }

    if (hit != null) onItemTap!(hit);
  }
}

class CanvasCorrectionOverlayPainter extends CustomPainter {
  final List<CanvasCorrectionOverlayItem> items;
  final CanvasCoordinateMapper mapper;

  CanvasCorrectionOverlayPainter({required this.items, required this.mapper});

  @override
  void paint(Canvas canvas, Size size) {
    for (final item in items) {
      // good(문제 없음)은 시각적 잡음을 줄이기 위해 기본적으로 표시하지 않음
      if (item.severity == FeedbackSeverity.good) continue;

      final rect = mapper.toDisplayRect(item.boundingBox);
      final color = SeverityStyle.color(item.severity);

      final fillPaint = Paint()
        ..color = color.withValues(alpha: 0.12)
        ..style = PaintingStyle.fill;
      canvas.drawRect(rect, fillPaint);

      final strokePaint = Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = item.severity == FeedbackSeverity.error ? 2.5 : 2.0;
      canvas.drawRect(rect, strokePaint);

      // REQ-007-6: 색맹 보조 아이콘 배지 (색상 + 형태로 severity 이중 표현)
      SeverityStyle.paintBadge(canvas, rect.topLeft, item.severity);
    }
  }

  @override
  bool shouldRepaint(covariant CanvasCorrectionOverlayPainter oldDelegate) {
    return !identical(oldDelegate.items, items) || oldDelegate.mapper != mapper;
  }
}
