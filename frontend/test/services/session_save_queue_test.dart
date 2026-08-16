import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/feedback/models/pending_session_save.dart';
import 'package:frontend/features/feedback/services/session_save_queue.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// SFR-009 오프라인 재시도 큐(REQ-009-5) 검증.
///
/// 참고: 서버 4xx/5xx 분기는 실제 서버 응답이 있어야 하고 API 서비스가 정적
/// 클래스라 주입할 수 없어 여기서는 다루지 않는다.
///
/// ⚠️ 이 파일은 한때 "mock 저장 성공 시 flush가 큐를 비운다"를 검증했다.
/// 2026-08-02에 `AppConfig.useMockApi`가 false로 바뀌면서 confirm이 실제 HTTP를
/// 때리게 됐고, 테스트 환경엔 서버가 없어 그 테스트가 깨진 채 방치됐다(2주간).
/// mock 성공 경로를 되살릴 수 없으므로, **서버가 없을 때의 계약**을 대신 검증한다 —
/// REQ-009-5가 큐를 둔 이유가 정확히 그 상황이라 오히려 본래 목적에 가깝다.
void main() {
  setUp(() {
    // 각 테스트마다 SharedPreferences를 빈 상태로 초기화
    SharedPreferences.setMockInitialValues({});
  });

  group('PendingSessionSave 직렬화', () {
    test('toJson/fromJson 왕복', () {
      const item =
          PendingSessionSave(mode: 'image', sessionId: 's1', saveImage: true);
      final restored = PendingSessionSave.fromJson(item.toJson());

      expect(restored.mode, 'image');
      expect(restored.sessionId, 's1');
      expect(restored.saveImage, true);
    });

    test('save_image 누락 시 false로 복원한다', () {
      final restored =
          PendingSessionSave.fromJson({'mode': 'canvas', 'session_id': 's2'});
      expect(restored.saveImage, false);
    });
  });

  group('SessionSaveQueue', () {
    test('enqueue 하면 pendingCount가 증가한다', () async {
      expect(await SessionSaveQueue.pendingCount(), 0);

      await SessionSaveQueue.enqueue(
          const PendingSessionSave(mode: 'canvas', sessionId: 's1'));
      await SessionSaveQueue.enqueue(const PendingSessionSave(
          mode: 'image', sessionId: 's2', saveImage: true));

      expect(await SessionSaveQueue.pendingCount(), 2);
    });

    test('서버에 못 붙으면 큐를 유지한다 (REQ-009-5 네트워크 장애 재시도)', () async {
      await SessionSaveQueue.enqueue(
          const PendingSessionSave(mode: 'canvas', sessionId: 's1'));

      // 테스트 환경엔 백엔드가 없다 → ApiClient가 statusCode 없는 ApiException을
      // 던지고, flush는 "네트워크 장애"로 보아 항목을 큐에 남긴다.
      final succeeded = await SessionSaveQueue.flush();

      expect(succeeded, 0, reason: '저장된 항목이 없어야 한다');
      expect(await SessionSaveQueue.pendingCount(), 1,
          reason: '네트워크 장애는 다음 flush에서 재시도해야 하므로 큐에 남아야 한다');
    });

    test('연결이 계속 안 되면 여러 번 flush해도 항목이 사라지지 않는다', () async {
      await SessionSaveQueue.enqueue(
          const PendingSessionSave(mode: 'image', sessionId: 's2', saveImage: true));

      await SessionSaveQueue.flush();
      await SessionSaveQueue.flush();

      // 재시도 큐의 존재 이유 — 연결이 돌아올 때까지 사용자의 기록을 잃지 않는다.
      expect(await SessionSaveQueue.pendingCount(), 1);
    });

    test('빈 큐를 flush하면 0을 반환한다', () async {
      expect(await SessionSaveQueue.flush(), 0);
    });
  });
}
