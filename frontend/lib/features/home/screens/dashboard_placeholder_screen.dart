import 'package:flutter/material.dart';

/// 학습 관리 대시보드 (SFR-008)
/// 오늘 작업 범위에는 포함되지 않으나, 메인 화면에서의 라우팅 연결을 위해
/// 자리만 잡아둔 placeholder 화면입니다.
class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('학습 대시보드')),
      body: const Center(
        child: Text(
          '대시보드는 다음 작업에서 구현될 예정입니다.\n(SFR-008)',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey),
        ),
      ),
    );
  }
}
