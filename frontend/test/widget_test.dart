// 기본 Flutter 프로젝트 생성 시 만들어지는 카운터 앱 템플릿 테스트가 그대로 남아있어서
// (MyApp이라는 클래스는 이 프로젝트에 없음 → 실제 앱 위젯인 HandwritingApp으로 교체) 발생한 오류.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('앱이 정상적으로 시작되고 로그인 화면이 보인다', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: HandwritingApp()));

    // mock 로그인 모드 안내 문구로 로그인 화면이 뜨는지 확인
    expect(find.textContaining('mock 로그인 모드'), findsOneWidget);
  });
}
