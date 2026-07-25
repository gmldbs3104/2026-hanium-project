import '../../../shared/models/bounding_box.dart';

/// backend CanvasGroupResponse.char_groups 항목 (schemas/canvas.py CharGroup)
/// POST /api/v1/canvas/{id}/group 응답에서 사용
class CharGroup {
  final String charId;
  final BoundingBox boundingBox;
  final int strokeCount;
  final double confidence;
  final bool lowConfidence;

  const CharGroup({
    required this.charId,
    required this.boundingBox,
    required this.strokeCount,
    required this.confidence,
    required this.lowConfidence,
  });

  factory CharGroup.fromJson(Map<String, dynamic> json) {
    return CharGroup(
      charId: json['char_id'] as String,
      boundingBox: BoundingBox.fromJson(json['bounding_box'] as Map<String, dynamic>),
      strokeCount: json['stroke_count'] as int,
      confidence: (json['confidence'] as num).toDouble(),
      lowConfidence: json['low_confidence'] as bool,
    );
  }
}
