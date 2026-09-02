import 'package:flutter/material.dart';
import '../../../shared/models/feedback_item.dart';
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

  /// 2색만 쓴다(사용자 결정 2026-09-01) — 캔버스 모드 성분 박스와 같은 팔레트다.
  ///   · 🟢 초록 — 이 글자에 걸린 항목이 전부 통과
  ///   · 🔴 빨강 — 크기·기울기·줄 정렬 중 **하나라도** 미흡
  static const _green = Color(0xFF34C759);
  static const _red = Color(0xFFFF3B30);

  ImageBBoxOverlayPainter({required this.items, required this.mapper});

  @override
  void paint(Canvas canvas, Size size) {
    for (final item in items) {
      final rect = mapper.toDisplayRect(item.boundingBox);
      // 색은 **서버 판정(ok)** 하나로 정한다. 종전에는 target_id="global" 피드백만
      // 와서 매칭이 안 돼 모든 박스가 중립 회색이었다 — 어느 글자가 문제인지 알 수
      // 없었다. 그 전에는 탐지 신뢰도로 갈랐는데 그 값이 항상 0.5 상수라 **모든
      // 박스가 주황**이었다(DEVLOG 17막 실측).
      //
      // ⚠️ 여기서 "애매한 탐지를 걸러내는 일"을 하려 하지 말 것 — 그건 CRAFT
      // 디코딩 단계에서 이미 한다(text_threshold 0.7 / low_text 0.4, 평가셋으로
      // 측정해 정한 값). 응답의 confidence는 게이트가 아니라 보고용 숫자다.
      final color = item.ok ? _green : _red;

      // 잘못 쓴 글자를 더 두껍게 그려, 색을 못 봐도 굵기로 구분되게 한다.
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
          ..strokeWidth = item.ok ? 1.5 : 2.6,
      );

      // REQ-007-6: 색상 + 형태로 이중 표현 — 빨간 박스에만 배지를 얹는다.
      // 초록까지 배지를 달면 사진 위가 아이콘으로 뒤덮여 글씨가 안 보인다.
      if (!item.ok) {
        SeverityStyle.paintBadge(canvas, rect.topLeft, FeedbackSeverity.error);
      }
    }
  }

  @override
  bool shouldRepaint(covariant ImageBBoxOverlayPainter oldDelegate) {
    return !identical(oldDelegate.items, items) || oldDelegate.mapper != mapper;
  }
}
