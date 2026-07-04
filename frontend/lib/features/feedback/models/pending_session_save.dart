/// SFR-009 REQ-009-5: 네트워크 장애로 저장에 실패했을 때 로컬 큐에 쌓아두는 항목.
/// 연결이 복구되면(또는 다음에 앱을 열었을 때) [SessionSaveQueue.flush]가
/// 이 정보로 다시 저장을 시도한다.
class PendingSessionSave {
  final String mode; // "canvas" | "image"
  final String sessionId;

  /// 이미지 모드에서만 의미 있음 (캔버스는 항상 false)
  final bool saveImage;

  const PendingSessionSave({
    required this.mode,
    required this.sessionId,
    this.saveImage = false,
  });

  Map<String, dynamic> toJson() => {
        'mode': mode,
        'session_id': sessionId,
        'save_image': saveImage,
      };

  factory PendingSessionSave.fromJson(Map<String, dynamic> json) {
    return PendingSessionSave(
      mode: json['mode'] as String,
      sessionId: json['session_id'] as String,
      saveImage: json['save_image'] as bool? ?? false,
    );
  }
}
