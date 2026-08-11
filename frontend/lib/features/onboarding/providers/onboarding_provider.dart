import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 온보딩(연습 목표 선택) 로컬 상태.
/// 백엔드와 무관한 순수 클라이언트 설정.
///
/// 교정 기준 폰트는 명조체로 고정이라 선택 상태가 없다 (AI/백엔드가 명조체만 지원).

const _onboardingPrefsKey = 'onboarding_completed';

/// 앱 시작 시(main.dart) 이 값을 읽어 [onboardingCompletedProvider]의 초기값으로
/// 덮어써야 한다 — 로그인 기록이 있으면 온보딩을 다시 보여주지 않기 위함.
/// (StateProvider는 초기값을 동기적으로 알아야 라우터 redirect가 첫 프레임부터
/// 정확히 동작하므로, Notifier의 비동기 로드 대신 main()에서 미리 읽어 override한다)
Future<bool> loadOnboardingCompleted() async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getBool(_onboardingPrefsKey) ?? false;
}

Future<void> saveOnboardingCompleted() async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setBool(_onboardingPrefsKey, true);
}

/// 손글씨 연습 목표(복수 선택)
enum PracticeGoal { infantBasics, examLegibility, seniorRehab, calligraphy }

extension PracticeGoalLabel on PracticeGoal {
  String get label => switch (this) {
        PracticeGoal.infantBasics => '영유아 기초',
        PracticeGoal.examLegibility => '수험생 가독성 개선',
        PracticeGoal.seniorRehab => '시니어 인지 재활',
        PracticeGoal.calligraphy => '캘리그라피',
      };
}

/// 선택된 목표 집합(복수 선택 가능)
final selectedGoalsProvider =
    StateProvider<Set<PracticeGoal>>((ref) => <PracticeGoal>{});

/// 온보딩 완료 여부(라우터 가드에서 로그인 직후 온보딩으로 보낼지 판단).
/// ⚠️ 기본값은 false지만, main.dart가 [loadOnboardingCompleted]로 읽은 값을
/// ProviderScope override로 미리 채워 넣는다 — 그래서 실제로는 SharedPreferences에
/// 저장된 값(최초 1회만 온보딩)으로 시작한다.
final onboardingCompletedProvider = StateProvider<bool>((ref) => false);
