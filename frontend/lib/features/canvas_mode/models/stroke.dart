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
  final double width;
  final double height;
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

/// /api/v1/canvas/analyze 응답 모델 (mock 단계에서는 단순화된 형태)
class CanvasAnalyzeResult {
  final String canvasSessionId;
  final int overallScore;

  const CanvasAnalyzeResult({
    required this.canvasSessionId,
    required this.overallScore,
  });

  factory CanvasAnalyzeResult.fromJson(Map<String, dynamic> json) {
    return CanvasAnalyzeResult(
      canvasSessionId: json['canvas_session_id'] as String,
      overallScore: json['overall_score'] as int,
    );
  }
}
