import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../../shared/services/api_client.dart';
import '../models/stroke.dart';
import '../services/canvas_api_service.dart';
import '../widgets/stroke_painter.dart';

/// 캔버스 손글씨 입력 화면 (SFR-003C 대응)
///
/// REQ-003C-1: 60fps 이상 샘플링 레이트 유지 (Flutter 기본 GestureDetector가 충족)
/// REQ-003C-2: 캔버스 스냅샷 PNG는 분석에 사용하지 않고 UI 오버레이 전용
/// REQ-003C-4: 한 획 지우기 및 전체 지우기 가능
/// REQ-003C-5: RepaintBoundary로 프레임 드롭 방지
/// REQ-003C-6: 이미지 모드 전처리 파이프라인을 거치지 않음 (별도 파일/서비스로 완전 분리됨)
///
/// SFR-003C Inputs 캔버스 설정: 선 굵기(가늘게/보통/굵게)와 격자 표시 여부를
/// 화면 내 인라인 컨트롤(하단 세그먼트 + AppBar 토글)로 조절한다.
class CanvasInputScreen extends StatefulWidget {
  const CanvasInputScreen({super.key});

  @override
  State<CanvasInputScreen> createState() => _CanvasInputScreenState();
}

class _CanvasInputScreenState extends State<CanvasInputScreen> {
  final List<Stroke> _strokes = [];
  Stroke? _currentStroke;
  bool _isSubmitting = false;
  String? _errorMessage;
  Size _canvasSize = Size.zero;

  // SFR-003C Inputs: 캔버스 설정 (선 굵기 프리셋, 격자 표시 여부)
  static const double _thinWidth = 2.0;
  static const double _mediumWidth = 4.0;
  static const double _thickWidth = 7.0;
  double _strokeWidth = _mediumWidth;
  bool _showGrid = false;

  static const _uuid = Uuid();

  void _onPanStart(DragStartDetails details) {
    setState(() {
      _currentStroke = Stroke(strokeId: _uuid.v4(), points: []);
      _addPoint(details.localPosition);
    });
  }

  void _onPanUpdate(DragUpdateDetails details) {
    setState(() => _addPoint(details.localPosition));
  }

  void _addPoint(Offset position) {
    _currentStroke?.points.add(
      StrokePoint(
        x: position.dx,
        y: position.dy,
        pressure: 1.0, // 압력 센서 미지원 기기 대비 기본값
        timestamp: DateTime.now().millisecondsSinceEpoch,
      ),
    );
  }

  void _onPanEnd(DragEndDetails details) {
    if (_currentStroke == null || _currentStroke!.points.isEmpty) return;
    setState(() {
      _strokes.add(_currentStroke!);
      _currentStroke = null;
    });
  }

  /// REQ-003C-4: 전체 지우기
  void _clearCanvas() {
    setState(() {
      _strokes.clear();
      _currentStroke = null;
    });
  }

  /// REQ-003C-4: 한 획 지우기 (가장 마지막 획 삭제)
  void _undoLastStroke() {
    if (_strokes.isEmpty) return;
    setState(() => _strokes.removeLast());
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

      final result = await CanvasApiService.analyze(
        strokes: _strokes,
        metadata: metadata,
      );

      if (mounted) {
        context.go('/feedback', extra: {
          'mode': 'canvas',
          'sessionId': result.canvasSessionId,
          // ⚠️ 점수/성취 메시지는 여기서 넘기지 않습니다.
          // analyze() 응답에는 원래 점수가 없고(백엔드 CanvasAnalyzeResponse 참고),
          // feedback_screen.dart가 GET /feedback을 직접 호출해서 진짜 점수를 받아옵니다.
          //
          // ── SFR-003C Action ③ 결정: PNG 스냅샷 대신 "재렌더링" 채택 ──
          // requirement 원문은 CustomPainter.toImage()로 스냅샷 PNG를 만들어 오버레이
          // 배경으로 쓰라고 되어 있으나, 서버로 PNG를 보내지 않는(REQ-003C-6) 이상
          // PNG 바이트를 메모리에 들고 다닐 이유가 없다. 대신 획 데이터 자체를 넘겨
          // feedback 화면에서 StrokePainter로 동일하게 다시 그린다(결과 동일, 메모리 절약).
          // → requirement Outputs·Post-condition 문구는 이 결정에 맞춰 갱신 필요(팀 합의).
          // 재렌더 배경이 실제 필기와 같은 굵기로 보이도록 strokeWidth도 함께 전달한다.
          'strokes': List<Stroke>.from(_strokes),
          'canvasMetadata': metadata,
          'strokeWidth': _strokeWidth,
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
      appBar: AppBar(
        title: const Text('글씨 연습'),
        actions: [
          IconButton(
            icon: Icon(_showGrid ? Icons.grid_on_rounded : Icons.grid_off_rounded),
            tooltip: _showGrid ? '격자 끄기' : '격자 켜기',
            onPressed: () => setState(() => _showGrid = !_showGrid),
          ),
          IconButton(
            icon: const Icon(Icons.undo_rounded),
            tooltip: '한 획 지우기',
            onPressed: _strokes.isEmpty ? null : _undoLastStroke,
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline_rounded),
            tooltip: '전체 지우기',
            onPressed: _strokes.isEmpty ? null : _clearCanvas,
          ),
        ],
      ),
      body: Column(
        children: [
          if (_errorMessage != null)
            Container(
              width: double.infinity,
              color: Colors.red.shade50,
              padding: const EdgeInsets.all(12),
              child: Text(
                _errorMessage!,
                style: TextStyle(color: Colors.red.shade700, fontSize: 13),
              ),
            ),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                // 분석 요청 시 캔버스 메타데이터(width, height)로 사용할 크기를 보관
                _canvasSize = Size(constraints.maxWidth, constraints.maxHeight);

                return RepaintBoundary( // REQ-003C-5: 프레임 드롭 방지
                  child: GestureDetector(
                    onPanStart: _onPanStart,
                    onPanUpdate: _onPanUpdate,
                    onPanEnd: _onPanEnd,
                    child: Container(
                      width: double.infinity,
                      height: double.infinity,
                      color: Colors.white,
                      child: CustomPaint(
                        painter: StrokePainter(
                          strokes: _strokes,
                          currentStroke: _currentStroke,
                          strokeWidth: _strokeWidth, // SFR-003C Inputs: 선 굵기
                          showGrid: _showGrid,       // SFR-003C Inputs: 격자 표시
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          _buildBottomControls(),
        ],
      ),
    );
  }

  /// SFR-003C Inputs: 하단 인라인 컨트롤 — 선 굵기 세그먼트 + 분석하기 버튼
  Widget _buildBottomControls() {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
        child: Row(
          children: [
            Expanded(
              child: SegmentedButton<double>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: _thinWidth, label: Text('가늘게')),
                  ButtonSegment(value: _mediumWidth, label: Text('보통')),
                  ButtonSegment(value: _thickWidth, label: Text('굵게')),
                ],
                selected: {_strokeWidth},
                onSelectionChanged: (selection) =>
                    setState(() => _strokeWidth = selection.first),
              ),
            ),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: _isSubmitting ? null : () => _submit(_canvasSize),
              child: _isSubmitting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('분석하기'),
            ),
          ],
        ),
      ),
    );
  }
}
