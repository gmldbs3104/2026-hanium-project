import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('앱이 정상적으로 시작되고 로그인 화면이 보인다', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: HandwritingApp()));

    // mock 로그인 모드 안내 문구로 로그인 화면이 뜨는지 확인
    expect(find.textContaining('mock 로그인 모드'), findsOneWidget);
  });

  testWidgets('로그인 후 "글씨 연습"을 선택하면 캔버스 입력 화면으로 이동한다 (SFR-002 모드 분기)',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: HandwritingApp()));
    await tester.pumpAndSettle();

    // mock Google 로그인 트리거
    await tester.tap(find.text('Google로 로그인'));
    // AuthLoading 중에는 CircularProgressIndicator가 계속 애니메이션되므로
    // pumpAndSettle 대신 mock 지연(800ms)만큼 시간을 진행시킨다.
    await tester.pump(); // 로딩 프레임
    await tester.pump(const Duration(milliseconds: 900)); // mock 로그인 완료 → 홈 이동
    await tester.pumpAndSettle();

    // 홈 화면의 캔버스 모드 카드
    expect(find.text('글씨 연습'), findsOneWidget);
    await tester.tap(find.text('글씨 연습'));
    await tester.pumpAndSettle();

    // 캔버스 입력 화면 진입 확인 (하단 "분석하기" 버튼은 이 화면에만 있음)
    expect(find.text('분석하기'), findsOneWidget);
  });
}
