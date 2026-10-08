// POST /api/v1/canvas/{canvas_session_id}/analyze-detail 응답 모델
// (schemas/canvas.py CanvasAnalysisResponse / CanvasCharAnalysis)
//
// DATA_FLOW.md §7.3/§8-B·C·D: 이 응답의 speed_profile/
// correction_flags/stroke_order_result.notes는 기존엔 파싱조차 되지 않고
// 버려졌다(analyzeDetail()이 Future<void>만 반환). 진짜 점수는 여전히
// /feedback에서만 나오므로(CanvasFeedbackResponse), 이 모델은 그 값들과
// 별개로 문자 상세 정보(탭하면 보이는 바텀시트)에만 쓰인다.

/// 획순 위치 매칭 결과 — target_text가 있었던 문자만 값이 있다.
/// (ai/canvas/canvas_quality_analyzer.py analyze_stroke_order_by_position 반환 형식)
class StrokeOrderResult {
  final int errorCount;
  final bool likelyWrongCharacter;
  final List<String> corrections;

  /// 복수 정본 안내 (예: ㅌ처럼 인정된 대안 필순이 있는 자모) — DATA_FLOW.md §8-D
  final List<String> notes;

  const StrokeOrderResult({
    required this.errorCount,
    required this.likelyWrongCharacter,
    required this.corrections,
    required this.notes,
  });

  factory StrokeOrderResult.fromJson(Map<String, dynamic> json) {
    return StrokeOrderResult(
      errorCount: (json['error_count'] as num?)?.toInt() ?? 0,
      likelyWrongCharacter: json['likely_wrong_character'] as bool? ?? false,
      corrections: (json['corrections'] as List?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
      notes: (json['notes'] as List?)?.map((e) => e as String).toList() ??
          const [],
    );
  }
}

/// 필기 속도 프로필 — **채점에는 안 쓰고 기록만** 한다(2026-09-01 결정).
/// 필압은 같은 날 제거했다(미지원 기기에서 늘 1.0 상수라 신호가 아니었음).
class WritingMotionProfile {
  final double meanSpeedPxPerMs;

  const WritingMotionProfile({
    required this.meanSpeedPxPerMs,
  });

  factory WritingMotionProfile.fromJson({
    Map<String, dynamic>? speedProfile,
  }) {
    return WritingMotionProfile(
      meanSpeedPxPerMs:
          (speedProfile?['mean_speed_px_per_ms'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

/// 문자 하나에 대한 분석 결과 (schemas/canvas.py CanvasCharAnalysis)
class CanvasCharAnalysis {
  final String charId;

  /// ⚠️ 아래 값들은 **못 잰 경우 null**이다 — 0이 아니라 '미측정'이다.
  /// 연습 종류마다 채점 항목이 다르다(낱자는 성분비율·자간이 없고, 한 글자는
  /// 자간이 없다). null을 0이나 만점으로 채워 쓰지 말 것 — 화면이 "안 잰 지표로
  /// 칭찬/감점"하게 된다(DATA_FLOW.md §4-1).
  final StrokeOrderResult? strokeOrderResult;
  final Map<String, dynamic>? directionResult;   // 획을 바른 방향으로 그었는가(역방향)
  final Map<String, dynamic>? tiltResult;        // 곧게 그을 획의 기울기
  final Map<String, dynamic>? balanceResult;     // 초·중·종성 크기 균형
  /// 화면에 그릴 **성분 단위 박스**. 낱자는 성분이 하나라 null이다(박스를 안 그린다).
  final List<dynamic>? componentBoxes;
  final double? spacingDeviation;
  final double? sizeDeviation;
  final double? sizeFillRatio;                   // 표준 자형 대비 크기 배율(1.0=표준)
  /// 채점 축 — {"획순": {"score": 100|70|40|null, "reasons": [...]}, "모양": ..., "짜임새": ..., "배치": ...}.
  /// 단계마다 측정되는 축이 다르다(자모음: 획순·모양 / 한 글자: +짜임새 / 문장: +배치).
  /// null은 미측정이다 — 0이나 100으로 채우지 말 것(2026-10-08 축 재설계).
  final Map<String, dynamic> axes;
  final WritingMotionProfile motion;
  final int? overallScore;

  /// 교정 플래그 (예: size_large, spacing_too_narrow, stroke_order_error)
  /// DATA_FLOW.md §8-C
  final List<String> correctionFlags;

  /// 이 글자에서 틀린 **항목** 목록 (2026-09-17 신설).
  /// 예: ["획순(2획 순서 틀림)", "기울기(1획 기울어짐)"]
  ///
  /// 성분 박스가 없는 연습(자음·모음)에서도 화면이 "무엇이 틀렸는지" 보여줄 수 있게
  /// 글자 단위로도 내려온다. 종전에는 박스에만 있어서 낱자 연습은 오류가 있어도
  /// 취약 습관 카드가 "훌륭해요"만 띄웠다(사용자 지적).
  final List<String> failedItems;

  /// false면 **채점하지 않은 글자**다 — 목표 글자와 달라 다시 쓰라고 안내한다.
  /// 이때 [overallScore]는 null이고, 0점이 아니다.
  final bool scorable;

  /// too_few_strokes | too_many_strokes | shape_mismatch | missing
  final String? unscorableReason;

  /// 채점 거부 안내문 등.
  final List<String> corrections;

  const CanvasCharAnalysis({
    required this.charId,
    required this.strokeOrderResult,
    required this.directionResult,
    required this.tiltResult,
    required this.balanceResult,
    required this.componentBoxes,
    required this.spacingDeviation,
    required this.sizeDeviation,
    required this.sizeFillRatio,
    required this.axes,
    required this.motion,
    required this.overallScore,
    required this.correctionFlags,
    this.failedItems = const [],
    this.scorable = true,
    this.unscorableReason,
    this.corrections = const [],
  });

  factory CanvasCharAnalysis.fromJson(Map<String, dynamic> json) {
    final rawOrder = json['stroke_order_result'] as Map<String, dynamic>?;
    return CanvasCharAnalysis(
      charId: json['char_id'] as String,
      failedItems:
          (json['failed_items'] as List?)?.map((e) => e as String).toList() ?? const [],
      scorable: json['scorable'] as bool? ?? true,
      unscorableReason: json['unscorable_reason'] as String?,
      corrections:
          (json['corrections'] as List?)?.map((e) => e as String).toList() ?? const [],
      strokeOrderResult:
          rawOrder != null ? StrokeOrderResult.fromJson(rawOrder) : null,
      directionResult: json['direction_result'] as Map<String, dynamic>?,
      tiltResult: json['tilt_result'] as Map<String, dynamic>?,
      balanceResult: json['balance_result'] as Map<String, dynamic>?,
      componentBoxes: json['component_boxes'] as List<dynamic>?,
      spacingDeviation: (json['spacing_deviation'] as num?)?.toDouble(),
      sizeDeviation: (json['size_deviation'] as num?)?.toDouble(),
      sizeFillRatio: (json['size_fill_ratio'] as num?)?.toDouble(),
      axes: (json['axes'] as Map<String, dynamic>?) ?? const {},
      motion: WritingMotionProfile.fromJson(
        speedProfile: json['speed_profile'] as Map<String, dynamic>?,
      ),
      overallScore: (json['overall_score'] as num?)?.toInt(),
      correctionFlags: (json['correction_flags'] as List?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
    );
  }

  /// 축 점수. 축이 없거나 미측정이면 null.
  int? axisScore(String axis) =>
      ((axes[axis] as Map<String, dynamic>?)?['score'] as num?)?.toInt();

  /// 화면에 칩으로 보여줄 교정 플래그.
  ///
  /// 서버는 같은 목록에 **기록용 진단값**도 남긴다(DB에 따로 둘 컬럼이 없어서) —
  /// 'unscorable:shape_mismatch', 'match_dist:0.41/0.52', 'ink_gap:0.233'처럼 콜론이
  /// 든 것들이다. 사용자에게 보여줄 말이 아니므로 뺀다.
  List<String> get displayFlags =>
      correctionFlags.where((f) => !f.contains(':')).toList();

  /// 성분 박스 어디에도 실리지 않은 글자 단위 사유.
  ///
  /// 박스가 없는 낱자는 사유 전부가 여기에 해당한다. 박스가 있는 글자도 자간처럼
  /// 성분에 귀속되지 않는 항목이나, 어느 성분 것인지 알 수 없는 여분 획은 박스에
  /// 안 실린다 — 박스만 모아 보여주면 점수는 깎였는데 사유가 화면에 없다.
  List<String> get failuresNotOnBoxes {
    if (!scorable) return const [];
    final boxes = componentBoxes;
    if (boxes == null || boxes.isEmpty) return failedItems;
    final onBoxes = <String>{};
    for (final box in boxes) {
      final reasons = (box as Map)['failed_items'] as List?;
      for (final reason in reasons ?? const []) {
        onBoxes.add(_itemName(reason as String));
      }
    }
    return failedItems.where((f) => !onBoxes.contains(_itemName(f))).toList();
  }

  /// '획순(2획 순서 틀림)' → '획순'
  static String _itemName(String reason) => reason.split('(').first;

  /// 교정 플래그 코드 → 사용자에게 보여줄 한글 라벨.
  static String flagLabel(String flag) {
    switch (flag) {
      case 'size_large':
        return '글자가 큼';
      case 'size_small':
        return '글자가 작음';
      case 'spacing_too_narrow':
        return '자간이 좁음';
      case 'spacing_too_wide':
        return '자간이 넓음';
      case 'stroke_order_error':
        return '획순 오류';
      case 'stroke_direction_error':
        return '획 방향 오류';
      case 'stroke_tilt_error':
        return '획이 기울어짐';
      case 'char_rotation_error':
        return '글자가 기울어짐';
      case 'corner_rounded':
        return '모서리를 둥글게 돌림';
      case 'component_balance_error':
        return '성분 비율 오류';
      case 'position_off':
        return '자리에서 벗어남';
      case 'shape_off':
        return '모양이 표준과 다름';
      case 'unscorable':
        return '채점 불가';
      default:
        return flag;
    }
  }
}

/// POST /api/v1/canvas/{canvas_session_id}/analyze-detail 전체 응답
/// (schemas/canvas.py CanvasAnalysisResponse)
class CanvasAnalysisResponse {
  final String canvasSessionId;
  final List<CanvasCharAnalysis> results;

  const CanvasAnalysisResponse({
    required this.canvasSessionId,
    required this.results,
  });

  factory CanvasAnalysisResponse.fromJson(Map<String, dynamic> json) {
    return CanvasAnalysisResponse(
      canvasSessionId: json['canvas_session_id'] as String,
      results: (json['results'] as List)
          .map((e) => CanvasCharAnalysis.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  /// char_id로 바로 찾기 위한 맵 (피드백 화면에서 탭한 문자의 상세 지표 조회용)
  Map<String, CanvasCharAnalysis> byCharId() => {
        for (final r in results) r.charId: r,
      };
}
