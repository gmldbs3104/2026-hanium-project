// POST /api/v1/image/{image_session_id}/analyze 응답 모델
// (schemas/image.py ImageAnalysisResponse)
//
// DATA_FLOW.md §5-8: AI는 5지표(높이균일·기울기·자간·행간·기준선)로 채점하지만
// 기존 계약엔 3개(크기/기울기/줄 정렬)만 있었다. 자간·행간 점수는
// spacing_uniformity_score/line_spacing_uniformity_score로 2026-08-09 응답에
// 추가됐지만, analyze()가 Future<void>만 반환해 프론트는 여태 파싱조차 안 했다
// (진짜 점수/메시지는 여전히 /feedback의 ImageFeedbackResponse에서만 온다).
// 측정 불가(글자/행 수 부족)면 null.

/// POST /api/v1/image/{image_session_id}/analyze 전체 응답
class ImageAnalysisResponse {
  final String imageSessionId;
  final int sizeUniformityScore;
  final double avgSlantAngle;
  final int slantConsistencyScore;
  final int lineAlignmentScore;
  final int overallScore;
  final String? overallTilt; // "straight" | "leaning_right" | "leaning_left"
  final String? totalGrade; // "우수" | "보통" | "불량"
  final List<String> clarityWarnings;

  final int? spacingUniformityScore;
  final int? lineSpacingUniformityScore;

  const ImageAnalysisResponse({
    required this.imageSessionId,
    required this.sizeUniformityScore,
    required this.avgSlantAngle,
    required this.slantConsistencyScore,
    required this.lineAlignmentScore,
    required this.overallScore,
    this.overallTilt,
    this.totalGrade,
    this.clarityWarnings = const [],
    this.spacingUniformityScore,
    this.lineSpacingUniformityScore,
  });

  factory ImageAnalysisResponse.fromJson(Map<String, dynamic> json) {
    return ImageAnalysisResponse(
      imageSessionId: json['image_session_id'] as String,
      sizeUniformityScore: (json['size_uniformity_score'] as num).toInt(),
      avgSlantAngle: (json['avg_slant_angle'] as num).toDouble(),
      slantConsistencyScore:
          (json['slant_consistency_score'] as num).toInt(),
      lineAlignmentScore: (json['line_alignment_score'] as num).toInt(),
      overallScore: (json['overall_score'] as num).toInt(),
      overallTilt: json['overall_tilt'] as String?,
      totalGrade: json['total_grade'] as String?,
      clarityWarnings: (json['clarity_warnings'] as List?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
      spacingUniformityScore:
          (json['spacing_uniformity_score'] as num?)?.toInt(),
      lineSpacingUniformityScore:
          (json['line_spacing_uniformity_score'] as num?)?.toInt(),
    );
  }
}
