import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../shared/services/api_client.dart';
import '../services/image_api_service.dart';

/// 카메라 촬영 화면 (SFR-003I 대응)
///
/// REQ-003I-2: JPEG/PNG 지원, 최대 10MB (촬영 이미지 클라이언트 검증)
/// REQ-003I-4: 품질 점수 40점 미만 시 재촬영 요구
/// REQ-003I-6: 캔버스 모드와 로직을 공유하지 않음 (별도 화면/서비스로 완전 분리)
///
/// ⚠️ 백엔드 `/image/preprocess`는 ROI 좌표를 받지 않는다 (전체 이미지만 처리) —
/// 그래서 촬영한 전체 이미지를 그대로 전송하고 ROI는 보내지 않는다.
class ImageCaptureScreen extends StatefulWidget {
  const ImageCaptureScreen({super.key});

  @override
  State<ImageCaptureScreen> createState() => _ImageCaptureScreenState();
}

class _ImageCaptureScreenState extends State<ImageCaptureScreen> {
  CameraController? _controller;
  bool _isProcessing = false;
  String? _errorMessage;
  bool _cameraUnavailable = false;

  // REQ-003I-2: 허용 최대 파일 크기(10MB)
  static const int _maxImageBytes = 10 * 1024 * 1024;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        setState(() => _cameraUnavailable = true);
        return;
      }
      _controller = CameraController(cameras.first, ResolutionPreset.high);
      await _controller!.initialize();
      if (mounted) setState(() {});
    } catch (e) {
      // 데스크톱/에뮬레이터 등 카메라가 없는 환경에서도
      // 화면 흐름(피드백 화면 이동까지)을 테스트할 수 있도록 fallback 처리
      setState(() => _cameraUnavailable = true);
    }
  }

  Future<void> _captureAndSend() async {
    setState(() {
      _isProcessing = true;
      _errorMessage = null;
    });

    try {
      List<int> bytes;
      bool isRealCapture;

      if (_cameraUnavailable || _controller == null) {
        // 카메라를 쓸 수 없는 환경(예: 데스크톱 테스트) → mock 이미지 바이트로 대체
        bytes = List<int>.filled(100, 0);
        isRealCapture = false;
      } else {
        final file = await _controller!.takePicture();
        bytes = await file.readAsBytes();
        isRealCapture = true;
      }

      // REQ-003I-2: 실제 촬영 이미지에 대해 형식(JPEG/PNG)·크기(≤10MB)를 클라이언트에서 먼저 검증
      if (isRealCapture) {
        final validationError = _validateImage(bytes);
        if (validationError != null) {
          setState(() => _errorMessage = validationError);
          return;
        }
      }

      final result = await ImageApiService.preprocess(imageBytes: bytes);

      // REQ-003I-4: 품질 점수 40점 미만 시 재촬영 요구
      // ⚠️ 백엔드가 quality_score를 아직 안 주면(null) 이 체크를 건너뜁니다.
      // (0으로 간주하면 실제 연동 시 항상 재촬영 에러가 나는 버그가 생김)
      if (result.qualityScore != null && result.qualityScore! < 40) {
        setState(() => _errorMessage = '이미지 품질이 낮습니다 (${result.qualityScore}점). 다시 촬영해주세요.');
        return;
      }

      if (mounted) {
        context.go('/feedback', extra: {
          'mode': 'image',
          'sessionId': result.imageSessionId,
          // ⚠️ 점수/성취 메시지는 여기서 넘기지 않습니다.
          // preprocess() 응답에는 원래 점수가 없고(백엔드 ImagePreprocessResponse 참고),
          // feedback_screen.dart가 GET /feedback을 직접 호출해서 진짜 점수를 받아옵니다.
          // SFR-007 오버레이 렌더링용: 촬영 이미지 바이트 + 원본 크기를 함께 전달
          'imageBytes': bytes,
          'imageWidth': result.width,
          'imageHeight': result.height,
        });
      }
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  /// REQ-003I-2: 형식(JPEG/PNG)·크기(≤10MB) 검증. 통과 시 null, 실패 시 오류 메시지 반환.
  String? _validateImage(List<int> bytes) {
    if (bytes.length > _maxImageBytes) {
      return '이미지 크기가 너무 큽니다 (최대 10MB).';
    }
    if (!_isJpeg(bytes) && !_isPng(bytes)) {
      return '지원하지 않는 이미지 형식입니다 (JPEG 또는 PNG만 가능).';
    }
    return null;
  }

  bool _isJpeg(List<int> b) =>
      b.length >= 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF;

  bool _isPng(List<int> b) =>
      b.length >= 8 &&
      b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47 &&
      b[4] == 0x0D && b[5] == 0x0A && b[6] == 0x1A && b[7] == 0x0A;

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('실전 모드')),
      body: Stack(
        children: [
          Positioned.fill(child: _buildPreview()),
          if (_errorMessage != null)
            Positioned(
              top: 16,
              left: 16,
              right: 16,
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: Text(
                  _errorMessage!,
                  style: TextStyle(color: Colors.red.shade700, fontSize: 13),
                ),
              ),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _isProcessing ? null : _captureAndSend,
        icon: _isProcessing
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
              )
            : const Icon(Icons.camera_alt_rounded),
        label: Text(_isProcessing ? '처리 중...' : '촬영하기'),
      ),
    );
  }

  Widget _buildPreview() {
    if (_cameraUnavailable) {
      return Container(
        color: Colors.black87,
        child: const Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.camera_alt_outlined, size: 64, color: Colors.white54),
              SizedBox(height: 12),
              Text(
                '이 기기/에뮬레이터에서는 카메라를 사용할 수 없습니다.\n'
                '실제 기기에서 실행하면 카메라 미리보기가 표시됩니다.\n'
                '(아래 버튼으로 mock 흐름은 계속 테스트할 수 있습니다)',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
            ],
          ),
        ),
      );
    }

    if (_controller == null || !_controller!.value.isInitialized) {
      return const ColoredBox(
        color: Colors.black,
        child: Center(child: CircularProgressIndicator(color: Colors.white)),
      );
    }

    return CameraPreview(_controller!);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// [2안] 촬영 후 드래그로 ROI 영역을 직접 지정하는 방식 (참고용 — 현재는 1안=전체 이미지 채택)
//
// 활성화 개요: 촬영 시 곧바로 preprocess를 호출하지 말고 "리뷰 단계"로 전환한다.
//  ① 아래 state를 _ImageCaptureScreenState에 추가
//  ② build()에서 _capturedBytes != null 이면 카메라 대신 _buildRoiReview()를 그림
//  ③ 리뷰 화면에서 드래그한 사각형(디스플레이 좌표)을 원본 픽셀 좌표로 역산해 ROI로 전송
//
// // ── state ──
// List<int>? _capturedBytes;   // 촬영 후 리뷰용 원본 바이트
// Size? _capturedImageSize;    // 디코딩한 원본 픽셀 크기 (좌표 매핑 기준)
// Rect? _roiRectDisplay;       // 화면(디스플레이) 좌표계의 드래그 사각형
//
// // ── 촬영: preprocess 대신 리뷰 단계로 전환 ──
// Future<void> _captureForReview() async {
//   final file = await _controller!.takePicture();
//   final bytes = await file.readAsBytes();
//   final err = _validateImage(bytes);                 // REQ-003I-2
//   if (err != null) { setState(() => _errorMessage = err); return; }
//   final codec = await ui.instantiateImageCodec(Uint8List.fromList(bytes));
//   final frame = await codec.getNextFrame();
//   setState(() {
//     _capturedBytes = bytes;
//     _capturedImageSize =
//         Size(frame.image.width.toDouble(), frame.image.height.toDouble());
//     _roiRectDisplay = null;
//   });
//   frame.image.dispose();
// }
//
// // ── 리뷰 UI: 사진 위에 드래그로 사각형 ──
// Widget _buildRoiReview() {
//   return Column(children: [
//     Expanded(
//       child: GestureDetector(
//         onPanStart: (d) => setState(() =>
//             _roiRectDisplay = Rect.fromPoints(d.localPosition, d.localPosition)),
//         onPanUpdate: (d) => setState(() => _roiRectDisplay =
//             Rect.fromPoints(_roiRectDisplay!.topLeft, d.localPosition)),
//         child: LayoutBuilder(builder: (context, box) {
//           return Stack(fit: StackFit.expand, children: [
//             Image.memory(Uint8List.fromList(_capturedBytes!), fit: BoxFit.contain),
//             if (_roiRectDisplay != null)
//               CustomPaint(painter: _RoiPainter(_roiRectDisplay!)),
//           ]);
//         }),
//       ),
//     ),
//     Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
//       TextButton(
//         onPressed: () => setState(() => _capturedBytes = null),
//         child: const Text('다시 촬영')),
//       TextButton(
//         onPressed: () => _sendWithRoi(null, Size.zero),  // ROI 없이 전체 분석
//         child: const Text('전체 이미지로 분석')),
//       FilledButton(
//         onPressed: _roiRectDisplay == null ? null : () {}, // _sendWithRoi(_roiRectDisplay, boxSize)
//         child: const Text('이 영역으로 분석')),
//     ]),
//   ]);
// }
//
// // ── 디스플레이 좌표 → 원본 픽셀 좌표 매핑 후 preprocess ──
// // [displayBox]는 이미지를 그린 영역의 크기(LayoutBuilder의 constraints.biggest).
// Future<void> _sendWithRoi(Rect? displayRect, Size displayBox) async {
//   ImageRoi? roi;
//   if (displayRect != null && _capturedImageSize != null) {
//     final img = _capturedImageSize!;
//     // BoxFit.contain: 이미지가 letterbox로 들어가므로 스케일·오프셋을 역산한다.
//     final scale = (displayBox.width / img.width) < (displayBox.height / img.height)
//         ? displayBox.width / img.width
//         : displayBox.height / img.height;
//     final dispW = img.width * scale, dispH = img.height * scale;
//     final offX = (displayBox.width - dispW) / 2, offY = (displayBox.height - dispH) / 2;
//     final px = ((displayRect.left - offX) / scale).clamp(0.0, img.width);
//     final py = ((displayRect.top - offY) / scale).clamp(0.0, img.height);
//     final pw = (displayRect.width / scale).clamp(0.0, img.width - px);
//     final ph = (displayRect.height / scale).clamp(0.0, img.height - py);
//     roi = ImageRoi(x: px.round(), y: py.round(), width: pw.round(), height: ph.round());
//   }
//   final result =
//       await ImageApiService.preprocess(imageBytes: _capturedBytes!, roi: roi);
//   // 이후 품질 체크(REQ-003I-4) + /feedback 이동은 _captureAndSend와 동일.
// }
//
// // ── ROI 사각형 페인터 (ROI 밖을 어둡게 + 주황 테두리) ──
// class _RoiPainter extends CustomPainter {
//   final Rect rect;
//   _RoiPainter(this.rect);
//   @override
//   void paint(Canvas canvas, Size size) {
//     canvas.saveLayer(Offset.zero & size, Paint());
//     canvas.drawRect(Offset.zero & size, Paint()..color = Colors.black54);
//     canvas.drawRect(rect, Paint()..blendMode = BlendMode.clear);
//     canvas.restore();
//     canvas.drawRect(
//         rect,
//         Paint()
//           ..color = Colors.orange
//           ..style = PaintingStyle.stroke
//           ..strokeWidth = 2);
//   }
//   @override
//   bool shouldRepaint(_RoiPainter old) => old.rect != rect;
// }
// ═══════════════════════════════════════════════════════════════════════════
