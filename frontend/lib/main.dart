import 'dart:async';

import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/app_config.dart';
import 'core/app_theme.dart';
import 'core/theme_provider.dart';
import 'features/feedback/services/session_save_queue.dart';
import 'features/onboarding/providers/onboarding_provider.dart';
import 'shared/router/app_router.dart';

import 'firebase_options.dart';

Future<void> main() async {
  // ⚠️ SFR-009 오프라인 재시도 큐가 shared_preferences(플러그인)를 쓰기 때문에,
  // mock 모드 여부와 무관하게 바인딩 초기화는 항상 필요하다.
  WidgetsFlutterBinding.ensureInitialized();

  // mock 모드에서는 Firebase 프로젝트 설정 없이도 앱이 뜨도록 초기화를 건너뜀.
  // 실제 로그인 테스트 시 AppConfig.useMockApi를 false로 바꾸기 *전에*
  // `flutterfire configure`로 firebase_options.dart를 생성해야 한다.
  if (!AppConfig.useMockApi) {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  }

  // REQ-009-5: 이전 세션에서 저장에 실패해 쌓여있던 항목이 있다면,
  // 앱을 다시 켰을 때(=연결이 복구됐을 가능성이 높을 때) 조용히 재시도한다.
  // 결과를 기다리지 않고 백그라운드로 흘려보낸다 (앱 시작을 지연시키지 않기 위함).
  unawaited(SessionSaveQueue.flush());

  // 온보딩은 최초 1회만 — 로그인 기록(SharedPreferences)이 있으면 온보딩 화면을
  // 건너뛰고 바로 메인(홈) 화면으로 간다. 라우터의 redirect가 첫 프레임부터 정확히
  // 판단해야 하므로 runApp 전에 미리 읽어서 provider 초기값으로 override한다.
  final onboardingDone = await loadOnboardingCompleted();

  runApp(ProviderScope(
    overrides: [
      onboardingCompletedProvider.overrideWith((ref) => onboardingDone),
    ],
    child: const HandwritingApp(),
  ));
}

class HandwritingApp extends ConsumerWidget {
  const HandwritingApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final themeMode = ref.watch(themeModeProvider);

    return MaterialApp.router(
      title: 'AI 손글씨 교정',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: themeMode, // SFR-007 Inputs: light / dark (기본 시스템 설정)
      routerConfig: router,
    );
  }
}
