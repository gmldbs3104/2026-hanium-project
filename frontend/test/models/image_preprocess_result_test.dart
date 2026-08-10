import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/image_mode/models/image_result.dart';

void main() {
  group('ImagePreprocessResult.fromJson', () {
    test('preprocessed_image_base64가 있으면 파싱한다', () {
      final result = ImagePreprocessResult.fromJson({
        'image_session_id': 'sess-1',
        'width': 1200,
        'height': 1600,
        'preprocessed_image_base64': 'aGVsbG8=',
      });

      expect(result.preprocessedImageBase64, 'aGVsbG8=');
    });

    test('preprocessed_image_base64가 없으면 null이다', () {
      final result = ImagePreprocessResult.fromJson({
        'image_session_id': 'sess-1',
        'width': 1200,
        'height': 1600,
      });

      expect(result.preprocessedImageBase64, isNull);
    });
  });
}
