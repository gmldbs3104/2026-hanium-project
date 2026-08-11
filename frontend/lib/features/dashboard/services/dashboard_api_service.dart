import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../models/dashboard_response.dart';

/// 학습 관리 대시보드 API 서비스 (SFR-008 대응)
///
/// canvas_api_service.dart / image_api_service.dart 와 동일한 패턴:
/// [AppConfig.useMockApi] 가 true인 동안은 실제 네트워크 호출 없이
/// mock 데이터로 화면을 테스트한다.
///
/// ★ 백엔드 연동 방법 ★
/// [AppConfig.useMockApi] 를 false로 바꾸면 GET /api/v1/dashboard 를
/// 실제로 호출한다. 이 엔드포인트는 인증이 필요하므로 [idToken]을 반드시 넘겨야 한다
/// (Firebase ID Token — auth_controller.dart의 getCurrentIdToken() 참고).
class DashboardApiService {
  static Future<DashboardResponse> fetch({
    required DashboardPeriod period,
    required DashboardModeFilter mode,
    String? idToken,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockFetch(period: period, mode: mode);
    }

    final response = await ApiClient.get(
      AppConfig.dashboardEndpoint,
      queryParams: {
        'period': period.value,
        'mode': mode.value,
      },
      authToken: idToken,
    );
    return DashboardResponse.fromJson(response);
  }

  /// ===== Mock 구현 =====
  /// period/mode 필터를 실제로 반영해서, 화면에서 필터를 바꿨을 때
  /// 데이터도 그에 맞게 달라지는 것처럼 보이도록 구성했다.
  static Future<DashboardResponse> _mockFetch({
    required DashboardPeriod period,
    required DashboardModeFilter mode,
  }) async {
    await Future.delayed(AppConfig.mockDelay);

    final allWeakItems = [
      const WeakItem(item: '받침 ㄹ', avgScore: 52.0, frequency: 14, mode: 'canvas'),
      const WeakItem(item: '자간 넓음', avgScore: 58.5, frequency: 11, mode: 'canvas'),
      const WeakItem(item: '기울기(우측)', avgScore: 61.0, frequency: 9, mode: 'image'),
      const WeakItem(item: '크기 불균일', avgScore: 63.5, frequency: 8, mode: 'image'),
      const WeakItem(item: '획순 오류(ㅂ)', avgScore: 66.0, frequency: 6, mode: 'canvas'),
    ];

    final allExercises = [
      const RecommendedExercise(
        text: '달빛이 조용히 내려앉은 밤',
        targetItems: ['받침 ㄹ', '자간 넓음'],
        difficulty: 'easy',
        mode: 'canvas',
      ),
      const RecommendedExercise(
        text: '바람에 흔들리는 나뭇잎 소리',
        targetItems: ['받침 ㄹ'],
        difficulty: 'medium',
        mode: 'canvas',
      ),
      const RecommendedExercise(
        text: '고요한 아침, 새소리가 들린다',
        targetItems: ['기울기(우측)', '크기 불균일'],
        difficulty: 'medium',
        mode: 'image',
      ),
      const RecommendedExercise(
        text: '느린 걸음으로 걷는 오후',
        targetItems: ['크기 불균일'],
        difficulty: 'hard',
        mode: 'image',
      ),
    ];

    final now = DateTime.now();
    final trendDays = switch (period) {
      DashboardPeriod.week => 7,
      DashboardPeriod.month => 30,
      DashboardPeriod.all => 90,
    };
    final allTrend = List.generate(trendDays, (i) {
      final day = now.subtract(Duration(days: trendDays - 1 - i));
      final base = 60 + (i * (78 - 60) / trendDays); // 완만한 상승 추세 mock
      return ScoreTrendPoint(
        date: DateTime(day.year, day.month, day.day),
        avgScore: base + (i % 5 == 0 ? -4 : 0), // 약간의 굴곡
        mode: i % 2 == 0 ? 'canvas' : 'image',
      );
    });

    bool matchesMode(String itemMode) => mode == DashboardModeFilter.all || itemMode == mode.value;

    final weakItems = allWeakItems.where((w) => matchesMode(w.mode)).take(10).toList();
    final exercises = allExercises.where((e) => matchesMode(e.mode)).take(5).toList();
    final trend = allTrend.where((t) => matchesMode(t.mode)).toList();

    const canvasSessions = 18;
    const imageSessions = 12;

    return DashboardResponse(
      periodSummary: PeriodSummary(
        totalSessions: mode == DashboardModeFilter.all
            ? canvasSessions + imageSessions
            : (mode == DashboardModeFilter.canvas ? canvasSessions : imageSessions),
        avgScore: 74.5,
        improvementRate: 12.0,
        canvasSessions: canvasSessions,
        imageSessions: imageSessions,
      ),
      weakItems: weakItems,
      scoreTrend: trend,
      recommendedExercises: exercises,
      level: 5,
      streakDays: 21,
    );
  }
}
