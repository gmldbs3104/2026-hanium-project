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
  final Map<String, dynamic>? tiltResult;        // 곧게 그을 획의 기울기(15도 기준)
  final Map<String, dynamic>? balanceResult;     // 초·중·종성 크기 균형
  /// 화면에 그릴 **성분 단위 박스**. 낱자는 성분이 하나라 null이다(박스를 안 그린다).
  final List<dynamic>? componentBoxes;
  final double? spacingDeviation;
  final double? sizeDeviation;
  final double? sizeFillRatio;                   // 표준 자형 대비 크기 배율(1.0=표준)
  final Map<String, dynamic> itemScores;         // {항목명: 0~100 또는 null}
  final WritingMotionProfile motion;
  final int? overallScore;

  /// 교정 플래그 (예: size_large, spacing_too_narrow, stroke_order_error)
  /// DATA_FLOW.md §8-C
  final List<String> correctionFlags;

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
    required this.itemScores,
    required this.motion,
    required this.overallScore,
    required this.correctionFlags,
  });

  factory CanvasCharAnalysis.fromJson(Map<String, dynamic> json) {
    final rawOrder = json['stroke_order_result'] as Map<String, dynamic>?;
    return CanvasCharAnalysis(
      charId: json['char_id'] as String,
      strokeOrderResult:
          rawOrder != null ? StrokeOrderResult.fromJson(rawOrder) : null,
      directionResult: json['direction_result'] as Map<String, dynamic>?,
      tiltResult: json['tilt_result'] as Map<String, dynamic>?,
      balanceResult: json['balance_result'] as Map<String, dynamic>?,
      componentBoxes: json['component_boxes'] as List<dynamic>?,
      spacingDeviation: (json['spacing_deviation'] as num?)?.toDouble(),
      sizeDeviation: (json['size_deviation'] as num?)?.toDouble(),
      sizeFillRatio: (json['size_fill_ratio'] as num?)?.toDouble(),
      itemScores: (json['item_scores'] as Map<String, dynamic>?) ?? const {},
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
