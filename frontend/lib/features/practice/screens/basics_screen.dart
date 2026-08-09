import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../shared/widgets/ui_kit.dart';

/// 손글씨 기초 — 바른 자세/필기구 쥐는 법 안내 (순수 안내 화면, 백엔드 없음)
class BasicsScreen extends StatelessWidget {
  const BasicsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    const grip = [
      '엄지와 검지로 연필을 자연스럽게 잡습니다',
      '중지는 받침대처럼 아래에서 지지합니다',
      '너무 꽉 쥐지 않고 편안하게 힘을 뺍니다',
      '연필은 60도 각도로 기울여 잡습니다',
    ];
    const posture = [
      '등을 곧게 펴고 의자 깊숙이 앉습니다',
      '팔꿈치와 무릎은 90도를 유지합니다',
      '책상과 눈의 거리는 30cm 정도 유지합니다',
      '발바닥 전체가 바닥에 닿도록 합니다',
    ];

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        leading: const BackButton(),
        title: const Text('손글씨 기초'),
        bottom: const PreferredSize(
          preferredSize: Size.fromHeight(20),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.only(left: 56, bottom: 8),
              child: Text('올바른 습관 만들기',
                  style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
            ),
          ),
        ),
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final wide = constraints.maxWidth >= 640;
                    final cards = [
                      const _GuideCard(
                        icon: Icons.back_hand_rounded,
                        title: '필기구 쥐는 법',
                        bullets: grip,
                      ),
                      const _GuideCard(
                        icon: Icons.event_seat_rounded,
                        title: '바른 자세 가이드',
                        bullets: posture,
                      ),
                    ];
                    return Column(
                      children: [
                        if (wide)
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(child: cards[0]),
                              const SizedBox(width: 16),
                              Expanded(child: cards[1]),
                            ],
                          )
                        else ...[
                          cards[0],
                          const SizedBox(height: 16),
                          cards[1],
                        ],
                        const SizedBox(height: 20),
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: AppTheme.mintSurface,
                            borderRadius:
                                BorderRadius.circular(AppTheme.radiusMd),
                          ),
                          child: const Text(
                            '💡 Tip: 올바른 습관은 처음엔 어색해도 꾸준히 연습하면 자연스러워집니다',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                                fontSize: 12.5,
                                height: 1.4,
                                color: AppTheme.primaryDark),
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
              child: MintButton(
                label: '다음 단계: 선 긋기 연습',
                onPressed: () => context.go('/character-practice'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GuideCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final List<String> bullets;
  const _GuideCard(
      {required this.icon, required this.title, required this.bullets});

  @override
  Widget build(BuildContext context) {
    return HaneumCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 20, color: AppTheme.primaryDark),
              const SizedBox(width: 8),
              Text(title,
                  style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
            ],
          ),
          const SizedBox(height: 12),
          AspectRatio(
            aspectRatio: 16 / 10,
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFFF0F2F5),
                borderRadius: BorderRadius.circular(AppTheme.radiusSm),
              ),
              child: const Center(
                child: Icon(Icons.image_rounded,
                    size: 36, color: AppTheme.inkFaint),
              ),
            ),
          ),
          const SizedBox(height: 12),
          ...bullets.map(
            (b) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 6, right: 8),
                    child: CircleAvatar(
                        radius: 2.5, backgroundColor: AppTheme.primaryColor),
                  ),
                  Expanded(
                    child: Text(b,
                        style: const TextStyle(
                            fontSize: 12.5,
                            height: 1.35,
                            color: AppTheme.ink)),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
