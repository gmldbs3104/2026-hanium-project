import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/app_theme.dart';

/// 하단 네비게이션을 가진 메인 셸 (홈 · AI 교정 · 분석 · 마이)
///
/// 홈/분석/마이는 각각 실제 URL(/main, /main/analysis, /main/mypage)을 가진
/// StatefulShellRoute 브랜치다(app_router.dart) — 그래야 새로고침(브라우저 하드 리로드)
/// 해도 마지막으로 보던 탭이 URL 그대로 유지된다. 이전에는 탭 인덱스가 순수 앱 상태라
/// 새로고침하면 항상 홈 탭으로 초기화됐다.
/// "AI 교정"은 탭이 아니라 촬영(실전 모드) 풀스크린 플로우로의 진입 액션이다.
class MainShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  const MainShell({super.key, required this.navigationShell});

  /// StatefulNavigationShell의 브랜치 인덱스(0: 홈, 1: 분석, 2: 마이)
  /// → 하단 네비 인덱스(0: 홈, 1: AI 교정, 2: 분석, 3: 마이)
  int get _navBarIndex => switch (navigationShell.currentIndex) {
        1 => 2,
        2 => 3,
        _ => 0,
      };

  void _onTap(BuildContext context, int index) {
    if (index == 1) {
      // AI 교정: 촬영 화면으로 진입 (탭 브랜치를 바꾸지 않음)
      context.push('/image-capture');
      return;
    }
    final branchIndex = switch (index) {
      2 => 1,
      3 => 2,
      _ => 0,
    };
    navigationShell.goBranch(
      branchIndex,
      // 이미 그 탭이면 해당 탭의 첫 화면으로 되돌아간다(표준 bottom-nav 관례).
      initialLocation: branchIndex == navigationShell.currentIndex,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: AppTheme.line)),
        ),
        child: BottomNavigationBar(
          currentIndex: _navBarIndex,
          onTap: (index) => _onTap(context, index),
          type: BottomNavigationBarType.fixed,
          backgroundColor: Colors.white,
          selectedItemColor: AppTheme.primaryColor,
          unselectedItemColor: AppTheme.inkFaint,
          selectedFontSize: 11,
          unselectedFontSize: 11,
          showUnselectedLabels: true,
          elevation: 0,
          items: const [
            BottomNavigationBarItem(
                icon: Icon(Icons.home_rounded), label: '홈'),
            BottomNavigationBarItem(
                icon: Icon(Icons.camera_alt_rounded), label: 'AI 교정'),
            BottomNavigationBarItem(
                icon: Icon(Icons.insights_rounded), label: '분석'),
            BottomNavigationBarItem(
                icon: Icon(Icons.person_rounded), label: '마이'),
          ],
        ),
      ),
    );
  }
}
