import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 온보딩(목표·기준 폰트 선택) 로컬 상태.
/// 백엔드와 무관한 순수 클라이언트 설정이며, 현재는 인메모리로만 유지한다.
/// (영속화가 필요하면 shared_preferences로 확장 — 추후)

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

/// 교정 기준 폰트
enum CorrectionFont { gothic, myeongjo, round }

extension CorrectionFontLabel on CorrectionFont {
  String get label => switch (this) {
        CorrectionFont.gothic => '고딕체',
        CorrectionFont.myeongjo => '명조체',
        CorrectionFont.round => '둥근체',
      };
}

/// 선택된 목표 집합(복수 선택 가능)
final selectedGoalsProvider =
    StateProvider<Set<PracticeGoal>>((ref) => <PracticeGoal>{});

/// 선택된 기준 폰트(기본값: 고딕체)
final selectedFontProvider =
    StateProvider<CorrectionFont>((ref) => CorrectionFont.gothic);

/// 온보딩 완료 여부(라우터 가드에서 로그인 직후 온보딩으로 보낼지 판단).
/// 인메모리 상태 — 앱 재시작 시 다시 온보딩을 거친다.
final onboardingCompletedProvider = StateProvider<bool>((ref) => false);
