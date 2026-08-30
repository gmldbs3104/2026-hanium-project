import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/analysis/screens/analysis_screen.dart';
import '../../features/auth/providers/auth_controller.dart';
import '../../features/auth/providers/auth_state.dart';
import '../../features/auth/screens/login_screen.dart';
import '../../features/canvas_mode/models/stroke.dart';
import '../../features/canvas_mode/screens/canvas_input_screen.dart';
import '../../features/dashboard/screens/report_screen.dart';
import '../../features/feedback/screens/feedback_screen.dart';
import '../../features/home/screens/home_screen.dart';
import '../../features/image_mode/screens/image_capture_screen.dart';
import '../../features/mypage/screens/achievement_screen.dart';
import '../../features/mypage/screens/mypage_screen.dart';
import '../../features/mypage/screens/profile_edit_screen.dart';
import '../../features/mypage/screens/settings_screen.dart';
import '../../features/onboarding/providers/onboarding_provider.dart';
import '../../features/onboarding/screens/onboarding_screen.dart';
import '../../features/practice/screens/basics_screen.dart';
import '../../features/practice/screens/sentence_practice_screen.dart';
import '../../features/shell/main_shell.dart';

/// 인증 상태가 바뀔 때마다 라우터가 재평가되도록 만들어주는 Listenable
class _AuthRefreshListenable extends ChangeNotifier {
  _AuthRefreshListenable(Ref ref) {
    ref.listen(authControllerProvider, (_, __) => notifyListeners());
  }
}

/// 앱 전역 라우터 (go_router)
///
/// 인증 + 온보딩 가드:
///  - 미로그인 상태에서 다른 화면 접근 → /login
///  - 로그인 완료 + 온보딩 미완료 → /onboarding
///  - 로그인 완료 + 온보딩 완료 후 /login 접근 → /main
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/login',
    refreshListenable: _AuthRefreshListenable(ref),
    redirect: (context, state) {
      final authState = ref.read(authControllerProvider);
      final isLoggedIn = authState is AuthAuthenticated;
      final loc = state.matchedLocation;
      final isLoginRoute = loc == '/login';
      final isOnboardingRoute = loc == '/onboarding';

      // 새로고침 직후 Firebase 세션 복원 중(auth_controller.dart의 _restoreSession)이면
      // 아직 로그인 여부를 모른다 — 로그인 화면으로 리다이렉트하지 않고 지금 화면(예:
      // 새로고침 전 /main)에 그대로 머무른다. 로그인 화면 자체는 원래 AuthLoading일 때
      // 로딩 스피너를 보여주므로 그대로 둔다.
      if (authState is AuthLoading && !isLoginRoute) {
        return null;
      }

      if (!isLoggedIn) {
        return isLoginRoute ? null : '/login';
      }

      // 로그인 완료 상태
      final onboarded = ref.read(onboardingCompletedProvider);
      if (isLoginRoute) return onboarded ? '/main' : '/onboarding';
      if (!onboarded && !isOnboardingRoute) return '/onboarding';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(
          path: '/onboarding',
          builder: (context, state) => const OnboardingScreen()),
      // 하단 네비게이션 메인 셸 (홈 · AI 교정 · 분석 · 마이)
      // 탭마다 실제 URL을 가진 브랜치로 분리 — 새로고침(브라우저 하드 리로드)해도
      // 마지막에 보던 탭이 유지되도록 하기 위함(이전엔 탭이 URL에 반영되지 않는
      // 순수 앱 상태라 새로고침하면 항상 홈 탭으로 돌아갔다).
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            MainShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/main', builder: (context, state) => const HomeScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
                path: '/main/analysis',
                builder: (context, state) => const AnalysisScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
                path: '/main/mypage',
                builder: (context, state) => const MyPageScreen()),
          ]),
        ],
      ),
      // 기존 코드 호환: /home 은 메인 셸로 리다이렉트
      GoRoute(path: '/home', redirect: (_, __) => '/main'),

      GoRoute(path: '/basics', builder: (context, state) => const BasicsScreen()),
      GoRoute(
          path: '/character-practice',
          builder: (context, state) {
            // 결과 화면 "다음 글자"에서 특정 탭/글자로 진입할 수 있다.
            final extra = state.extra as Map<String, dynamic>?;
            return CanvasInputScreen(
              initialTabIndex: extra?['tabIndex'] as int?,
              initialCharIndex: extra?['charIndex'] as int?,
            );
          }),
      GoRoute(
          path: '/sentence-practice',
          builder: (context, state) {
            final extra = state.extra as Map<String, dynamic>?;
            return SentencePracticeScreen(
              initialTabIndex: extra?['tabIndex'] as int?,
            );
          }),
      GoRoute(
          path: '/image-capture',
          builder: (context, state) => const ImageCaptureScreen()),
      GoRoute(path: '/report', builder: (context, state) => const ReportScreen()),
      GoRoute(
          path: '/settings', builder: (context, state) => const SettingsScreen()),
      GoRoute(
          path: '/achievements',
          builder: (context, state) => const AchievementScreen()),
      GoRoute(
          path: '/profile-edit',
          builder: (context, state) => const ProfileEditScreen()),

      GoRoute(
        path: '/feedback',
        // 브라우저 새로고침/뒤로가기 등 in-memory extra 없이 URL만으로 이 라우트에
        // 도달하면(특히 Flutter web) state.extra가 null이라 builder의 캐스팅이 그대로
        // 터진다 — 필기/이미지 데이터를 URL만으로 복원할 방법이 없으니 홈으로 보낸다.
        redirect: (context, state) =>
            state.extra is Map<String, dynamic> ? null : '/main',
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>;
          final mode = extra['mode'] as String;

          return FeedbackScreen(
            mode: mode,
            sessionId: extra['sessionId'] as String,
            strokes: extra['strokes'] as List<Stroke>?,
            canvasMetadata: extra['canvasMetadata'] as CanvasMetadata?,
            strokeWidth: extra['strokeWidth'] as double?,
            imageBytes: extra['imageBytes'] as List<int>?,
            imageWidth: extra['imageWidth'] as int?,
            imageHeight: extra['imageHeight'] as int?,
            preservationMode: extra['preservationMode'] as bool?,
            // 연습 화면에서 넘어온 탭/진행률 컨텍스트 (없으면 헤더 생략)
            practiceTabs: (extra['practiceTabs'] as List?)?.cast<String>(),
            practiceTabIndex: extra['practiceTabIndex'] as int?,
            practiceStep: extra['practiceStep'] as int?,
            practiceTotal: extra['practiceTotal'] as int?,
            practiceRoute: extra['practiceRoute'] as String?,
          );
        },
      ),
    ],
  );
});
