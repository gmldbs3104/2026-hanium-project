import 'dart:ui';
import '../../../shared/models/bounding_box.dart';

/// 원본(캔버스 메타데이터 width/height, 또는 이미지 width/height) 좌표계를
/// 실제 화면에 표시되는 위젯 좌표계로 변환하는 공용 유틸리티.
///
/// BoxFit.contain 방식으로 배경(스트로크 재렌더링 또는 촬영 이미지)이 표시된다고
/// 가정하며, 캔버스 교정 오버레이 / 이미지 bbox 오버레이에서 공통으로 사용한다.
class CanvasCoordinateMapper {
  final double sourceWidth;
  final double sourceHeight;
  final double displayWidth;
  final double displayHeight;

  late final double scale;
  late final double offsetX;
  late final double offsetY;

  CanvasCoordinateMapper({
    required this.sourceWidth,
    required this.sourceHeight,
    required this.displayWidth,
    required this.displayHeight,
  }) {
    final scaleX = displayWidth / sourceWidth;
    final scaleY = displayHeight / sourceHeight;
    scale = scaleX < scaleY ? scaleX : scaleY;

    final scaledWidth = sourceWidth * scale;
    final scaledHeight = sourceHeight * scale;

    offsetX = (displayWidth - scaledWidth) / 2;
    offsetY = (displayHeight - scaledHeight) / 2;
  }

  Offset toDisplay(Offset source) {
    return Offset(source.dx * scale + offsetX, source.dy * scale + offsetY);
  }

  /// 원본 좌표계의 axis-aligned BoundingBox -> 화면 표시 Rect
  Rect toDisplayRect(BoundingBox box) {
    final topLeft = toDisplay(Offset(box.x, box.y));
    return Rect.fromLTWH(topLeft.dx, topLeft.dy, box.width * scale, box.height * scale);
  }

  /// 화면 표시 좌표(탭 이벤트 등) -> 원본 좌표
  Offset toSource(Offset display) {
    return Offset((display.dx - offsetX) / scale, (display.dy - offsetY) / scale);
  }
}
