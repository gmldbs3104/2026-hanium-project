// POST /api/v1/canvas/{canvas_session_id}/analyze-detail 응답 모델
// (schemas/canvas.py CanvasAnalysisResponse / CanvasCharAnalysis)
//
// DATA_FLOW.md §7.3/§8-B·C·D: 이 응답의 pressure_profile/speed_profile/
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

/// 필압·속도 프로필 — 필압 센서 없는 기기에서는 pressure가 항상 1.0 고정.
/// (DATA_FLOW.md §8-B: 필기 습관 지표, 이번에 응답 레벨로 연결됨)
class WritingMotionProfile {
  final double meanPressure;
  final double meanSpeedPxPerMs;

  const WritingMotionProfile({
    required this.meanPressure,
    required this.meanSpeedPxPerMs,
  });

  factory WritingMotionProfile.fromJson({
    Map<String, dynamic>? pressureProfile,
    Map<String, dynamic>? speedProfile,
  }) {
    return WritingMotionProfile(
      meanPressure:
          (pressureProfile?['mean_pressure'] as num?)?.toDouble() ?? 0.0,
      meanSpeedPxPerMs:
          (speedProfile?['mean_speed_px_per_ms'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

/// 문자 하나에 대한 분석 결과 (schemas/canvas.py CanvasCharAnalysis)
class CanvasCharAnalysis {
  final String charId;

  /// target_text 없이 자유연습한 세션은 획순 채점 자체가 생략되어 null.
  final StrokeOrderResult? strokeOrderResult;
  final double spacingDeviation;
  final double sizeDeviation;
  final WritingMotionProfile motion;
  final int overallScore;

  /// 교정 플래그 (예: size_large, spacing_too_narrow, stroke_order_error)
  /// DATA_FLOW.md §8-C
  final List<String> correctionFlags;

  const CanvasCharAnalysis({
    required this.charId,
    required this.strokeOrderResult,
    required this.spacingDeviation,
    required this.sizeDeviation,
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
      spacingDeviation: (json['spacing_deviation'] as num).toDouble(),
      sizeDeviation: (json['size_deviation'] as num).toDouble(),
      motion: WritingMotionProfile.fromJson(
        pressureProfile: json['pressure_profile'] as Map<String, dynamic>?,
        speedProfile: json['speed_profile'] as Map<String, dynamic>?,
      ),
      overallScore: (json['overall_score'] as num).toInt(),
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
