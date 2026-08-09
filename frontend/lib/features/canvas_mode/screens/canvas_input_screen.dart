import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../../core/app_theme.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../data/stroke_order_data.dart';
import '../models/stroke.dart';
import '../services/canvas_api_service.dart';
import '../widgets/stroke_order_painter.dart';
import '../widgets/stroke_painter.dart';

/// 손글씨(글자) 연습 화면 (SFR-003C 대응) — UI 리디자인
///
/// 자음/모음/받침 탭 + 진행률 + 획순 가이드(번호·방향) + 색상/굵기/지우기/저장.
/// 저장 시 CanvasApiService.analyze()로 분석을 요청하고 결과는 피드백 화면에서 표시한다.
/// (백엔드 연동/파이프라인은 기존과 동일 — analyze → /feedback)
///
/// [initialTabIndex]/[initialCharIndex]: 결과 화면의 "다음 글자"에서 진입할 때
/// 특정 탭·글자에서 바로 시작하도록 전달받는다(없으면 처음부터).
class CanvasInputScreen extends StatefulWidget {
  final int? initialTabIndex;
  final int? initialCharIndex;

  const CanvasInputScreen({
    super.key,
    this.initialTabIndex,
    this.initialCharIndex,
  });

  @override
  State<CanvasInputScreen> createState() => _CanvasInputScreenState();
}

class _CanvasInputScreenState extends State<CanvasInputScreen> {
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

  // 자음/모음/받침 탭별 연습 글자 세트
  static const _tabs = ['자음 쓰기', '모음 쓰기', '받침 글자 쓰기'];
  static const _charSets = [
    ['ㄱ', 'ㄴ', 'ㄷ', 'ㄹ', 'ㅁ'],
    ['ㅏ', 'ㅑ', 'ㅓ', 'ㅕ', 'ㅗ'],
    ['각', '간', '달', '밤', '상'],
  ];
  int _tabIndex = 0;
  int _charIndex = 0;

  List<String> get _chars => _charSets[_tabIndex];
  String get _currentChar => _chars[_charIndex];

  static const _uuid = Uuid();

  @override
  void initState() {
    super.initState();
    // 결과 화면 "다음 글자"에서 넘어온 시작 위치 반영
    if (widget.initialTabIndex != null) {
      _tabIndex = widget.initialTabIndex!.clamp(0, _tabs.length - 1);
    }
    if (widget.initialCharIndex != null) {
      _charIndex = widget.initialCharIndex!.clamp(0, _charSets[_tabIndex].length - 1);
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

  void _clearCanvas() => setState(() {
        _strokes.clear();
        _currentStroke = null;
      });

  void _selectTab(int i) => setState(() {
        _tabIndex = i;
        _charIndex = 0;
        _clearStrokesOnly();
      });

  void _nextChar() => setState(() {
        _charIndex = (_charIndex + 1) % _chars.length;
        _clearStrokesOnly();
      });

  void _clearStrokesOnly() {
    _strokes.clear();
    _currentStroke = null;
  }

  Future<void> _submit(Size canvasSize) async {
    if (_strokes.isEmpty) {
      setState(() => _errorMessage = '먼저 글씨를 입력해주세요.');
      return;
    }
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    try {
      final metadata = CanvasMetadata(
        width: canvasSize.width,
        height: canvasSize.height,
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
          // 결과 화면 상단에 탭/진행률을 그대로 보여주기 위한 컨텍스트
          'practiceTabs': _tabs,
          'practiceTabIndex': _tabIndex,
          'practiceStep': _charIndex + 1,
          'practiceTotal': _chars.length,
          'practiceRoute': '/character-practice',
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
    final progress = (_charIndex + 1) / _chars.length;
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        leading: const BackButton(),
        title: const Text('손글씨 연습'),
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            _TabBar(tabs: _tabs, index: _tabIndex, onSelect: _selectTab),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Row(
                children: [
                  Text('진행률: ${_charIndex + 1}/${_chars.length}',
                      style: const TextStyle(
                          fontSize: 12, color: AppTheme.inkMuted)),
                  const Spacer(),
                  Text('${(progress * 100).round()}%',
                      style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.primaryDark)),
                  const SizedBox(width: 12),
                  GestureDetector(
                    onTap: _nextChar,
                    child: const Text('다음 글자 →',
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: AppTheme.inkMuted)),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 6,
                  backgroundColor: AppTheme.line,
                  valueColor:
                      const AlwaysStoppedAnimation(AppTheme.primaryColor),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: AppTheme.mintSurface,
                  borderRadius: BorderRadius.circular(AppTheme.radiusSm),
                ),
                child: Text(
                  "번호 순서와 화살표 방향대로 '$_currentChar' 글자를 써보세요",
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
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    _canvasSize =
                        Size(constraints.maxWidth, constraints.maxHeight);
                    return ClipRRect(
                      borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.white,
                          border: Border.all(color: AppTheme.line),
                          borderRadius:
                              BorderRadius.circular(AppTheme.radiusMd),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Stack(
                          children: [
                            // 뒤: 획순 가이드 (번호 + 방향 화살표). 점선/옅은 글자 대체.
                            Positioned.fill(
                              child: IgnorePointer(
                                child: CustomPaint(
                                  size: Size.infinite,
                                  painter: StrokeOrderGuidePainter(
                                      _currentChar, strokeOrderFor(_currentChar)),
                                ),
                              ),
                            ),
                            // 앞: 사용자의 필기 (투명 배경으로 가이드가 비쳐 보이도록)
                            Positioned.fill(
                              child: RepaintBoundary(
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
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
            _buildToolbar(),
          ],
        ),
      ),
    );
  }

  Widget _buildToolbar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 14),
      child: Row(
        children: [
          _ToolChip(
            icon: Icons.circle,
            iconColor: _penColor,
            label: '색상',
            onTap: () => setState(
                () => _colorIndex = (_colorIndex + 1) % _palette.length),
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
            onTap: _strokes.isEmpty ? null : _clearCanvas,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: MintButton(
              label: '저장',
              height: 48,
              loading: _isSubmitting,
              onPressed:
                  _isSubmitting ? null : () => _submit(_canvasSize),
            ),
          ),
        ],
      ),
    );
  }
}

class _TabBar extends StatelessWidget {
  final List<String> tabs;
  final int index;
  final ValueChanged<int> onSelect;
  const _TabBar(
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
                    color: selected ? AppTheme.primaryDark : AppTheme.inkFaint,
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
