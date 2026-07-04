import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../canvas_mode/models/stroke.dart';
import '../../canvas_mode/services/canvas_api_service.dart';
import '../../canvas_mode/widgets/stroke_painter.dart';
import '../../image_mode/services/image_api_service.dart';
import '../models/canvas_correction_overlay_item.dart';
import '../models/image_bbox_overlay_item.dart';
import '../models/pending_session_save.dart';
import '../services/session_save_queue.dart';
import '../widgets/canvas_correction_overlay_view.dart';
import '../widgets/image_bbox_overlay_view.dart';

/// 교정 피드백 화면 (SFR-007 + SFR-009 저장 확인)
///
/// REQ-007-2: 캔버스 모드와 이미지 모드의 렌더링 로직은 분리되어야 함
/// → mode 값에 따라 완전히 다른 오버레이 위젯(CanvasCorrectionOverlayView /
///   ImageBBoxOverlayView)을 사용한다.
///
/// ⚠️ score/achievement_message는 여기서 API로 직접 받아옵니다.
/// analyze()/preprocess() 단계 응답에는 원래 점수가 없습니다 (백엔드 스키마 참고).
/// 반드시 GET /{canvas|image}/{id}/feedback 응답에서만 점수를 받습니다.
///
/// SFR-009: 하단 "확인" 버튼을 탭하면 저장을 트리거한다 (requirement.md
/// SFR-007 Post-condition: "사용자가 피드백을 확인하면 SFR-009가 트리거된다").
/// 저장 요청이 네트워크 문제로 실패하면 로컬 큐에 쌓아두고, 다음에 이 화면을
/// 열 때(또는 "지금 재시도")마다 자동으로 다시 시도한다 (REQ-009-5).
class FeedbackScreen extends StatefulWidget {
  final String mode; // 'canvas' | 'image'
  final String sessionId;

  // 캔버스 모드 오버레이용 (mode == 'canvas'일 때 필수)
  // 서버에 PNG를 보내지 않으므로(REQ-003C-6) 배경을 이 데이터로 다시 그린다.
  final List<Stroke>? strokes;
  final CanvasMetadata? canvasMetadata;

  // 이미지 모드 오버레이용 (mode == 'image'일 때 필수)
  final List<int>? imageBytes;
  final int? imageWidth;
  final int? imageHeight;

  const FeedbackScreen({
    super.key,
    required this.mode,
    required this.sessionId,
    this.strokes,
    this.canvasMetadata,
    this.imageBytes,
    this.imageWidth,
    this.imageHeight,
  });

  @override
  State<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends State<FeedbackScreen> {
  bool _isLoading = true;
  String? _errorMessage;

  // /feedback 응답에서만 받아오는 진짜 결과 (score, 메시지)
  int? _overallScore;
  String? _achievementMessage;

  // 캔버스 모드 오버레이 항목
  List<CanvasCorrectionOverlayItem> _canvasItems = [];

  // 이미지 모드 오버레이 항목
  List<ImageBBoxOverlayItem> _imageItems = [];

  bool _showOverlay = true;

  // ---- SFR-009 저장 확인 관련 상태 ----
  bool _saveImageConsent = false; // REQ-009-4: 이미지 모드에서만 의미 있음, 기본 미동의
  bool _isConfirming = false;
  bool _confirmed = false;
  int _pendingQueueCount = 0;

  @override
  void initState() {
    super.initState();
    _loadFeedback();
    _flushPendingQueueOnOpen();
  }

  bool get _isCanvas => widget.mode == 'canvas';

  Future<void> _loadFeedback() async {
    try {
      if (_isCanvas) {
        await _loadCanvasFeedback();
      } else {
        await _loadImageFeedback();
      }
    } catch (e) {
      setState(() => _errorMessage = '피드백을 불러오지 못했습니다. 다시 시도해주세요.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _loadCanvasFeedback() async {
    // SFR-004C: 문자 단위 bounding box
    final groupResponse = await CanvasApiService.group(widget.sessionId);
    // SFR-007: 문자별 severity + 메시지 + 최종 종합 점수 (진짜 점수는 여기서만 나옴)
    final feedbackResponse = await CanvasApiService.feedback(widget.sessionId);

    setState(() {
      _canvasItems = CanvasCorrectionOverlayItem.merge(
        charGroups: groupResponse.charGroups,
        feedbackItems: feedbackResponse.feedbackItems,
      );
      _overallScore = feedbackResponse.overallScore;
      _achievementMessage = feedbackResponse.achievementMessage;
    });
  }

  Future<void> _loadImageFeedback() async {
    // SFR-004I: 문자 검출 bounding box
    final detectResponse = await ImageApiService.detect(widget.sessionId);
    // SFR-007: 피드백 (현재는 target_id="global"만 옴 — 문서 참고) + 최종 종합 점수
    final feedbackResponse = await ImageApiService.feedback(widget.sessionId);

    setState(() {
      _imageItems = ImageBBoxOverlayItem.merge(
        detectedChars: detectResponse.detectedChars,
        feedbackItems: feedbackResponse.feedbackItems,
      );
      _overallScore = feedbackResponse.overallScore;
      _achievementMessage = feedbackResponse.achievementMessage;
    });
  }

  /// REQ-009-5: 이 화면을 열 때마다 이전에 실패해서 쌓여있던 저장 요청을
  /// 조용히 재시도해본다 (연결이 이미 복구됐을 수도 있으므로).
  Future<void> _flushPendingQueueOnOpen() async {
    await SessionSaveQueue.flush();
    await _refreshPendingQueueCount();
  }

  Future<void> _refreshPendingQueueCount() async {
    final count = await SessionSaveQueue.pendingCount();
    if (mounted) setState(() => _pendingQueueCount = count);
  }

  Future<void> _retryPendingQueueNow() async {
    final succeeded = await SessionSaveQueue.flush();
    await _refreshPendingQueueCount();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(succeeded > 0 ? '$succeeded건 재전송에 성공했습니다.' : '아직 연결이 불안정한 것 같아요.')),
    );
  }

  /// SFR-009 저장 확인 (requirement.md SFR-007 Post-condition에서 트리거)
  Future<void> _onConfirm() async {
    setState(() => _isConfirming = true);

    try {
      if (_isCanvas) {
        await CanvasApiService.confirm(widget.sessionId);
      } else {
        await ImageApiService.confirm(widget.sessionId, saveImage: _saveImageConsent);
      }

      if (mounted) {
        setState(() => _confirmed = true);
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('학습 결과가 저장되었습니다.')));
      }
    } catch (e) {
      // REQ-009-5: 네트워크 문제로 저장이 실패하면 로컬 큐에 쌓아두고
      // 나중에(다음에 이 화면을 열 때, 또는 "지금 재시도") 자동으로 다시 시도한다.
      await SessionSaveQueue.enqueue(PendingSessionSave(
        mode: widget.mode,
        sessionId: widget.sessionId,
        saveImage: _saveImageConsent,
      ));
      await _refreshPendingQueueCount();

      if (mounted) {
        setState(() => _confirmed = true); // 큐에 넣어뒀으니 사용자 입장에서는 완료로 처리
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('오프라인 상태예요. 연결되면 자동으로 다시 저장할게요.')),
        );
      }
    } finally {
      if (mounted) setState(() => _isConfirming = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('분석 결과'),
        actions: [
          if (!_isLoading && _errorMessage == null)
            IconButton(
              tooltip: _showOverlay ? '오버레이 숨기기' : '오버레이 보이기',
              icon: Icon(_showOverlay ? Icons.visibility_rounded : Icons.visibility_off_rounded),
              onPressed: () => setState(() => _showOverlay = !_showOverlay),
            ),
        ],
      ),
      body: SafeArea(child: _buildBody(context)),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return _buildErrorState();
    }

    return Column(
      children: [
        if (_pendingQueueCount > 0) _buildPendingQueueBanner(),
        _buildScoreHeader(context),
        const Divider(height: 1),
        Expanded(child: _buildOverlayArea(context)),
        const Divider(height: 1),
        _buildConfirmSection(context),
      ],
    );
  }

  /// REQ-009-5: 재전송 대기 중인 이전 학습 기록이 있음을 알리는 배너
  Widget _buildPendingQueueBanner() {
    return Container(
      width: double.infinity,
      color: Colors.orange.shade50,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Icon(Icons.cloud_off_rounded, size: 16, color: Colors.orange.shade700),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '동기화 대기 중인 학습 기록이 $_pendingQueueCount건 있어요.',
              style: TextStyle(fontSize: 12, color: Colors.orange.shade800),
            ),
          ),
          TextButton(
            onPressed: _retryPendingQueueNow,
            child: const Text('지금 재시도', style: TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }

  Widget _buildScoreHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Icon(
                _isCanvas ? Icons.draw_rounded : Icons.camera_alt_rounded,
                size: 32,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(width: 8),
              Text(
                '${_overallScore ?? 0}',
                style: TextStyle(
                  fontSize: 40,
                  fontWeight: FontWeight.bold,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const Padding(
                padding: EdgeInsets.only(bottom: 8, left: 4),
                child: Text('점', style: TextStyle(color: Colors.grey)),
              ),
            ],
          ),
          if (_achievementMessage != null) ...[
            const SizedBox(height: 4),
            Text(
              _achievementMessage!,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13, color: Colors.grey),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildOverlayArea(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Container(
          color: Colors.grey.shade100,
          child: _isCanvas ? _buildCanvasOverlay() : _buildImageOverlay(),
        ),
      ),
    );
  }

  Widget _buildCanvasOverlay() {
    if (widget.strokes == null || widget.canvasMetadata == null) {
      return _buildMissingDataState('캔버스 획 데이터가 전달되지 않았습니다.');
    }

    final metadata = widget.canvasMetadata!;

    return CanvasCorrectionOverlayView(
      // ⚠️ 오버레이 박스는 CanvasCoordinateMapper가 원본 크기를 BoxFit.contain으로
      // 화면에 맞게 스케일링해서 그린다. 배경(StrokePainter)도 똑같은 스케일 기준을
      // 쓰지 않으면 획이 잘리거나 오버레이와 위치가 안 맞는다 — 그래서 원본 크기의
      // SizedBox로 감싼 뒤 FittedBox(contain)로 똑같이 축소한다.
      background: FittedBox(
        fit: BoxFit.contain,
        child: SizedBox(
          width: metadata.width,
          height: metadata.height,
          child: CustomPaint(
            painter: StrokePainter(strokes: widget.strokes!),
          ),
        ),
      ),
      sourceWidth: metadata.width,
      sourceHeight: metadata.height,
      items: _canvasItems,
      showOverlay: _showOverlay,
      onItemTap: (item) => _showFeedbackSheet(
        charId: item.charId,
        message: item.feedback?.feedbackMessage ?? '이 글자는 특별한 교정사항이 없습니다.',
      ),
    );
  }

  Widget _buildImageOverlay() {
    if (widget.imageBytes == null || widget.imageWidth == null || widget.imageHeight == null) {
      return _buildMissingDataState('촬영 이미지 데이터가 전달되지 않았습니다.');
    }

    return ImageBBoxOverlayView(
      image: Image.memory(
        Uint8List.fromList(widget.imageBytes!),
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) =>
            Container(color: Colors.grey.shade300), // mock 바이트(진짜 이미지가 아님)일 때 대비
      ),
      sourceWidth: widget.imageWidth!.toDouble(),
      sourceHeight: widget.imageHeight!.toDouble(),
      items: _imageItems,
      showOverlay: _showOverlay,
      onItemTap: (item) => _showFeedbackSheet(
        charId: item.charId,
        message: item.feedback?.feedbackMessage ?? '이 영역은 아직 문자 단위 피드백이 지원되지 않습니다.',
      ),
    );
  }

  Widget _buildMissingDataState(String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          message,
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
        ),
      ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, color: Colors.red.shade300, size: 40),
            const SizedBox(height: 8),
            Text(_errorMessage!, style: TextStyle(color: Colors.red.shade700)),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: () {
                setState(() {
                  _isLoading = true;
                  _errorMessage = null;
                });
                _loadFeedback();
              },
              child: const Text('다시 시도'),
            ),
          ],
        ),
      ),
    );
  }

  /// SFR-009: 하단 저장 확인 영역 (이미지 모드는 저장 동의 체크박스 포함, REQ-009-4)
  Widget _buildConfirmSection(BuildContext context) {
    if (_confirmed) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_rounded, color: Colors.green.shade600, size: 20),
            const SizedBox(width: 8),
            const Text('저장이 완료되었습니다.'),
            const SizedBox(width: 16),
            TextButton(
              onPressed: () => context.go('/home'),
              child: const Text('홈으로'),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          if (!_isCanvas)
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              dense: true,
              value: _saveImageConsent,
              onChanged: (v) => setState(() => _saveImageConsent = v ?? false),
              title: const Text('원본 이미지도 함께 저장하기', style: TextStyle(fontSize: 13)),
              subtitle: const Text(
                '동의하지 않으면 분석 결과만 저장되고, 촬영한 사진은 저장되지 않습니다.',
                style: TextStyle(fontSize: 11),
              ),
            ),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _isConfirming ? null : _onConfirm,
              child: _isConfirming
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('확인 (결과 저장)'),
            ),
          ),
        ],
      ),
    );
  }

  void _showFeedbackSheet({required String charId, required String message}) {
    showModalBottomSheet(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(charId, style: const TextStyle(fontSize: 12, color: Colors.grey)),
            const SizedBox(height: 8),
            Text(message, style: const TextStyle(fontSize: 15)),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}
