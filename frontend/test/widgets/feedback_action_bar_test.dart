import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/feedback/widgets/feedback_action_bar.dart';

/// 위젯을 단독으로 세우는 래퍼 — API mock이나 라우터가 필요 없다.
/// 기본값은 "이미지 모드 / 저장 전 / 아무것도 진행 중이 아님".
Widget _wrap({
  bool isCanvas = false,
  bool confirmed = false,
  bool isConfirming = false,
  bool isDownloading = false,
  bool saveImageConsent = false,
  ValueChanged<bool>? onConsentChanged,
  VoidCallback? onConfirm,
  VoidCallback? onDownload,
  VoidCallback? onGoHome,
}) {
  return MaterialApp(
    home: Scaffold(
      body: FeedbackActionBar(
        isCanvas: isCanvas,
        confirmed: confirmed,
        isConfirming: isConfirming,
        isDownloading: isDownloading,
        saveImageConsent: saveImageConsent,
        onConsentChanged: onConsentChanged ?? (_) {},
        onConfirm: onConfirm ?? () {},
        onDownload: onDownload ?? () {},
        onGoHome: onGoHome ?? () {},
      ),
    ),
  );
}

void main() {
  testWidgets('캔버스 모드에는 원본 사진 보관 체크박스가 없다', (tester) async {
    await tester.pumpWidget(_wrap(isCanvas: true));

    expect(find.byKey(FeedbackActionBar.consentCheckboxKey), findsNothing);
  });

  testWidgets('이미지 모드에는 체크박스가 있고, 켜면 onConsentChanged(true)가 호출된다', (tester) async {
    bool? received;
    await tester.pumpWidget(_wrap(onConsentChanged: (v) => received = v));

    expect(find.text('촬영한 원본 사진도 서버에 보관'), findsOneWidget);
    expect(find.text('체크하지 않으면 분석 결과만 저장되고, 사진은 서버에 남지 않아요.'), findsOneWidget);

    await tester.tap(find.byKey(FeedbackActionBar.consentCheckboxKey));
    expect(received, isTrue);
  });

  testWidgets('저장 전에는 "이미지 받기"와 "학습 기록 저장"이 함께 보인다', (tester) async {
    await tester.pumpWidget(_wrap());

    expect(find.text('이미지 받기'), findsOneWidget);
    expect(find.text('학습 기록 저장'), findsOneWidget);
  });

  testWidgets('저장 후에는 완료 문구와 "이미지 받기"·"홈으로"만 남는다', (tester) async {
    await tester.pumpWidget(_wrap(confirmed: true));

    expect(find.text('학습 기록을 저장했어요.'), findsOneWidget);
    expect(find.text('이미지 받기'), findsOneWidget);
    expect(find.text('홈으로'), findsOneWidget);
    // 저장이 끝났으므로 저장 버튼과 동의 체크박스는 사라진다
    expect(find.text('학습 기록 저장'), findsNothing);
    expect(find.byKey(FeedbackActionBar.consentCheckboxKey), findsNothing);
  });

  testWidgets('저장 중에는 저장 버튼만 비활성이고 받기 버튼은 누를 수 있다', (tester) async {
    await tester.pumpWidget(_wrap(isConfirming: true));

    final save = tester.widget<ButtonStyleButton>(
      find.byKey(FeedbackActionBar.saveButtonKey),
    );
    final download = tester.widget<ButtonStyleButton>(
      find.byKey(FeedbackActionBar.downloadButtonKey),
    );

    expect(save.onPressed, isNull);
    expect(download.onPressed, isNotNull);
  });

  testWidgets('다운로드 중에는 받기 버튼만 비활성이고 저장 버튼은 누를 수 있다', (tester) async {
    await tester.pumpWidget(_wrap(isDownloading: true));

    final save = tester.widget<ButtonStyleButton>(
      find.byKey(FeedbackActionBar.saveButtonKey),
    );
    final download = tester.widget<ButtonStyleButton>(
      find.byKey(FeedbackActionBar.downloadButtonKey),
    );

    expect(save.onPressed, isNotNull);
    expect(download.onPressed, isNull);
  });

  testWidgets('저장 전 각 버튼 탭이 해당 콜백을 한 번씩 호출한다', (tester) async {
    var confirmCount = 0;
    var downloadCount = 0;
    await tester.pumpWidget(_wrap(
      onConfirm: () => confirmCount++,
      onDownload: () => downloadCount++,
    ));

    await tester.tap(find.byKey(FeedbackActionBar.saveButtonKey));
    await tester.tap(find.byKey(FeedbackActionBar.downloadButtonKey));

    expect(confirmCount, 1);
    expect(downloadCount, 1);
  });

  testWidgets('저장 후 "홈으로" 탭이 onGoHome을 호출한다', (tester) async {
    var homeCount = 0;
    await tester.pumpWidget(_wrap(confirmed: true, onGoHome: () => homeCount++));

    await tester.tap(find.byKey(FeedbackActionBar.homeButtonKey));

    expect(homeCount, 1);
  });
}
