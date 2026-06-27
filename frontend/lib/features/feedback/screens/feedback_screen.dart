import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// 교정 피드백 화면 (SFR-007 대응 - 오늘 작업 범위에서는 단순 결과 표시까지)
///
/// REQ-007-2: 캔버스 모드와 이미지 모드의 렌더링 로직은 분리되어야 함
/// → 이 화면에서 mode 값에 따라 분기 처리 (추후 오버레이 렌더링은 별도로 확장)
class FeedbackScreen extends StatelessWidget {
  final String mode; // 'canvas' | 'image'
  final String sessionId;
  final int score;

  const FeedbackScreen({
    super.key,
    required this.mode,
    required this.sessionId,
    required this.score,
  });

  @override
  Widget build(BuildContext context) {
    final isCanvas = mode == 'canvas';

    return Scaffold(
      appBar: AppBar(title: const Text('분석 결과')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                isCanvas ? Icons.draw_rounded : Icons.camera_alt_rounded,
                size: 56,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: 16),
              Text(
                isCanvas ? '글씨 연습 결과' : '실전 모드 결과',
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 24),
              Text(
                '$score',
                style: TextStyle(
                  fontSize: 56,
                  fontWeight: FontWeight.bold,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const Text('종합 점수', style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 24),
              Text(
                'session_id: $sessionId',
                style: const TextStyle(fontSize: 11, color: Colors.grey),
              ),
              const SizedBox(height: 32),
              Text(
                '※ 오늘 작업 범위는 API 연결까지입니다.\n실제 교정 오버레이(SFR-007) UI는 추후 작업에서 구현합니다.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
              ),
              const SizedBox(height: 24),
              OutlinedButton(
                onPressed: () => context.go('/home'),
                child: const Text('메인으로 돌아가기'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
