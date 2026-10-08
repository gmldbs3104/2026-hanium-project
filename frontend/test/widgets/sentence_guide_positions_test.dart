import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/canvas_mode/widgets/stroke_painter.dart';
import 'package:frontend/features/practice/screens/sentence_practice_screen.dart';

/// 서버로 보내는 글자 자리(char_positions)가 화면의 회색 가이드 글씨와 같은
/// 곳을 가리키는지 확인한다. 서버가 이 자리로 획을 글자에 배정하므로, 어긋나면
/// 가이드를 정확히 따라 써도 "채점 불가"가 된다.
const _sentence = '시원한 선풍기';
const _padding = EdgeInsets.symmetric(horizontal: 16, vertical: 18);
const _maxLineHeight = 150.0;

Future<({Rect guide, Rect canvas, List<Map<String, dynamic>> positions})>
    _pumpAndMeasure(WidgetTester tester, Size screen) async {
  tester.view.physicalSize = screen;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(const MaterialApp(home: SentencePracticeScreen()));

  final guideFinder = find.text(_sentence);
  final canvasFinder = find.byWidgetPredicate(
    (w) => w is CustomPaint && w.painter is StrokePainter,
  );
  expect(guideFinder, findsOneWidget);
  expect(canvasFinder, findsOneWidget);

  final canvas = tester.getRect(canvasFinder);
  final element = tester.element(guideFinder);
  final positions = sentenceGuideCharPositions(
    sentence: _sentence,
    style: DefaultTextStyle.of(element)
        .style
        .merge(tester.widget<Text>(guideFinder).style),
    textScaler: MediaQuery.textScalerOf(element),
    canvasSize: canvas.size,
    padding: _padding,
    maxLineHeight: _maxLineHeight,
  );
  return (
    // 캔버스 좌표계(획 좌표와 같은 기준)로 옮긴 가이드 글씨의 실제 자리
    guide: tester.getRect(guideFinder).shift(-canvas.topLeft),
    canvas: canvas,
    positions: positions,
  );
}

void _expectPositionsOnGuide(
    Rect guide, List<Map<String, dynamic>> positions) {
  expect(positions.length, _sentence.replaceAll(' ', '').length);
  final first = positions.first;
  final last = positions.last;
  expect(first['x'] as double, closeTo(guide.left, 0.5));
  expect((last['x'] as double) + (last['width'] as double),
      closeTo(guide.right, 0.5));
  // 글자 상자는 줄 전체가 아니라 글리프 높이라(줄 높이의 여백이 빠진다) 세로는
  // 가이드 줄 안에 들어 있는지만 본다. 배율이 어긋나면 위 가로 검사가 잡는다.
  for (final p in positions) {
    final top = p['y'] as double;
    final bottom = top + (p['height'] as double);
    expect(top, greaterThanOrEqualTo(guide.top - 0.5));
    expect(bottom, lessThanOrEqualTo(guide.bottom + 0.5));
    expect(bottom - top, greaterThan(guide.height * 0.5));
  }
}

void main() {
  testWidgets('넓은 화면: 가이드가 상한까지만 커지고 글자 자리가 그 위에 놓인다', (tester) async {
    final m = await _pumpAndMeasure(tester, const Size(1300, 900));

    // 상한이 실제로 걸리는 크기인지 — 폭을 가득 채우지 않고 줄 높이가 상한이다.
    expect(m.guide.height, closeTo(_maxLineHeight, 0.5));
    expect(m.guide.width, lessThan(m.canvas.width - _padding.horizontal - 1));
    _expectPositionsOnGuide(m.guide, m.positions);
  });

  testWidgets('좁은 화면: 가이드가 폭에 맞춰지고 글자 자리가 그 위에 놓인다', (tester) async {
    final m = await _pumpAndMeasure(tester, const Size(400, 800));

    expect(m.guide.width,
        closeTo(m.canvas.width - _padding.horizontal, 0.5));
    expect(m.guide.height, lessThan(_maxLineHeight));
    _expectPositionsOnGuide(m.guide, m.positions);
  });
}
