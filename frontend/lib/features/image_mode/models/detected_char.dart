import '../../../shared/models/bounding_box.dart';

/// backend ImageDetectResponse.detected_chars 항목 (schemas/image.py DetectedChar)
/// POST /api/v1/image/{id}/detect 응답에서 사용
class DetectedChar {
  final String charId;
  final BoundingBox boundingBox;

  /// 탐지 신뢰도 (0.0~1.0). 값이 없으면 null.
  final double? confidence;

  /// 기울기 (degree, 시계방향 양수). 값이 없으면 null.
  final double? angle;

  /// false면 [angle]을 측정할 수 없는 글자(예: 세로획이 없는 'ㅇ')라 값을 신뢰할 수 없다.
  final bool? angleReliable;

  const DetectedChar({
    required this.charId,
    required this.boundingBox,
    this.confidence,
    this.angle,
    this.angleReliable,
  });

  factory DetectedChar.fromJson(Map<String, dynamic> json) {
    return DetectedChar(
      charId: json['char_id'] as String,
      boundingBox: BoundingBox.fromJson(json['bounding_box'] as Map<String, dynamic>),
      confidence: (json['confidence'] as num?)?.toDouble(),
      angle: (json['angle'] as num?)?.toDouble(),
      angleReliable: json['angle_reliable'] as bool?,
    );
  }
}
