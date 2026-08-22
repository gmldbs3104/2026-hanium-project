import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 대시보드 요약(레벨/연속 출석일) 새로고침 신호.
///
/// 홈 화면(HomeScreen)은 StatefulShellRoute(IndexedStack) 브랜치라 탭을 벗어났다
/// 돌아와도 initState가 다시 실행되지 않는다 — 그래서 오늘 첫 연습을 마치고 피드백
/// 화면에서 "홈으로"를 눌러도 연속 출석일이 방금 갱신된 값(예: 0일→1일)으로 바뀌지
/// 않고 앱을 껐다 켜야만 반영되는 문제가 있었다. 이 값을 bump하면 HomeScreen이
/// 이를 감지해 대시보드 요약을 다시 불러온다.
final dashboardRefreshProvider = StateProvider<int>((ref) => 0);
