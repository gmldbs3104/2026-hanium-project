/// /api/v1/image/preprocess 응답 모델 (schemas/image.py ImagePreprocessResponse)
class ImagePreprocessResult {
  final String imageSessionId;
  final int? qualityScore;
  final bool? retakeRequired;
  final String? preprocessedImageBase64;

  /// true면 연한 글씨 보존 모드로 처리됐다는 뜻 — 종이 뒷면 글씨(비침)가
  /// 지워지지 않고 남아 글자로 잡혔을 수 있다. 사용자에게 안내만 한다
  /// (탐지 단계에서 걸러내는 로직은 없음 — DATA_FLOW.md §5-10 / §6.2).
  final bool? preservationMode;

  final int width;
  final int height;

  const ImagePreprocessResult({
    required this.imageSessionId,
    required this.width,
    required this.height,
    this.qualityScore,
    this.retakeRequired,
    this.preprocessedImageBase64,
    this.preservationMode,
  });

  factory ImagePreprocessResult.fromJson(Map<String, dynamic> json) {
    return ImagePreprocessResult(
      imageSessionId: json['image_session_id'] as String,
      qualityScore: json['quality_score'] as int?,
      retakeRequired: json['retake_required'] as bool?,
      preprocessedImageBase64: json['preprocessed_image_base64'] as String?,
      preservationMode: json['preservation_mode'] as bool?,
      width: json['width'] as int,
      height: json['height'] as int,
    );
  }
}
