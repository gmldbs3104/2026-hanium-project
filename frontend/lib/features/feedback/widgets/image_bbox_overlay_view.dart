import 'package:flutter/material.dart';
import '../models/image_bbox_overlay_item.dart';
import '../utils/canvas_coordinate_mapper.dart';
import '../utils/severity_style.dart';

/// SFR-007: 촬영 이미지 위에 문자 검출 Bounding Box 오버레이를 렌더링하는 위젯.
///
/// (백엔드 현재 구현은 OpenCV contour 기반 placeholder이며 추후 CRAFT로 교체 예정 —
///  detect 엔드포인트의 배열 형식만 바라보므로 이 위젯은 영향받지 않음)
///
/// 사용 예:
/// ```dart
/// ImageBBoxOverlayView(
///   image: Image.memory(capturedBytes),
///   sourceWidth: preprocessResult.width.toDouble(),
///   sourceHeight: preprocessResult.height.toDouble(),
///   items: ImageBBoxOverlayItem.merge(
///     detectedChars: detectResponse.detectedChars,
///     feedbackItems: feedbackResponse.feedbackItems,
///   ),
/// )
/// ```
class ImageBBoxOverlayView extends StatelessWidget {
  final Widget image;
  final double sourceWidth;
  final double sourceHeight;
  final List<ImageBBoxOverlayItem> items;
  final ValueChanged<ImageBBoxOverlayItem>? onItemTap;
  final bool showOverlay;

  const ImageBBoxOverlayView({
    super.key,
    required this.image,
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
            image,
            if (showOverlay)
              Positioned.fill(
                child: GestureDetector(
                  behavior: HitTestBehavior.translucent,
                  onTapUp: (details) => _handleTap(details.localPosition, mapper),
                  child: RepaintBoundary(
                    child: CustomPaint(
                      painter: ImageBBoxOverlayPainter(items: items, mapper: mapper),
                    ),
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
    for (final item in items) {
      if (mapper.toDisplayRect(item.boundingBox).contains(localPosition)) {
        onItemTap!(item);
        return;
      }
    }
  }
}

class ImageBBoxOverlayPainter extends CustomPainter {
  final List<ImageBBoxOverlayItem> items;
  final CanvasCoordinateMapper mapper;

  static const _neutralColor = Color(0xFF8E8E93); // 피드백 없음(target_id 매칭 안 됨) 시 중립 회색

  ImageBBoxOverlayPainter({required this.items, required this.mapper});

  @override
  void paint(Canvas canvas, Size size) {
    for (final item in items) {
      final rect = mapper.toDisplayRect(item.boundingBox);
      final severity = item.severity;
      // 피드백이 있는 글자만 심각도 색, 나머지는 중립색으로 통일한다.
      // 종전에는 탐지 신뢰도로 "애매한 박스"를 옅은 주황으로 갈랐는데,
      // 그 값이 항상 0.5 상수라 조건에 늘 걸려 **모든 박스가 주황**이었다
      // (DEVLOG 17막 실측). 게다가 requirement.md SFR-004I는 애매한 탐지를
      // 색으로 구분하라고 하지 않고 **걸러내라**고 한다 — 색 구분은 요구사항에
      // 없던 동작이라 제거한다(팀 결정 2026-08-16).
      final color =
          severity != null ? SeverityStyle.color(severity) : _neutralColor;

      final strokePaint = Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5;
      canvas.drawRect(rect, strokePaint);

      // REQ-007-6: severity가 있는 박스에만 색맹 보조 아이콘 배지 (색상 + 형태)
      if (severity != null) {
        SeverityStyle.paintBadge(canvas, rect.topLeft, severity);
      }
    }
  }

  @override
  bool shouldRepaint(covariant ImageBBoxOverlayPainter oldDelegate) {
    return !identical(oldDelegate.items, items) || oldDelegate.mapper != mapper;
  }
}
