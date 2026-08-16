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

  /// ⚠️ **알려진 취약점 (2026-08-17 발견, 의도적으로 안 고침)**
  ///
  /// `FirebaseAnalytics.instance`는 Firebase가 초기화되지 않았으면 **동기적으로**
  /// 예외를 던진다. 호출부가 `await`을 안 붙여도 그 예외는 탭 핸들러까지 올라간다.
  /// `home_screen._goPractice`가 이 호출을 `context.go()`보다 **앞**에서 하므로,
  /// 예외가 나면 **연습 카드를 눌러도 화면이 안 넘어간다** — 사용자는 "버튼이 안 먹는다"고
  /// 느끼는데 원인은 통계 수집이다.
  ///
  /// 실제 앱은 `main.dart`가 Firebase를 초기화하므로 지금은 재현되지 않는다.
  /// 초기화 실패·설정 누락 시에만 드러난다. (위젯 테스트에서는 Firebase가 없어
  /// 항상 이 경로를 타므로, 테스트는 인증 상태를 주입해 우회한다.)
  ///
  /// 고치려면 이 호출을 try/catch로 감싸면 된다(통계는 부가 기능이므로 실패해도
  /// 사용자 흐름을 막지 않아야 한다). 팀 판단으로 **지금은 제품 동작을 건드리지
  /// 않기로 했다**(2026-08-17). 상세: DEVLOG 23막.
  static Future<void> _logEvent(String name, Map<String, Object> parameters) async {
    if (AppConfig.useMockApi) {
      debugPrint('[Analytics] $name: $parameters');
      return;
    }
    await FirebaseAnalytics.instance.logEvent(name: name, parameters: parameters);
  }
}
