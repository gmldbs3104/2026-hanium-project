import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/providers/auth_controller.dart';
import '../../features/auth/providers/auth_state.dart';
import '../../features/auth/screens/login_screen.dart';
import '../../features/canvas_mode/models/stroke.dart';
import '../../features/canvas_mode/screens/canvas_input_screen.dart';
import '../../features/dashboard/screens/report_screen.dart';
import '../../features/feedback/screens/feedback_screen.dart';
import '../../features/image_mode/screens/image_capture_screen.dart';
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
      GoRoute(path: '/main', builder: (context, state) => const MainShell()),
      // 기존 코드 호환: /home 은 메인 셸로 리다이렉트
      GoRoute(path: '/home', redirect: (_, __) => '/main'),

      GoRoute(path: '/basics', builder: (context, state) => const BasicsScreen()),
      GoRoute(
          path: '/character-practice',
          builder: (context, state) => const CanvasInputScreen()),
      GoRoute(
          path: '/sentence-practice',
          builder: (context, state) => const SentencePracticeScreen()),
      GoRoute(
          path: '/image-capture',
          builder: (context, state) => const ImageCaptureScreen()),
      GoRoute(path: '/report', builder: (context, state) => const ReportScreen()),
      GoRoute(
          path: '/settings', builder: (context, state) => const SettingsScreen()),

      GoRoute(
        path: '/feedback',
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
          );
        },
      ),
    ],
  );
});
