import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/feedback/models/pending_session_save.dart';
import 'package:frontend/features/feedback/services/session_save_queue.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// SFR-009 오프라인 재시도 큐(REQ-009-5) 검증.
///
/// 참고: 서버 4xx/5xx vs 네트워크 장애 분기(feedback_screen/flush의 최근 수정)는
/// 정적 API 서비스에 강하게 결합돼 있어 여기서는 단위 테스트하지 않는다.
/// 여기서는 큐의 영속화(enqueue/pendingCount)와 mock 성공 시 flush가 큐를
/// 비우는지를 검증한다 (AppConfig.useMockApi=true라 confirm mock은 성공).
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

    test('flush는 mock 저장 성공 시 큐를 비운다', () async {
      await SessionSaveQueue.enqueue(
          const PendingSessionSave(mode: 'canvas', sessionId: 's1'));

      final succeeded = await SessionSaveQueue.flush();

      expect(succeeded, 1);
      expect(await SessionSaveQueue.pendingCount(), 0);
    });

    test('빈 큐를 flush하면 0을 반환한다', () async {
      expect(await SessionSaveQueue.flush(), 0);
    });
  });
}
