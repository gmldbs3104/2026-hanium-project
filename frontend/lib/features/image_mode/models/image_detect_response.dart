import 'detected_char.dart';

/// POST /api/v1/image/{image_session_id}/detect 응답 (schemas/image.py ImageDetectResponse)
class ImageDetectResponse {
  final String imageSessionId;
  final List<DetectedChar> detectedChars;
  final int totalDetected;

  const ImageDetectResponse({
    required this.imageSessionId,
    required this.detectedChars,
    required this.totalDetected,
  });

  factory ImageDetectResponse.fromJson(Map<String, dynamic> json) {
    return ImageDetectResponse(
      imageSessionId: json['image_session_id'] as String,
      detectedChars: (json['detected_chars'] as List)
          .map((e) => DetectedChar.fromJson(e as Map<String, dynamic>))
          .toList(),
      totalDetected: json['total_detected'] as int,
    );
  }
}
