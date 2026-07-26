import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/feedback/utils/canvas_coordinate_mapper.dart';
import 'package:frontend/shared/models/bounding_box.dart';

/// SFR-007 오버레이 좌표 매핑 검증.
/// 원본(캔버스/이미지) 좌표계 ↔ 화면 표시 좌표계를 BoxFit.contain 기준으로 변환한다.
void main() {
  group('CanvasCoordinateMapper (BoxFit.contain)', () {
    // 세로로 긴 100x200 원본을 100x100 정사각형 영역에 넣는 케이스
    CanvasCoordinateMapper build() => CanvasCoordinateMapper(
          sourceWidth: 100,
          sourceHeight: 200,
          displayWidth: 100,
          displayHeight: 100,
        );

    test('contain 스케일과 레터박스 오프셋을 계산한다', () {
      final mapper = build();
      // scale = min(100/100, 100/200) = 0.5
      expect(mapper.scale, 0.5);
      // scaledWidth = 50 → 좌우 여백 (100-50)/2 = 25, 세로는 꽉 참
      expect(mapper.offsetX, 25);
      expect(mapper.offsetY, 0);
    });

    test('toDisplay는 스케일 + 오프셋을 적용한다', () {
      final mapper = build();
      expect(mapper.toDisplay(const Offset(0, 0)), const Offset(25, 0));
      expect(mapper.toDisplay(const Offset(100, 200)), const Offset(75, 100));
    });

    test('toDisplayRect는 원본 박스를 표시 Rect로 변환한다', () {
      final mapper = build();
      final rect = mapper.toDisplayRect(
        const BoundingBox(x: 0, y: 0, width: 100, height: 200),
      );
      expect(rect, const Rect.fromLTWH(25, 0, 50, 100));
    });

    test('toSource(toDisplay(p)) == p (역변환 왕복)', () {
      final mapper = CanvasCoordinateMapper(
        sourceWidth: 1200,
        sourceHeight: 1600,
        displayWidth: 300,
        displayHeight: 500,
      );
      const p = Offset(432.1, 789.0);
      final back = mapper.toSource(mapper.toDisplay(p));
      expect(back.dx, closeTo(p.dx, 1e-9));
      expect(back.dy, closeTo(p.dy, 1e-9));
    });
  });
}
