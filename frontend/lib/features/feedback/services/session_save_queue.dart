import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../shared/services/api_client.dart';
import '../../canvas_mode/services/canvas_api_service.dart';
import '../../image_mode/services/image_api_service.dart';
import '../models/pending_session_save.dart';

/// SFR-009 REQ-009-5: "네트워크 장애 시 로컬 큐에 저장하고 연결 복구 후
/// 자동으로 재전송(Retry)해야 한다."
///
/// requirement.md는 서버 측 재시도 큐(트랜잭션 실패 시)를 말하지만, 클라이언트
/// 쪽에서도 confirm() 호출 자체가 네트워크 문제로 실패할 수 있으므로 같은 개념을
/// 로컬(SharedPreferences)에 구현했다.
///
/// 두 모드(canvas/image)가 SFR-007·009 단계에서 합류한다는 requirement.md 설명에
/// 따라, 이 큐는 feedback 기능 아래 둔다 (canvas_mode/image_mode 양쪽 서비스를
/// 모두 참조해야 해서 어느 한쪽 하위에 두기보다 합류 지점이 적절함).
class SessionSaveQueue {
  static const _prefsKey = 'pending_session_saves';

  static Future<List<PendingSessionSave>> _readAll() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_prefsKey) ?? const [];
    return raw
        .map((s) => PendingSessionSave.fromJson(jsonDecode(s) as Map<String, dynamic>))
        .toList();
  }

  static Future<void> _writeAll(List<PendingSessionSave> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _prefsKey,
      items.map((i) => jsonEncode(i.toJson())).toList(),
    );
  }

  /// 현재 재전송 대기 중인 항목 수 (UI에 "동기화 대기 N건" 표시용)
  static Future<int> pendingCount() async => (await _readAll()).length;

  /// 저장 실패한 항목을 큐에 추가
  static Future<void> enqueue(PendingSessionSave item) async {
    final items = await _readAll();
    items.add(item);
    await _writeAll(items);
  }

  /// 큐에 쌓인 항목들을 순서대로 다시 저장 시도한다.
  /// 반환값: 이번 flush에서 성공적으로 저장된 항목 수.
  ///
  /// 재시도 정책(REQ-009-5는 "네트워크 장애" 복구용 큐):
  ///  - 성공: 큐에서 제거
  ///  - 네트워크 장애(ApiException.statusCode == null): 큐에 유지 → 다음 flush에서 재시도
  ///  - 서버 4xx/5xx(statusCode != null): 재시도해도 같은 이유로 실패하므로 큐에서 제거
  ///    (poison 항목이 큐를 무한 점유하는 것을 방지)
  ///  - 분류 불가 예외: 데이터 유실 방지를 위해 보수적으로 큐에 유지
  static Future<int> flush() async {
    final items = await _readAll();
    if (items.isEmpty) return 0;

    final remaining = <PendingSessionSave>[];
    var succeeded = 0;

    for (final item in items) {
      try {
        if (item.mode == 'canvas') {
          await CanvasApiService.confirm(item.sessionId);
        } else {
          await ImageApiService.confirm(item.sessionId, saveImage: item.saveImage);
        }
        succeeded++;
      } on ApiException catch (e) {
        if (e.statusCode == null) {
          remaining.add(item); // 네트워크 장애 → 다음 flush에서 재시도
        } else {
          // 서버가 거부한 요청(4xx/5xx) → 큐에서 제거 (무한 재시도 방지)
          debugPrint('[SessionSaveQueue] dropping ${item.sessionId} (server error ${e.statusCode})');
        }
      } catch (e) {
        remaining.add(item); // 분류 불가 예외 → 유실 방지 위해 큐 유지
      }
    }

    await _writeAll(remaining);
    return succeeded;
  }
}
