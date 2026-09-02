import 'image_char_box.dart';

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
  // ⚠️ 점수는 **측정 불가면 null**이다(만점 아님). 예: 한 줄만 썼으면 행간을,
  // 글자가 3자 미만이면 기울기를 못 잰다. 종전에는 이 셋이 non-null로 선언돼 있어
  // 서버가 null을 주면 파싱에서 죽었다 — 화면이 통째로 안 뜨는 사고가 된다.
  final int? sizeUniformityScore;
  final double avgSlantAngle;

  /// 글자 기울기의 중앙값(도, 양수=오른쪽). '기울기 균일성'과 별개 축 —
  /// 전부 똑같이 많이 기울여 쓰면 균일성은 만점이지만 이 값이 크다.
  /// 점수엔 반영되지 않고 서버가 문구로만 쓴다. 측정 불가면 null.
  final double? meanCharSlant;
  final int? slantConsistencyScore;
  final int? lineAlignmentScore;
  final int overallScore;
  /// 글줄 방향 — "straight" | "falling"(오른쪽으로 내려감) | "rising"(오른쪽으로 올라감).
  /// ⚠️ 이 주석이 오래 leaning_right/leaning_left로 적혀 있었고, 화면도 그 이름으로
  /// 매칭해 **어떤 사진을 넣어도 "반듯하게 썼어요"** 가 떴다(2026-09-02 수정).
  final String? overallTilt;
  final String? totalGrade; // "우수" | "보통" | "불량"
  final List<String> clarityWarnings;

  final int? spacingUniformityScore;
  final int? lineSpacingUniformityScore;

  /// 초록/빨강 박스 판정 — 앱은 이 목록만 그리면 된다(2026-09-01).
  final List<ImageCharBox> charBoxes;

  const ImageAnalysisResponse({
    required this.imageSessionId,
    this.sizeUniformityScore,
    required this.avgSlantAngle,
    this.meanCharSlant,
    this.slantConsistencyScore,
    this.lineAlignmentScore,
    required this.overallScore,
    this.overallTilt,
    this.totalGrade,
    this.clarityWarnings = const [],
    this.spacingUniformityScore,
    this.lineSpacingUniformityScore,
    this.charBoxes = const [],
  });

  factory ImageAnalysisResponse.fromJson(Map<String, dynamic> json) {
    return ImageAnalysisResponse(
      imageSessionId: json['image_session_id'] as String,
      sizeUniformityScore: (json['size_uniformity_score'] as num?)?.toInt(),
      avgSlantAngle: (json['avg_slant_angle'] as num).toDouble(),
      meanCharSlant: (json['mean_char_slant'] as num?)?.toDouble(),
      slantConsistencyScore:
          (json['slant_consistency_score'] as num?)?.toInt(),
      lineAlignmentScore: (json['line_alignment_score'] as num?)?.toInt(),
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
      charBoxes: (json['char_boxes'] as List?)
              ?.map((e) => ImageCharBox.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}
