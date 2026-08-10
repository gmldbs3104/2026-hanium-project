/// 획 내의 한 점 (SFR-003C Inputs 기준: {x, y, pressure, timestamp})
class StrokePoint {
  final double x;
  final double y;
  final double pressure;
  final int timestamp;

  const StrokePoint({
    required this.x,
    required this.y,
    required this.pressure,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
        'x': x,
        'y': y,
        'pressure': pressure,
        'timestamp': timestamp,
      };
}

/// 하나의 획 (펜/손가락을 대고 뗄 때까지의 연속된 좌표 시퀀스)
class Stroke {
  final String strokeId;
  final List<StrokePoint> points;

  Stroke({required this.strokeId, required this.points});

  Map<String, dynamic> toJson() => {
        'stroke_id': strokeId,
        'points': points.map((p) => p.toJson()).toList(),
      };
}

/// 캔버스 메타데이터 (SFR-003C Outputs 기준)
class CanvasMetadata {
  final int width;
  final int height;
  final int strokeCount;

  const CanvasMetadata({
    required this.width,
    required this.height,
    required this.strokeCount,
  });

  Map<String, dynamic> toJson() => {
        'width': width,
        'height': height,
        'stroke_count': strokeCount,
      };
}

/// POST /api/v1/canvas/analyze 응답 모델 (schemas/canvas.py CanvasAnalyzeResponse)
///
/// ⚠️ 이 단계는 아직 분석 전 "접수 확인" 응답이라 overall_score가 없습니다.
/// (이전엔 mock 편의상 overall_score를 여기 끼워 넣었는데, 실제 백엔드로 바꾸면
///  이 필드가 없어서 파싱 에러가 났을 것 — 최종 점수는 반드시
///  /canvas/{id}/feedback 응답(CanvasFeedbackResponse.overallScore)에서 받아야 합니다.)
class CanvasAnalyzeResult {
  final String canvasSessionId;
  final int strokeCount;
  final String status;

  const CanvasAnalyzeResult({
    required this.canvasSessionId,
    required this.strokeCount,
    required this.status,
  });

  factory CanvasAnalyzeResult.fromJson(Map<String, dynamic> json) {
    return CanvasAnalyzeResult(
      canvasSessionId: json['canvas_session_id'] as String,
      strokeCount: json['stroke_count'] as int,
      status: json['status'] as String? ?? 'received',
    );
  }
}
