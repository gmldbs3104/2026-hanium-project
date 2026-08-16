import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/feedback/widgets/preservation_notice.dart';
import 'package:frontend/features/image_mode/models/image_result.dart';

/// 연한 글씨 보존 모드 안내 (DATA_FLOW.md §5-10)
///
/// 이 안내가 뜨려면 서버 응답(`preservation_mode`)이 화면까지 흘러야 한다.
/// 여기서는 그 흐름의 양 끝을 잡는다 — ① 응답 파싱 ② 실제 렌더링.
void main() {
  group('preservation_mode 파싱', () {
    test('true면 preservationMode가 true다', () {
      final r = ImagePreprocessResult.fromJson(const {
        'image_session_id': 's1',
        'width': 800,
        'height': 600,
        'preservation_mode': true,
      });
      expect(r.preservationMode, isTrue);
    });

    test('false면 false, 필드가 없으면 null이다 (구버전 서버 호환)', () {
      final off = ImagePreprocessResult.fromJson(const {
        'image_session_id': 's1',
        'width': 800,
        'height': 600,
        'preservation_mode': false,
      });
      final missing = ImagePreprocessResult.fromJson(const {
        'image_session_id': 's1',
        'width': 800,
        'height': 600,
      });
      expect(off.preservationMode, isFalse);
      expect(missing.preservationMode, isNull);
    });
  });

  group('PreservationNotice 렌더링', () {
    Future<void> pump(WidgetTester tester, {double width = 360}) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SizedBox(width: width, child: const PreservationNotice()),
        ),
      ));
    }

    testWidgets('안내 문구가 실제로 그려진다', (tester) async {
      await pump(tester);

      expect(find.byKey(PreservationNotice.noticeKey), findsOneWidget);
      // 원인 → 영향 → 대처가 모두 담겨야 한다. 원인을 빼고 "다시 찍으세요"만
      // 남기면 사용자가 같은 종이로 또 찍는다.
      expect(find.textContaining('연하게 쓴 글씨라'), findsOneWidget);
      expect(find.textContaining('글자로 잘못 잡힐 수 있으니'), findsOneWidget);
      expect(find.textContaining('두꺼운 종이'), findsOneWidget);
      expect(find.byIcon(Icons.info_outline), findsOneWidget);
    });

    testWidgets('좁은 폭에서도 넘치지 않는다 (문구가 길어 줄바꿈 필요)', (tester) async {
      // 오버플로는 pumpWidget 중 예외로 잡힌다. 폭 280은 소형 기기 가정.
      await pump(tester, width: 280);
      expect(tester.takeException(), isNull);
      expect(find.byKey(PreservationNotice.noticeKey), findsOneWidget);
    });
  });
}
