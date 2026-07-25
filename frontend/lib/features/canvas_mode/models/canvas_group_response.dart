import 'char_group.dart';

/// POST /api/v1/canvas/{canvas_session_id}/group 응답 (schemas/canvas.py CanvasGroupResponse)
class CanvasGroupResponse {
  final String canvasSessionId;
  final List<CharGroup> charGroups;
  final int lowConfidenceCount;

  const CanvasGroupResponse({
    required this.canvasSessionId,
    required this.charGroups,
    required this.lowConfidenceCount,
  });

  factory CanvasGroupResponse.fromJson(Map<String, dynamic> json) {
    return CanvasGroupResponse(
      canvasSessionId: json['canvas_session_id'] as String,
      charGroups: (json['char_groups'] as List)
          .map((e) => CharGroup.fromJson(e as Map<String, dynamic>))
          .toList(),
      lowConfidenceCount: json['low_confidence_count'] as int,
    );
  }
}
