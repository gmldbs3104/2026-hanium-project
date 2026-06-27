/// /api/v1/image/preprocess 응답 모델 (SFR-003I Outputs 기준)
class ImagePreprocessResult {
  final String imageSessionId;
  final int qualityScore;
  final double? detectedSlantAngle;

  const ImagePreprocessResult({
    required this.imageSessionId,
    required this.qualityScore,
    this.detectedSlantAngle,
  });

  factory ImagePreprocessResult.fromJson(Map<String, dynamic> json) {
    return ImagePreprocessResult(
      imageSessionId: json['image_session_id'] as String,
      qualityScore: json['quality_score'] as int,
      detectedSlantAngle: (json['detected_slant_angle'] as num?)?.toDouble(),
    );
  }
}
