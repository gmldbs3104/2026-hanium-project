import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../shared/services/api_client.dart';
import '../services/image_api_service.dart';

/// 카메라 촬영 화면 (SFR-003I 대응)
///
/// REQ-003I-2: JPEG/PNG 지원, 최대 10MB
/// REQ-003I-4: 품질 점수 40점 미만 시 재촬영 요구
/// REQ-003I-6: 캔버스 모드와 로직을 공유하지 않음 (별도 화면/서비스로 완전 분리)
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

      if (_cameraUnavailable || _controller == null) {
        // 카메라를 쓸 수 없는 환경(예: 데스크톱 테스트) → mock 이미지 바이트로 대체
        bytes = List<int>.filled(100, 0);
      } else {
        final file = await _controller!.takePicture();
        bytes = await file.readAsBytes();
      }

      final result = await ImageApiService.preprocess(imageBytes: bytes);

      // REQ-003I-4: 품질 점수 40점 미만 시 재촬영 요구
      if (result.qualityScore < 40) {
        setState(() => _errorMessage = '이미지 품질이 낮습니다 (${result.qualityScore}점). 다시 촬영해주세요.');
        return;
      }

      if (mounted) {
        context.go('/feedback', extra: {
          'mode': 'image',
          'sessionId': result.imageSessionId,
          'score': result.qualityScore,
        });
      }
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

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
