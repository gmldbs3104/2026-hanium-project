import '../../../shared/models/bounding_box.dart';

/// 이미지 모드 **글자 단위** 박스와 그 색 판정 (2026-09-01 신설).
/// backend `schemas/image.py`의 `ImageCharBox`와 1:1.
///
/// 종전에는 백엔드가 `target_id="global"` 피드백만 내려줘서, 앱은 탐지된 영역을
/// **전부 회색**으로만 그렸다 — 어느 글자가 문제인지 화면에서 알 수 없었다.
///
/// 색은 두 가지뿐이다(사용자 결정).
///   · 🟢 초록 — 이 글자에 걸린 항목이 전부 통과
///   · 🔴 빨강 — 하나라도 미흡
///
/// 박스 색에 반영되는 항목은 **글자마다 판정되는 3가지**뿐이다.
///   · 크기   — 다른 글자들의 평균보다 크거나 작다
///   · 기울기 — 다른 글자들의 평균과 다른 쪽으로 기울었다
///   · 줄 정렬 — 자기 행의 기준선에서 위아래로 벗어났다
/// 자간·행간은 글자 하나에 귀속되지 않아 문구로만 나간다.
///
/// ⚠️ 서버가 이미 [ok]로 판정해서 내려준다. 앱이 점수로 다시 판정하지 말 것 —
/// 종합 점수로 색을 정하면 한 항목을 크게 틀려도 다른 항목이 끌어올려 초록이 된다.
class ImageCharBox {
  final String charId;
  final BoundingBox boundingBox;

  /// true면 초록, false면 빨강. 서버 판정을 그대로 쓴다.
  final bool ok;

  /// 빨강일 때 무엇이 걸렸는지. 예: "크기(너무 큼)", "줄 정렬(아래로 벗어남)".
  final List<String> failedItems;

  const ImageCharBox({
    required this.charId,
    required this.boundingBox,
    required this.ok,
    required this.failedItems,
  });

  factory ImageCharBox.fromJson(Map<String, dynamic> json) {
    final box = json['box'] as Map<String, dynamic>;
    return ImageCharBox(
      charId: json['char_id'] as String,
      boundingBox: BoundingBox(
        x: (box['x'] as num).toDouble(),
        y: (box['y'] as num).toDouble(),
        width: (box['width'] as num).toDouble(),
        height: (box['height'] as num).toDouble(),
      ),
      // 서버가 못 내려주면 색을 지어내지 않고 통과로 둔다 — 안 잰 것을 빨강으로
      // 칠하면 "재지도 않은 지표로 감점"이 된다.
      ok: json['ok'] as bool? ?? true,
      failedItems: (json['failed_items'] as List?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
    );
  }
}
