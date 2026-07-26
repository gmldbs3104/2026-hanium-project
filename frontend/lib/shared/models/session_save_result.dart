/// POST /api/v1/{canvas|image}/{session_id}/confirm 응답 (requirement.md SFR-009 Outputs 기준)
///
/// {session_id, saved_at, mode} + 동기화 상태 {firestore_synced, s3_uploaded}
class SessionSaveResult {
  final String sessionId;
  final DateTime savedAt;
  final String mode; // "canvas" | "image"
  final bool firestoreSynced;
  final bool s3Uploaded;

  const SessionSaveResult({
    required this.sessionId,
    required this.savedAt,
    required this.mode,
    required this.firestoreSynced,
    required this.s3Uploaded,
  });

  factory SessionSaveResult.fromJson(Map<String, dynamic> json) {
    return SessionSaveResult(
      sessionId: json['session_id'] as String,
      savedAt: DateTime.parse(json['saved_at'] as String),
      mode: json['mode'] as String,
      firestoreSynced: json['firestore_synced'] as bool? ?? false,
      s3Uploaded: json['s3_uploaded'] as bool? ?? false,
    );
  }
}
