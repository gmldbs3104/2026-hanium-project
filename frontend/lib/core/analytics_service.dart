import 'package:firebase_analytics/firebase_analytics.dart';
import 'package:flutter/foundation.dart';

import 'app_config.dart';

/// Firebase Analytics 로깅 서비스.
///
/// 로그인(AuthController)과 동일한 패턴으로 동작한다:
/// [AppConfig.useMockApi] 가 true인 동안은 Firebase를 초기화하지 않으므로
/// (main.dart 참고) 실제 Analytics 호출 대신 debugPrint로 대체한다.
/// useMockApi=false + Firebase 프로젝트 설정이 완료되면 실제 이벤트가 전송된다.
class AnalyticsService {
  AnalyticsService._();

  /// SFR-002 Side Effect: 메인 화면 모드 선택 이벤트 로깅
  static Future<void> logModeSelected(String mode) =>
      _logEvent('mode_selected', {'mode': mode});

  static Future<void> _logEvent(String name, Map<String, Object> parameters) async {
    if (AppConfig.useMockApi) {
      debugPrint('[Analytics] $name: $parameters');
      return;
    }
    await FirebaseAnalytics.instance.logEvent(name: name, parameters: parameters);
  }
}
