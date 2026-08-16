import 'package:flutter/material.dart';

/// 연한 글씨 보존 모드로 처리된 사진에 붙는 안내 (DATA_FLOW.md §5-10).
///
/// 연필처럼 연하게 쓴 사진은 비침(종이 뒷면 글씨)을 지우려 하면 진짜 획까지 같이
/// 지워진다. 그래서 서버가 "흐린 것도 살리는" 쪽(gentle_stretch)을 택하는데,
/// 그 대가로 비친 자국이 글자로 잡혀 오버레이에 네모가 쳐지고 점수에도 섞인다.
///
/// 사용자가 **이유를 모른 채** "점수가 왜 이상하지" 하는 상황을 막는 게 목적이다.
/// 그래서 문구에 원인·영향·대처를 각각 한 문장씩 담았다 — 원인을 안 밝히고
/// "다시 촬영하세요"만 하면 같은 종이로 또 찍게 된다.
///
/// ⚠️ **실제로 걸러내지는 않는다**(팀 결정 2026-08-12). 비침과 연한 진짜 획은
/// 진하기로 구분이 안 되고(`ai/preprocessing/image_preprocessor.py` 실측 결론),
/// 걸러내려면 탐지 확률값이 필요한데 지금 파이프라인엔 그 값이 오지 않는다
/// (DEVLOG 17막 — 확률이 전부 0.5 상수로 채워짐).
///
/// 상태를 갖지 않는다. 표시 여부 판단은 호출부(FeedbackScreen)가 한다.
class PreservationNotice extends StatelessWidget {
  /// 테스트가 존재 여부를 잡을 수 있는 키.
  static const noticeKey = Key('feedback_preservation_notice');

  const PreservationNotice({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      key: noticeKey,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF6E5),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFF0D9A8)),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 18, color: Color(0xFF9A6B08)),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              '연하게 쓴 글씨라 흐린 부분까지 살려서 분석했어요. '
              '종이 뒷면 글씨가 비쳐 보이면 글자로 잘못 잡힐 수 있으니, '
              '결과가 이상하면 더 진한 펜으로 쓰거나 두꺼운 종이에 써보세요.',
              style: TextStyle(
                  fontSize: 12.5, height: 1.5, color: Color(0xFF6B4E08)),
            ),
          ),
        ],
      ),
    );
  }
}
