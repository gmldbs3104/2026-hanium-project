import '../../../shared/models/bounding_box.dart';
import '../../image_mode/models/detected_char.dart';
import '../../image_mode/models/image_char_box.dart';

/// 화면에서 실제로 그릴 이미지 bbox 오버레이 1개 항목.
///
/// 2026-09-01 개편 — 종전에는 백엔드가 `target_id="global"` 피드백만 내려줘서
/// **모든 박스가 중립 회색**이었다. 어느 글자가 문제인지 화면에서 알 수 없었고,
/// 캔버스 모드는 성분마다 색을 칠하는데 이미지 모드만 회색이라 짝이 안 맞았다.
/// 이제 서버가 글자마다 `ok`/`failed_items`를 내려주므로 초록·빨강 2색으로 그린다.
///
/// 박스 색에 반영되는 항목은 **글자마다 판정되는 3가지**(크기·기울기·줄 정렬)뿐이다.
/// 자간·행간은 글자 하나에 귀속되지 않아 문구로만 나간다(사용자 결정).
class ImageBBoxOverlayItem {
  final String charId;
  final BoundingBox boundingBox;

  /// true면 초록, false면 빨강. **서버 판정을 그대로 쓴다.**
  final bool ok;

  /// 빨강일 때 무엇이 걸렸는지. 예: "크기(너무 큼)".
  final List<String> failedItems;

  /// DetectedChar.confidence 그대로 전달 (상세 시트에서 참고용).
  final double? confidence;

  const ImageBBoxOverlayItem({
    required this.charId,
    required this.boundingBox,
    required this.ok,
    this.failedItems = const [],
    this.confidence,
  });

  /// 사람이 읽는 한 줄. 상세 시트·접근성 라벨에 쓴다.
  String get message => ok
      ? '$charId — 잘 썼어요'
      : '$charId — ${failedItems.join(', ')}';

  /// 탐지 결과와 서버의 색 판정을 붙인다.
  ///
  /// [charBoxes]가 비어 있으면(구버전 서버·목업) 판정이 없는 것이므로 **전부 통과**로
  /// 둔다 — 안 잰 것을 빨강으로 칠하면 "재지도 않은 지표로 감점"이 된다.
  static List<ImageBBoxOverlayItem> merge({
    required List<DetectedChar> detectedChars,
    required List<ImageCharBox> charBoxes,
  }) {
    final judged = {for (final b in charBoxes) b.charId: b};
    return detectedChars.map((c) {
      final j = judged[c.charId];
      return ImageBBoxOverlayItem(
        charId: c.charId,
        boundingBox: c.boundingBox,
        ok: j?.ok ?? true,
        failedItems: j?.failedItems ?? const [],
        confidence: c.confidence,
      );
    }).toList();
  }
}
