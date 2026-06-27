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
          'score': result.overallScore,
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
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _isSubmitting ? null : () => _submit(_canvasSize),
        icon: _isSubmitting
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
              )
            : const Icon(Icons.check_rounded),
        label: Text(_isSubmitting ? '분석 중...' : '분석하기'),
      ),
    );
  }
}
