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
      final color =
          severity != null ? SeverityStyle.color(severity) : _neutralColorFor(item.confidence);

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

  /// severity(문자 단위 피드백)가 아직 없을 때의 중립색. confidence가 있으면
  /// (ai/AI_MODEL_INTERFACE.md 기준 CRAFT가 이미 계산하는 값, 백엔드가 노출하면
  /// 여기서 바로 반영됨) 저신뢰도 탐지만 옅은 주황으로 구분한다.
  Color _neutralColorFor(double? confidence) {
    if (confidence != null && confidence < 0.7) {
      return const Color(0xFFFF9500);
    }
    return _neutralColor;
  }

  @override
  bool shouldRepaint(covariant ImageBBoxOverlayPainter oldDelegate) {
    return !identical(oldDelegate.items, items) || oldDelegate.mapper != mapper;
  }
}
