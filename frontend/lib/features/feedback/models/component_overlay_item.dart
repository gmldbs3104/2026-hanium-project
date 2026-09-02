import '../../../shared/models/bounding_box.dart';
import '../../canvas_mode/models/canvas_char_analysis.dart';

/// 화면에 그릴 **성분(초·중·종성) 단위** 오버레이 1개 항목 (2026-09-01 신설).
///
/// 종전에는 박스가 **음절 단위**여서, 빨간 박스를 봐도 무엇이 문제인지 알 수 없었다.
/// 채점 단위가 성분(초·중·종성)인데 박스만 음절이었기 때문이다. 박스를 성분으로
/// 내리면 **빨간 박스 자체가 답**이 된다 — "받침이 크다"를 글로 읽는 대신 눈으로 본다.
///
/// 색은 두 가지뿐이다(사용자 결정 2026-09-01).
///   · 초록 — 이 성분에 걸린 항목이 **전부** 통과
///   · 빨강 — **하나라도** 오류
///
/// ⚠️ 서버가 이미 `ok`로 판정해서 내려준다. 앱이 점수로 다시 판정하지 말 것 —
/// 종합 점수(가중 평균)로 색을 정하면 획순을 통째로 틀려도 다른 항목이 끌어올려
/// 초록이 나온다(2026-09-01 실측: 낱자 획순 0점인데 종합 62점).
class ComponentOverlayItem {
  /// 글자 안에서의 자리 (0=초성, 1=중성, 2=종성)
  final int block;

  /// 자모 그 자체 ('ㄱ', 'ㅏ' …)
  final String jamo;

  /// 사람이 읽는 자리 이름 ('초성' / '중성' / '종성')
  final String role;

  final BoundingBox boundingBox;

  /// true면 초록, false면 빨강. 서버 판정을 그대로 쓴다.
  final bool ok;

  /// 빨강일 때 어느 항목이 걸렸는지 ('획순' / '획방향' / '기울기' / '성분비율' / '크기').
  /// 상세 시트에서 이유를 보여주는 데 쓴다.
  final List<String> failedItems;

  /// 이 성분이 속한 글자 id — 상세 시트가 글자 단위 분석을 찾을 때 쓴다.
  final String charId;

  const ComponentOverlayItem({
    required this.block,
    required this.jamo,
    required this.role,
    required this.boundingBox,
    required this.ok,
    required this.failedItems,
    required this.charId,
  });

  factory ComponentOverlayItem.fromJson(Map<String, dynamic> json, String charId) {
    final box = json['box'] as Map<String, dynamic>;
    return ComponentOverlayItem(
      block: (json['block'] as num?)?.toInt() ?? 0,
      jamo: json['jamo'] as String? ?? '',
      role: json['role'] as String? ?? '',
      boundingBox: BoundingBox(
        x: (box['x'] as num).toDouble(),
        y: (box['y'] as num).toDouble(),
        width: (box['width'] as num).toDouble(),
        height: (box['height'] as num).toDouble(),
      ),
      // 서버가 못 내려주면 색을 지어내지 않고 통과로 둔다 — 안 잰 것을 빨강으로
      // 칠하면 "재지도 않은 지표로 감점"이 된다.
      ok: json['ok'] as bool? ?? true,
      failedItems: (json['failed_items'] as List?)?.map((e) => e as String).toList() ??
          const [],
      charId: charId,
    );
  }

  /// 글자별 분석 목록에서 성분 박스를 모두 펼쳐 온다.
  ///
  /// 낱자(ㄱ·ㅏ) 연습은 `componentBoxes`가 null이라 **아무 박스도 안 나온다** —
  /// 성분이 하나뿐이라 박스를 쳐도 캔버스 테두리를 다시 그리는 것과 같아서다.
  /// 판정은 문구로만 전달된다.
  static List<ComponentOverlayItem> fromAnalyses(List<CanvasCharAnalysis> analyses) {
    final out = <ComponentOverlayItem>[];
    for (final a in analyses) {
      for (final raw in a.componentBoxes ?? const []) {
        out.add(ComponentOverlayItem.fromJson(
            raw as Map<String, dynamic>, a.charId));
      }
    }
    return out;
  }
}
