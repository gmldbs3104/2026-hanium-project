import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/app_theme.dart';
import '../analysis/screens/analysis_screen.dart';
import '../home/screens/home_screen.dart';
import '../mypage/screens/mypage_screen.dart';

/// 하단 네비게이션을 가진 메인 셸 (홈 · AI 교정 · 분석 · 마이)
///
/// 홈/분석/마이는 셸 내부 탭으로 상태를 유지하고,
/// "AI 교정"은 촬영(실전 모드) 풀스크린 플로우로 진입한다.
class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = 0; // 0: 홈, 1: AI 교정(액션), 2: 분석, 3: 마이

  /// 하단 네비 인덱스 → IndexedStack의 body 인덱스 (AI 교정 제외)
  int get _bodyIndex => switch (_currentIndex) {
        2 => 1,
        3 => 2,
        _ => 0,
      };

  void _onTap(int index) {
    if (index == 1) {
      // AI 교정: 촬영 화면으로 진입 (탭 선택은 바꾸지 않음)
      context.push('/image-capture');
      return;
    }
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _bodyIndex,
        children: const [
          HomeScreen(),
          AnalysisScreen(),
          MyPageScreen(),
        ],
      ),
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: AppTheme.line)),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: _onTap,
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
