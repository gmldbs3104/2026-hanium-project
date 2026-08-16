import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/auth/providers/auth_controller.dart';
import 'package:frontend/features/auth/providers/auth_state.dart';
import 'package:frontend/features/onboarding/providers/onboarding_provider.dart';
import 'package:frontend/main.dart';

/// ⚠️ 이 파일은 한때 mock 로그인 화면을 전제로 작성됐다("mock 로그인 모드" 문구를
/// 찾고 "Google로 로그인"을 탭). 2026-08-02 백엔드 연동 커밋에서 로그인 화면이
/// Firebase 기반으로 다시 쓰이고 `AppConfig.useMockApi`가 false로 바뀌면서
/// 두 테스트가 깨진 채 2주간 방치됐다.
///
/// 이제는 **실제 로그인을 흉내 내지 않는다.** 위젯 테스트에서 Firebase를 태울 수
/// 없기도 하고, 애초에 검증 대상(SFR-002 모드 분기)은 로그인 자체가 아니다.
/// 인증 상태를 주입해 로그인 이후 화면 흐름만 본다.

/// 이미 로그인된 상태로 고정하는 가짜 컨트롤러.
class _AuthenticatedController extends AuthController {
  @override
  AuthState build() => const AuthAuthenticated(
        UserProfile(id: 'u1', email: 'tester@example.com', provider: 'google'),
      );
}

/// 로그인 완료 + 온보딩 완료 상태의 앱. (온보딩을 안 넘기면 라우터가 /onboarding으로
/// 리다이렉트해서 홈에 닿지 못한다.)
Widget _loggedInApp() => ProviderScope(
      overrides: [
        authControllerProvider.overrideWith(_AuthenticatedController.new),
        onboardingCompletedProvider.overrideWith((ref) => true),
      ],
      child: const HandwritingApp(),
    );

void main() {
  testWidgets('앱이 정상적으로 시작되고 로그인 화면이 보인다', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: HandwritingApp()));
    await tester.pumpAndSettle();

    // 미로그인 상태면 라우터 가드가 /login으로 보낸다.
    expect(find.text('Google 계정으로 시작하기'), findsOneWidget);
  });

  testWidgets('로그인 후 "손글씨 연습"을 선택하면 캔버스 입력 화면으로 이동한다 (SFR-002 모드 분기)',
      (tester) async {
    await tester.pumpWidget(_loggedInApp());
    await tester.pumpAndSettle();

    // 홈 화면의 캔버스 모드 카드
    expect(find.text('손글씨 연습'), findsOneWidget);
    await tester.tap(find.text('손글씨 연습'));
    await tester.pumpAndSettle();

    // 캔버스 입력 화면 진입 확인 — 자음/모음/받침 탭은 이 화면에만 있다.
    expect(find.text('자음 쓰기'), findsOneWidget);
    expect(find.text('모음 쓰기'), findsOneWidget);
  });
}
