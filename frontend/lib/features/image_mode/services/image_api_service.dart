import 'dart:convert';
import 'package:uuid/uuid.dart';

import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../models/image_result.dart';

/// 이미지 모드 전용 API 서비스 (SFR-003I 대응)
///
/// REQ-003I-6: 캔버스 모드의 파이프라인(SFR-003C 이후)과 로직을 공유하지 않아야 한다
/// → canvas_mode/services/canvas_api_service.dart 와 완전히 별개 파일/클래스
///
/// ★ 백엔드 연동 방법 ★
/// [AppConfig.useMockApi] 를 false로 바꾸면 preprocess() 가
/// 자동으로 실제 ApiClient.post() 호출로 전환됩니다.
class ImageApiService {
  /// 촬영된 이미지를 Base64로 인코딩해 서버로 전송
  /// (requirement Action ①: POST /api/v1/image/preprocess)
  static Future<ImagePreprocessResult> preprocess({
    required List<int> imageBytes,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockPreprocess(imageBytes);
    }

    final base64Image = base64Encode(imageBytes);
    final response = await ApiClient.post(
      AppConfig.imagePreprocessEndpoint,
      {
        'image': base64Image,
        'input_type': 'camera',
      },
    );
    return ImagePreprocessResult.fromJson(response);
  }

  /// ===== Mock 구현 =====
  static Future<ImagePreprocessResult> _mockPreprocess(List<int> imageBytes) async {
    await Future.delayed(AppConfig.mockDelay);

    if (imageBytes.isEmpty) {
      throw ApiException('이미지 데이터가 비어 있습니다.');
    }

    return ImagePreprocessResult(
      imageSessionId: 'mock-image-session-${const Uuid().v4().substring(0, 8)}',
      qualityScore: 82, // mock 고정값. 40 미만으로 바꾸면 재촬영 분기 테스트 가능
      detectedSlantAngle: 2.5,
    );
  }
}
