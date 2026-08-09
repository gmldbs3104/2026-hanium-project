import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/canvas_mode/models/stroke.dart';

void main() {
  group('CanvasMetadata.toJson', () {
    test('width/height를 정수로 직렬화한다', () {
      const metadata = CanvasMetadata(width: 412, height: 611, strokeCount: 3);

      final json = metadata.toJson();

      expect(json['width'], isA<int>());
      expect(json['height'], isA<int>());
      expect(json['width'], 412);
      expect(json['height'], 611);
    });
  });
}
