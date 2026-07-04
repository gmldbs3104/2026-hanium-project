import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/providers/auth_controller.dart';
import '../../features/auth/providers/auth_state.dart';
import '../../features/auth/screens/login_screen.dart';
import '../../features/canvas_mode/models/stroke.dart';
import '../../features/canvas_mode/screens/canvas_input_screen.dart';
import '../../features/dashboard/screens/dashboard_screen.dart';
import '../../features/feedback/screens/feedback_screen.dart';
import '../../features/home/screens/home_screen.dart';
import '../../features/image_mode/screens/image_capture_screen.dart';

/// 인증 상태가 바뀔 때마다 라우터가 재평가되도록 만들어주는 Listenable
/// (go_router는 Riverpod 상태 변화를 직접 알지 못하므로 이 어댑터가 필요합니다)
class _AuthRefreshListenable extends ChangeNotifier {
  _AuthRefreshListenable(Ref ref) {
    ref.listen(authControllerProvider, (_, __) => notifyListeners());
  }
}

/// 앱 전역 라우터 (go_router)
///
/// 인증 가드:
///  - 로그인하지 않은 상태에서 다른 화면 접근 시 → /login 으로 리다이렉트
///  - 로그인 완료 후 /login 화면에 남아있으면 → /home 으로 리다이렉트
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/login',
    refreshListenable: _AuthRefreshListenable(ref),
    redirect: (context, state) {
      final authState = ref.read(authControllerProvider);
      final isLoggedIn = authState is AuthAuthenticated;
      final isLoginRoute = state.matchedLocation == '/login';

      if (!isLoggedIn && !isLoginRoute) return '/login';
      if (isLoggedIn && isLoginRoute) return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/home', builder: (context, state) => const HomeScreen()),
      GoRoute(path: '/dashboard', builder: (context, state) => const DashboardScreen()),
      GoRoute(path: '/canvas', builder: (context, state) => const CanvasInputScreen()),
      GoRoute(
        path: '/image-capture',
        builder: (context, state) => const ImageCaptureScreen(),
      ),
      GoRoute(
        path: '/feedback',
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>;
          final mode = extra['mode'] as String;

          return FeedbackScreen(
            mode: mode,
            sessionId: extra['sessionId'] as String,
            // SFR-007 오버레이용 — mode에 따라 아래 중 필요한 것만 넘어옴
            strokes: extra['strokes'] as List<Stroke>?,
            canvasMetadata: extra['canvasMetadata'] as CanvasMetadata?,
            imageBytes: extra['imageBytes'] as List<int>?,
            imageWidth: extra['imageWidth'] as int?,
            imageHeight: extra['imageHeight'] as int?,
          );
        },
      ),
    ],
  );
});
