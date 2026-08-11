import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 필기 환경 설정(가이드 글자 투명도 / 그림판 테마)의 "저장된" 값 (mypage_upgrade.md 3.4-2).
///
/// SettingsScreen의 슬라이더·테마 칩은 화면 안에서 즉시 미리보기에 반영되지만,
/// "저장" 버튼을 눌러야 이 provider에 반영된다. ⚠️ 아직 실제 연습 화면
/// (canvas_mode/screens/canvas_input_screen.dart의 StrokeOrderGuidePainter)에는
/// 연결돼 있지 않다 — 적용 여부/방식은 보류, 상의 필요(mypage_upgrade.md 3.4-2 참고).
/// 지금은 값을 앱 상태로 들고 있는 것까지만 한다.
class HandwritingEnv {
  final double guideOpacity; // 0.0~1.0, 기본 0.5
  final int boardTheme; // 0 무지, 1 격자, 2 줄글, 3 원고지 — 기본 0

  const HandwritingEnv({required this.guideOpacity, required this.boardTheme});
}

const handwritingEnvDefault = HandwritingEnv(guideOpacity: 0.5, boardTheme: 0);

final handwritingEnvProvider = StateProvider<HandwritingEnv>((ref) => handwritingEnvDefault);
