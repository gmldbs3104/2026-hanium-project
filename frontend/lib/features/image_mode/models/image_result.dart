/// /api/v1/image/preprocess 응답 모델 (schemas/image.py ImagePreprocessResponse)
class ImagePreprocessResult {
  final String imageSessionId;
  final int? qualityScore;
  final bool? retakeRequired;
  final String? preprocessedImageBase64;
  final int width;
  final int height;

  const ImagePreprocessResult({
    required this.imageSessionId,
    required this.width,
    required this.height,
    this.qualityScore,
    this.retakeRequired,
    this.preprocessedImageBase64,
  });

  factory ImagePreprocessResult.fromJson(Map<String, dynamic> json) {
    return ImagePreprocessResult(
      imageSessionId: json['image_session_id'] as String,
      qualityScore: json['quality_score'] as int?,
      retakeRequired: json['retake_required'] as bool?,
      preprocessedImageBase64: json['preprocessed_image_base64'] as String?,
      width: json['width'] as int,
      height: json['height'] as int,
    );
  }
}
