import '../../../shared/models/bounding_box.dart';

/// backend ImageDetectResponse.detected_chars 항목 (schemas/image.py DetectedChar)
/// POST /api/v1/image/{id}/detect 응답에서 사용
///
/// 참고: 현재 백엔드 탐지 로직(ai_adapters.craft_detect_chars)은 OpenCV contour 기반
/// placeholder이고, ai/ 폴더의 CraftDetector(진짜 CRAFT 모델)로 교체될 예정이다.
///
/// ⚠️ ai/AI_MODEL_INTERFACE.md 기준으로 craft_detect_chars()는 이미 문자별
/// `confidence`(0.0~1.0)와 `angle`(기울기, degree)을 계산해서 반환하고 있다.
/// 다만 지금 `routes/image.py`의 `/detect` 엔드포인트가 `bounding_box`만 꺼내서
/// DetectedChar를 만들고 confidence/angle은 버리고 있어서, 현재 API 응답에는
/// 이 두 필드가 없다. 백엔드가 스키마에 추가해서 넘겨주기 시작하면 이 모델이
/// 자동으로 파싱하도록 미리 nullable로 준비해뒀다 (없으면 그냥 null).
class DetectedChar {
  final String charId;
  final BoundingBox boundingBox;

  /// 탐지 신뢰도 (0.0~1.0). 백엔드가 아직 안 내려주면 null.
  final double? confidence;

  /// 기울기 (degree, 시계방향 양수). 백엔드가 아직 안 내려주면 null.
  final double? angle;

  const DetectedChar({
    required this.charId,
    required this.boundingBox,
    this.confidence,
    this.angle,
  });

  factory DetectedChar.fromJson(Map<String, dynamic> json) {
    return DetectedChar(
      charId: json['char_id'] as String,
      boundingBox: BoundingBox.fromJson(json['bounding_box'] as Map<String, dynamic>),
      confidence: (json['confidence'] as num?)?.toDouble(),
      angle: (json['angle'] as num?)?.toDouble(),
    );
  }
}
