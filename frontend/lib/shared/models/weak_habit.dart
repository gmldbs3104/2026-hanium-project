/// AI 분석: "취약한 습관" 한 항목.
///
/// 목업의 앰버 배지(예: "선 이탈 3회", "좌상향 기울기 심함 2회", "밸런스 불균형 6회")에 대응한다.
///
/// ⚠️ 백엔드 연동 예정 필드:
/// canvas/image feedback 응답의 최상위에 `weak_habits` 배열로 내려주기로 한다.
/// 각 항목 스키마 (backend schemas/canvas.py·image.py에 추가 예정):
/// ```json
/// { "label": "선 이탈", "count": 3, "severity": "warning" }
/// ```
/// - label:    화면에 표시할 습관 이름 (필수)
/// - count:    해당 습관이 감지된 횟수 (선택, 없으면 배지에 횟수 미표시)
/// - severity: "warning" | "error" (선택, 기본 "warning")
///
/// 백엔드가 아직 이 필드를 내려주지 않아도 앱이 깨지지 않도록,
/// 파싱은 전부 널 세이프(nullable/기본값)로 처리한다.
class WeakHabit {
  final String label;
  final int? count;
  final String severity; // "warning" | "error"

  const WeakHabit({
    required this.label,
    this.count,
    this.severity = 'warning',
  });

  bool get isError => severity == 'error';

  /// "3회"처럼 배지에 붙일 횟수 문자열 (count가 없으면 null).
  String? get countLabel => count == null ? null : '$count회';

  factory WeakHabit.fromJson(Map<String, dynamic> json) {
    return WeakHabit(
      label: (json['label'] ?? json['name'] ?? '').toString(),
      count: (json['count'] as num?)?.toInt(),
      severity: (json['severity'] as String?) ?? 'warning',
    );
  }

  /// 응답 최상위의 `weak_habits`(또는 하위호환용 `weakHabits`) 배열을 파싱한다.
  /// 필드가 없거나 형식이 다르면 빈 리스트를 반환한다 (백엔드 미구현 대비).
  static List<WeakHabit> listFromJson(Map<String, dynamic> json) {
    final raw = json['weak_habits'] ?? json['weakHabits'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((e) => WeakHabit.fromJson(Map<String, dynamic>.from(e)))
        .where((h) => h.label.isNotEmpty)
        .toList();
  }
}
