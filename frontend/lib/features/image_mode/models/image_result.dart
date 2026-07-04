/// /api/v1/image/preprocess 응답 모델
///
/// ⚠️ 참고: 실제 백엔드 스키마(backend/app/schemas/image.py ImagePreprocessResponse)는
/// `image_session_id`, `width`, `height` 세 필드만 있고 `quality_score`,
/// `detected_slant_angle`는 없습니다.
///
/// `quality_score`는 ai/preprocessing/quality_scorer.py의 QualityScorer가 이미
/// 정확히 이 용도(REQ-003I-4, 40점 미만 재촬영)로 계산하고 있지만, 백엔드
/// `/preprocess` 라우트가 아직 이걸 호출도 안 하고 응답에도 안 넣고 있습니다
/// (백엔드팀 확인 필요한 연동 누락).
///
/// 그래서 `qualityScore`를 nullable로 뒀습니다 — 백엔드가 이 필드를 연결하기
/// 전까지는 null로 오고, 그 경우 재촬영 체크를 건너뜁니다 (기본값 0으로
/// 처리하면 실제 연동 시 모든 촬영이 "품질 0점"으로 재촬영 요구되는
/// 버그가 생기기 때문입니다).
class ImagePreprocessResult {
  final String imageSessionId;
  final int? qualityScore;
  final double? detectedSlantAngle;
  final int width;
  final int height;

  const ImagePreprocessResult({
    required this.imageSessionId,
    required this.width,
    required this.height,
    this.qualityScore,
    this.detectedSlantAngle,
  });

  factory ImagePreprocessResult.fromJson(Map<String, dynamic> json) {
    return ImagePreprocessResult(
      imageSessionId: json['image_session_id'] as String,
      // ⚠️ 실제 백엔드 응답에는 아직 없는 필드 — 있으면 쓰고, 없으면 null
      qualityScore: json['quality_score'] as int?,
      detectedSlantAngle: (json['detected_slant_angle'] as num?)?.toDouble(),
      width: json['width'] as int,
      height: json['height'] as int,
    );
  }
}
