import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderRepaintBoundary;
import 'package:go_router/go_router.dart';

import '../../../shared/services/api_client.dart';
import '../utils/image_download.dart';
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
  // strokeWidth: 입력 화면에서 고른 선 굵기 — 재렌더 배경이 실제 필기와 같게 보이도록.
  final List<Stroke>? strokes;
  final CanvasMetadata? canvasMetadata;
  final double? strokeWidth;

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
    this.strokeWidth,
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

  // 경계 케이스 안내용 상태
  int _lowConfidenceCount = 0; // SFR-004C Side Effect: 저신뢰 문자 수 (canvas)
  int _detectedCount = 0;      // REQ-004I-5 / SFR-005I Side Effect: 탐지 문자 수 (image)

  // 오버레이(배경 + 교정 표시)를 PNG로 캡처해 다운로드하기 위한 키
  final GlobalKey _overlayCaptureKey = GlobalKey();
  bool _isDownloading = false;

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
      _lowConfidenceCount = groupResponse.lowConfidenceCount;
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
      _detectedCount = detectResponse.totalDetected;
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
    } on ApiException catch (e) {
      // REQ-009-5는 "네트워크 장애" 시에만 로컬 큐에 저장하도록 요구한다.
      // 연결 실패(statusCode == null)만 큐에 넣어 연결 복구 후 자동 재시도하고,
      // 서버가 응답한 4xx/5xx(statusCode != null)는 재시도해도 같은 이유로 실패하므로
      // 큐에 넣지 않고 즉시 실패로 안내한다 (무한 재시도 방지).
      if (e.statusCode == null) {
        await _enqueueForRetry();
      } else {
        _showSaveFailed('저장에 실패했습니다 (오류 ${e.statusCode}). 잠시 후 다시 시도해주세요.');
      }
    } catch (e) {
      // 예상치 못한 예외 — 네트워크 장애로 단정할 수 없으므로 큐에 넣지 않고 실패로 안내한다.
      debugPrint('[Feedback] confirm unexpected error: $e');
      _showSaveFailed('저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      if (mounted) setState(() => _isConfirming = false);
    }
  }

  /// REQ-009-5: 네트워크 장애 시 저장 요청을 로컬 큐에 넣고, 사용자에게는 완료로 안내한다
  /// (다음에 이 화면을 열 때 또는 "지금 재시도"로 자동 재전송되므로).
  Future<void> _enqueueForRetry() async {
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
  }

  /// 서버 오류 등 재시도 큐잉이 부적절한 실패 — 완료로 처리하지 않아 사용자가 다시 시도할 수 있게 둔다.
  void _showSaveFailed(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('분석 결과'),
        actions: [
          if (!_isLoading && _errorMessage == null) ...[
            IconButton(
              tooltip: '이미지 다운로드',
              icon: _isDownloading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.download_rounded),
              onPressed: _isDownloading ? null : _downloadFeedbackImage,
            ),
            IconButton(
              tooltip: _showOverlay ? '오버레이 숨기기' : '오버레이 보이기',
              icon: Icon(_showOverlay ? Icons.visibility_rounded : Icons.visibility_off_rounded),
              onPressed: () => setState(() => _showOverlay = !_showOverlay),
            ),
          ],
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
        ..._buildCaseNotices(),
        _buildScoreHeader(context),
        const Divider(height: 1),
        Expanded(child: _buildOverlayArea(context)),
        const Divider(height: 1),
        _buildConfirmSection(context),
      ],
    );
  }

  /// 저신뢰/경계 케이스 안내 배너들 (모드에 따라 필요한 것만 표시).
  ///  - 캔버스: 저신뢰 문자 존재 시 '일부 문자 인식 불확실' (SFR-004C Side Effect)
  ///  - 이미지: 탐지 0자 '인식 불가'(REQ-004I-5), 3자 미만 '분석 데이터 부족'(SFR-005I Side Effect)
  List<Widget> _buildCaseNotices() {
    final notices = <Widget>[];

    if (_isCanvas) {
      if (_lowConfidenceCount > 0) {
        notices.add(_buildInfoBanner(
          icon: Icons.help_outline_rounded,
          color: Colors.orange,
          message: '일부 문자($_lowConfidenceCount개)의 인식이 불확실해요. 결과가 정확하지 않을 수 있어요.',
        ));
      }
    } else {
      if (_detectedCount == 0) {
        notices.add(_buildInfoBanner(
          icon: Icons.error_outline_rounded,
          color: Colors.red,
          message: '글씨를 인식할 수 없습니다. 밝은 곳에서 글씨가 선명하게 보이도록 다시 촬영해주세요.',
        ));
      } else if (_detectedCount < 3) {
        notices.add(_buildInfoBanner(
          icon: Icons.info_outline_rounded,
          color: Colors.orange,
          message: '분석 데이터가 부족해요 (탐지 $_detectedCount자). 3자 이상 촬영하면 더 정확한 결과를 받을 수 있어요.',
        ));
      }
    }

    return notices;
  }

  /// 경계 케이스 안내용 공통 배너 (기존 대기 큐 배너와 동일한 톤).
  Widget _buildInfoBanner({
    required IconData icon,
    required MaterialColor color,
    required String message,
  }) {
    return Container(
      width: double.infinity,
      color: color.shade50,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Icon(icon, size: 16, color: color.shade700),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: TextStyle(fontSize: 12, color: color.shade800)),
          ),
        ],
      ),
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
        // 다운로드 시 이 RepaintBoundary 하위(배경 + 교정 오버레이)를 PNG로 캡처한다.
        child: RepaintBoundary(
          key: _overlayCaptureKey,
          child: Container(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: _isCanvas ? _buildCanvasOverlay() : _buildImageOverlay(),
          ),
        ),
      ),
    );
  }

  /// 피드백 오버레이가 그려진 화면을 PNG로 캡처해 사용자 기기에 다운로드한다.
  /// (웹: 브라우저 다운로드 / 그 외 플랫폼: 미지원 안내)
  Future<void> _downloadFeedbackImage() async {
    if (_isDownloading) return;
    setState(() => _isDownloading = true);
    try {
      final boundary = _overlayCaptureKey.currentContext?.findRenderObject()
          as RenderRepaintBoundary?;
      if (boundary == null) throw StateError('캡처 대상을 찾을 수 없습니다.');

      final image = await boundary.toImage(pixelRatio: 3.0);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      image.dispose();
      if (byteData == null) throw StateError('이미지 변환에 실패했습니다.');

      final filename =
          '${_isCanvas ? 'canvas' : 'image'}_feedback_${widget.sessionId}.png';
      await downloadPng(byteData.buffer.asUint8List(), filename);

      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('이미지를 다운로드했어요.')));
      }
    } on UnsupportedError {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('이 플랫폼에서는 이미지 다운로드를 지원하지 않아요.')),
        );
      }
    } catch (e) {
      debugPrint('[Feedback] download error: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('이미지 다운로드에 실패했어요. 잠시 후 다시 시도해주세요.')),
        );
      }
    } finally {
      if (mounted) setState(() => _isDownloading = false);
    }
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
            // 격자(showGrid)는 필기 보조선이므로 결과 배경에는 넣지 않는다.
            painter: StrokePainter(
              strokes: widget.strokes!,
              strokeWidth: widget.strokeWidth ?? 4.0,
            ),
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
