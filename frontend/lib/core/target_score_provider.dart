import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 사용자가 설정하는 "목표 점수".
///
/// 앱 로컬 상태(백엔드 무관)이며 기본값은 90점.
/// 상세환경설정(SettingsScreen)에서 슬라이더로 변경하고,
/// 결과 화면(FeedbackScreen)의 점수 카드가 이 값을 목표로 사용한다.
final targetScoreProvider = StateProvider<int>((ref) => 90);
