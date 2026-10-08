import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../../core/app_theme.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../../canvas_mode/models/stroke.dart';
import '../../canvas_mode/services/canvas_api_service.dart';
import '../../canvas_mode/widgets/stroke_painter.dart';

/// 배경 가이드 문장에서 글자별 렌더링 위치(캔버스 기준 실제 좌표)를 계산한다.
///
/// 서버가 이 자리로 획을 글자에 배정하고 위치를 채점하므로, 화면에 그려진 회색
/// 글씨와 정확히 같아야 한다. 화면은 폭 가득·높이 [maxLineHeight]까지인 상자에
/// FittedBox(contain, 가운데 정렬)로 그리므로 배율은 가로·세로 중 더 빡빡한
/// 쪽이고, [style]·[textScaler]는 가이드 Text가 실제로 쓰는 값이어야 한다.
@visibleForTesting
List<Map<String, dynamic>> sentenceGuideCharPositions({
  required String sentence,
  required TextStyle style,
  required TextScaler textScaler,
  required Size canvasSize,
  required EdgeInsets padding,
  required double maxLineHeight,
}) {
  // 문장 전체를 한 번(줄바꿈 없이) 레이아웃해 원본 크기를 얻는다.
  final painter = TextPainter(
    text: TextSpan(text: sentence, style: style),
    textDirection: TextDirection.ltr,
    textScaler: textScaler,
  )..layout();

  final availableWidth = canvasSize.width - padding.horizontal;
  final availableHeight = canvasSize.height - padding.vertical;
  var scale = 1.0;
  if (availableWidth > 0 &&
      availableHeight > 0 &&
      painter.width > 0 &&
      painter.height > 0) {
    scale = math.min(
      availableWidth / painter.width,
      math.min(availableHeight, maxLineHeight) / painter.height,
    );
  }
  final offsetX = padding.left + (availableWidth - painter.width * scale) / 2;
  final offsetY = padding.top + (availableHeight - painter.height * scale) / 2;

  final positions = <Map<String, dynamic>>[];
  for (var i = 0; i < sentence.length; i++) {
    if (sentence[i] == ' ') continue;
    final boxes = painter.getBoxesForSelection(
      TextSelection(baseOffset: i, extentOffset: i + 1),
    );
    if (boxes.isEmpty) continue;
    final box = boxes.first;
    positions.add({
      'char': sentence[i],
      'index': i,
      'x': offsetX + box.left * scale,
      'y': offsetY + box.top * scale,
      'width': (box.right - box.left) * scale,
      'height': (box.bottom - box.top) * scale,
    });
  }
  painter.dispose();
  return positions;
}

/// 문장 쓰기 화면
///
/// 짧은/긴/캘리그라피 탭 + 따라쓰기 가이드 문장 + 필기 캔버스.
/// 저장 시 캔버스 모드 분석(CanvasApiService.analyze)을 그대로 사용한다(백엔드 연동 유지).
class SentencePracticeScreen extends StatefulWidget {
  /// 결과 화면 탭에서 특정 문장 탭으로 진입할 때 전달(없으면 첫 탭).
  final int? initialTabIndex;

  const SentencePracticeScreen({super.key, this.initialTabIndex});

  @override
  State<SentencePracticeScreen> createState() => _SentencePracticeScreenState();
}

class _SentencePracticeScreenState extends State<SentencePracticeScreen> {
  final List<Stroke> _strokes = [];
  Stroke? _currentStroke;
  bool _isSubmitting = false;
  String? _errorMessage;
  Size _canvasSize = Size.zero;

  static const double _thinWidth = 2.0;
  static const double _mediumWidth = 4.0;
  static const double _thickWidth = 7.0;
  double _strokeWidth = _mediumWidth;

  static const _palette = [
    Colors.black87,
    AppTheme.primaryColor,
    Color(0xFF3B82F6),
    Color(0xFFEF4444),
  ];
  int _colorIndex = 0;
  Color get _penColor => _palette[_colorIndex];

  static const _tabs = ['짧은 문장', '긴 문장'];
  // "짧은 문장" 탭은 완전한 문장이 아니라 형용사+명사 두 단어가 합쳐진 구(句)를
  // 보여준다(예: '시원한 선풍기') — 짧게 따라 쓰기 좋은 단위로 시작하기 위함.
  static const _sentences = [
    '시원한 선풍기',
    '천 리 길도 한 걸음부터 시작된다는 마음으로',
  ];
  int _tabIndex = 0;
  String get _sentence => _sentences[_tabIndex];

  static const _uuid = Uuid();

  // 배경 가이드 문구(딱 한 줄, FittedBox로 확대)와 반드시 같은 값이어야 좌표가
  // 실제 렌더링 위치와 일치한다 — fontSize 자체는 FittedBox가 다시 스케일하므로
  // 무관하고, 패딩/텍스트 스타일(폰트 굵기 등)만 일치하면 된다.
  static const _guidePadding = EdgeInsets.symmetric(horizontal: 16, vertical: 18);
  static const _guideStyle =
      TextStyle(fontSize: 48, fontWeight: FontWeight.w700, color: Color(0xFFC9CFD8));

  /// 가이드 한 줄이 커질 수 있는 한계 (논리 픽셀). 짧은 문장이 캔버스를 가득 채우며
  /// 지나치게 커지는 것을 막는다(사용자 요청 2026-09-17).
  /// FittedBox는 남는 공간만큼 계속 확대하므로, 4글자짜리 예문은 글자 하나가
  /// 캔버스 폭의 1/4을 차지할 만큼 커졌다.
  static const _maxGuideGlyph = 150.0;

  // 가이드 Text가 실제로 쓰는 스타일·글자 배율 — build에서 Text와 같은 자리의
  // context로 잡아 둔다. 테마가 얹는 줄 높이·자간을 빼고 재면 좌표가 화면과 어긋난다.
  TextStyle _guideEffectiveStyle = _guideStyle;
  TextScaler _guideTextScaler = TextScaler.noScaling;

  List<Map<String, dynamic>> _computeCharPositions() => sentenceGuideCharPositions(
        sentence: _sentence,
        style: _guideEffectiveStyle,
        textScaler: _guideTextScaler,
        canvasSize: _canvasSize,
        padding: _guidePadding,
        maxLineHeight: _maxGuideGlyph,
      );

  @override
  void initState() {
    super.initState();
    if (widget.initialTabIndex != null) {
      _tabIndex = widget.initialTabIndex!.clamp(0, _tabs.length - 1);
    }
  }

  void _onPanStart(DragStartDetails d) {
    setState(() {
      _currentStroke = Stroke(strokeId: _uuid.v4(), points: []);
      _addPoint(d.localPosition);
    });
  }

  void _onPanUpdate(DragUpdateDetails d) =>
      setState(() => _addPoint(d.localPosition));

  void _addPoint(Offset p) {
    _currentStroke?.points.add(
      StrokePoint(
        x: p.dx,
        y: p.dy,
        timestamp: DateTime.now().millisecondsSinceEpoch,
      ),
    );
  }

  void _onPanEnd(DragEndDetails d) {
    if (_currentStroke == null || _currentStroke!.points.isEmpty) return;
    setState(() {
      _strokes.add(_currentStroke!);
      _currentStroke = null;
    });
  }

  void _clear() => setState(() {
        _strokes.clear();
        _currentStroke = null;
      });

  void _selectTab(int i) => setState(() {
        _tabIndex = i;
        _clear();
      });

  Future<void> _submit() async {
    if (_strokes.isEmpty) {
      setState(() => _errorMessage = '먼저 문장을 따라 써주세요.');
      return;
    }
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    try {
      final metadata = CanvasMetadata(
        width: _canvasSize.width.round(),
        height: _canvasSize.height.round(),
        strokeCount: _strokes.length,
      );
      final result = await CanvasApiService.analyze(
        strokes: _strokes,
        metadata: metadata,
        targetText: _sentence.replaceAll(' ', ''),
        charPositions: _computeCharPositions(),
      );
      if (mounted) {
        context.go('/feedback', extra: {
          'mode': 'canvas',
          'sessionId': result.canvasSessionId,
          'strokes': List<Stroke>.from(_strokes),
          'canvasMetadata': metadata,
          'strokeWidth': _strokeWidth,
          // 결과 화면 상단에 탭을 그대로 보여주기 위한 컨텍스트
          // (문장 연습은 글자 단위 진행률이 없어 step/total은 넘기지 않는다)
          'practiceTabs': _tabs,
          'practiceTabIndex': _tabIndex,
          'practiceRoute': '/sentence-practice',
        });
      }
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        // canvas_input_screen.dart와 동일한 이유 — 항상 홈으로 명시적 이동(기록 미저장).
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/main'),
        ),
        title: const Text('문장 쓰기'),
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            _SentenceTabBar(
                tabs: _tabs, index: _tabIndex, onSelect: _selectTab),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: AppTheme.mintSurface,
                  borderRadius: BorderRadius.circular(AppTheme.radiusSm),
                ),
                child: Text(
                  "회색 글씨 위에 맞춰 따라 써보세요",
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppTheme.primaryDark),
                ),
              ),
            ),
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(_errorMessage!,
                    style: const TextStyle(
                        color: AppTheme.errorColor, fontSize: 12)),
              ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border: Border.all(color: AppTheme.line),
                    borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      _canvasSize =
                          Size(constraints.maxWidth, constraints.maxHeight);
                      _guideEffectiveStyle =
                          DefaultTextStyle.of(context).style.merge(_guideStyle);
                      _guideTextScaler = MediaQuery.textScalerOf(context);
                      return Stack(
                        children: [
                          // 뒤: 따라쓰기 가이드 문장 — 한 번만, 캔버스 폭에 맞게
                          // FittedBox로 확대하되 줄 높이는 _maxGuideGlyph까지만.
                          // ⚠️ 이 배치는 sentenceGuideCharPositions()의 공식과 짝이다.
                          // 한쪽만 바꾸면 서버가 받는 글자 자리가 회색 글씨와 어긋난다.
                          Positioned.fill(
                            child: IgnorePointer(
                              child: Padding(
                                padding: _guidePadding,
                                child: Center(
                                  child: SizedBox(
                                    width: double.infinity,
                                    height: _maxGuideGlyph,
                                    child: FittedBox(
                                      fit: BoxFit.contain,
                                      child:
                                          Text(_sentence, style: _guideStyle),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          // 앞: 필기 레이어 (투명 배경)
                          RepaintBoundary(
                            child: GestureDetector(
                              onPanStart: _onPanStart,
                              onPanUpdate: _onPanUpdate,
                              onPanEnd: _onPanEnd,
                              child: CustomPaint(
                                size: Size.infinite,
                                painter: StrokePainter(
                                  strokes: _strokes,
                                  currentStroke: _currentStroke,
                                  strokeWidth: _strokeWidth,
                                  penColor: _penColor,
                                  fillBackground: false,
                                ),
                              ),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 14),
              child: Row(
                children: [
                  _ToolChip(
                    icon: Icons.circle,
                    iconColor: _penColor,
                    label: '색상',
                    onTap: () => setState(() =>
                        _colorIndex = (_colorIndex + 1) % _palette.length),
                  ),
                  const SizedBox(width: 8),
                  _ToolChip(
                    icon: Icons.brush_rounded,
                    label: '굵기',
                    onTap: () => setState(() {
                      _strokeWidth = switch (_strokeWidth) {
                        _thinWidth => _mediumWidth,
                        _mediumWidth => _thickWidth,
                        _ => _thinWidth,
                      };
                    }),
                  ),
                  const SizedBox(width: 8),
                  _ToolChip(
                    icon: Icons.cleaning_services_rounded,
                    label: '지우기',
                    onTap: _strokes.isEmpty ? null : _clear,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: MintButton(
                      label: '저장',
                      height: 48,
                      loading: _isSubmitting,
                      onPressed: _isSubmitting ? null : _submit,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SentenceTabBar extends StatelessWidget {
  final List<String> tabs;
  final int index;
  final ValueChanged<int> onSelect;
  const _SentenceTabBar(
      {required this.tabs, required this.index, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.line)),
      ),
      child: Row(
        children: List.generate(tabs.length, (i) {
          final selected = i == index;
          return Expanded(
            child: InkWell(
              onTap: () => onSelect(i),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 14),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      color: selected
                          ? AppTheme.primaryColor
                          : Colors.transparent,
                      width: 2,
                    ),
                  ),
                ),
                child: Text(
                  tabs[i],
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight:
                        selected ? FontWeight.w700 : FontWeight.w500,
                    color:
                        selected ? AppTheme.primaryDark : AppTheme.inkFaint,
                  ),
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _ToolChip extends StatelessWidget {
  final IconData icon;
  final Color? iconColor;
  final String label;
  final VoidCallback? onTap;
  const _ToolChip(
      {required this.icon, required this.label, this.iconColor, this.onTap});

  @override
  Widget build(BuildContext context) {
    final disabled = onTap == null;
    return InkWell(
      borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppTheme.radiusSm),
          border: Border.all(color: AppTheme.line),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                size: 15,
                color: disabled
                    ? AppTheme.inkFaint
                    : (iconColor ?? AppTheme.inkMuted)),
            const SizedBox(width: 5),
            Text(label,
                style: TextStyle(
                    fontSize: 12,
                    color: disabled ? AppTheme.inkFaint : AppTheme.ink)),
          ],
        ),
      ),
    );
  }
}
