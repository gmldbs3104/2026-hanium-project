import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../../core/app_theme.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../../canvas_mode/models/stroke.dart';
import '../../canvas_mode/services/canvas_api_service.dart';
import '../../canvas_mode/widgets/stroke_painter.dart';

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

  static const _tabs = ['짧은 문장', '긴 문장', '캘리그라피'];
  static const _sentences = [
    '작은 실천이 큰 변화를 만든다',
    '천 리 길도 한 걸음부터 시작된다는 마음으로',
    '오늘도 좋은 하루 되세요',
  ];
  int _tabIndex = 0;
  String get _sentence => _sentences[_tabIndex];

  static const _uuid = Uuid();

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
        pressure: 1.0,
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
      final result =
          await CanvasApiService.analyze(strokes: _strokes, metadata: metadata);
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
        leading: const BackButton(),
        title: const Text('문장 쓰기'),
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            _SentenceTabBar(
                tabs: _tabs, index: _tabIndex, onSelect: _selectTab),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: AppTheme.mintSurface,
                  borderRadius: BorderRadius.circular(AppTheme.radiusSm),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('연습할 문장',
                        style: TextStyle(
                            fontSize: 11, color: AppTheme.inkMuted)),
                    const SizedBox(height: 4),
                    Text(_sentence,
                        style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.ink)),
                  ],
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
                      return Stack(
                        children: [
                          // 뒤: 따라쓰기 가이드 문장 (첫 줄 진하게, 이후 옅게)
                          Positioned.fill(
                            child: IgnorePointer(
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 16, vertical: 18),
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    Text(_sentence,
                                        style: const TextStyle(
                                            fontSize: 20,
                                            fontWeight: FontWeight.w600,
                                            color: AppTheme.ink)),
                                    const SizedBox(height: 20),
                                    for (var i = 0; i < 4; i++) ...[
                                      Text(_sentence,
                                          style: const TextStyle(
                                              fontSize: 20,
                                              fontWeight: FontWeight.w500,
                                              color: Color(0xFFD8DDE3))),
                                      const SizedBox(height: 20),
                                    ],
                                  ],
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
