import 'dart:convert';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../shared/services/api_client.dart';
import '../../auth/providers/auth_controller.dart';
import '../../auth/providers/auth_state.dart';
import '../services/image_api_service.dart';

/// 실전 모드 촬영 화면 (SFR-003I 대응) — UI 리디자인
///
/// REQ-003I-2: JPEG/PNG 지원, 최대 10MB (촬영 이미지 클라이언트 검증)
/// REQ-003I-4: 품질 점수 40점 미만 시 재촬영 요구
/// REQ-003I-6: 캔버스 모드와 로직을 공유하지 않음 (별도 화면/서비스로 완전 분리)
///
/// ⚠️ 백엔드 `/image/preprocess`는 ROI 좌표를 받지 않는다 (전체 이미지만 처리) —
/// 그래서 촬영한 전체 이미지를 그대로 전송하고 ROI는 보내지 않는다.
class ImageCaptureScreen extends ConsumerStatefulWidget {
  const ImageCaptureScreen({super.key});

  @override
  ConsumerState<ImageCaptureScreen> createState() => _ImageCaptureScreenState();
}

class _ImageCaptureScreenState extends ConsumerState<ImageCaptureScreen> {
  CameraController? _controller;
  bool _isProcessing = false;
  String? _errorMessage;
  bool _cameraUnavailable = false;

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
      setState(() => _cameraUnavailable = true);
    }
  }

  Future<void> _captureAndSend() async {
    if (_cameraUnavailable || _controller == null) {
      return;
    }

    setState(() {
      _isProcessing = true;
      _errorMessage = null;
    });

    try {
      final file = await _controller!.takePicture();
      final bytes = await file.readAsBytes();

      final validationError = _validateImage(bytes);
      if (validationError != null) {
        setState(() => _errorMessage = validationError);
        return;
      }

      final result = await ImageApiService.preprocess(imageBytes: bytes);

      final needsRetake = result.retakeRequired ??
          (result.qualityScore != null && result.qualityScore! < 40);
      if (needsRetake) {
        setState(() => _errorMessage = result.qualityScore != null
            ? '이미지 품질이 낮습니다 (${result.qualityScore}점). 다시 촬영해주세요.'
            : '사진 상태를 확인하기 어렵습니다. 다시 촬영해주세요.');
        return;
      }

      if (mounted) {
        // 오버레이 배경은 촬영 원본이 아니라 **서버가 회전·리사이즈한 이미지**여야
        // 좌표계가 맞는다(원본 위에 그리면 deskew 각도만큼 밀린다).
        // 그중 사용자에게는 컬러본(display)을 보여준다 — 이진본은 AI가 본 것이라
        // 개발 중엔 유용하지만 사용자 눈엔 자기 사진이 자연스럽다(팀 결정 2026-08-16).
        // 컬러본이 없으면 이진본, 그것도 없으면 원본 순으로 물러난다.
        final overlayBytes = result.displayImageBase64 != null
            ? base64Decode(result.displayImageBase64!)
            : result.preprocessedImageBase64 != null
                ? base64Decode(result.preprocessedImageBase64!)
                : bytes;
        context.go('/feedback', extra: {
          'mode': 'image',
          'sessionId': result.imageSessionId,
          'imageBytes': overlayBytes,
          'imageWidth': result.width,
          'imageHeight': result.height,
          // 연한 글씨 보존 모드면 비침이 글자로 잡혔을 수 있어 결과 화면에서 안내한다
          'preservationMode': result.preservationMode,
        });
      }
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.serverMessage ?? e.message);
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

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
      b[0] == 0x89 &&
      b[1] == 0x50 &&
      b[2] == 0x4E &&
      b[3] == 0x47 &&
      b[4] == 0x0D &&
      b[5] == 0x0A &&
      b[6] == 0x1A &&
      b[7] == 0x0A;

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_isProcessing) {
      final authState = ref.watch(authControllerProvider);
      final name = authState is AuthAuthenticated
          ? (authState.user.name ?? '회원')
          : '회원';
      return _AnalyzingView(name: name);
    }

    return Scaffold(
      backgroundColor: const Color(0xFF0E1116),
      body: Stack(
        children: [
          Positioned.fill(child: _buildPreview()),
          // 상단 그라데이션 + 컨트롤
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    _CircleIconButton(
                      icon: Icons.arrow_back_rounded,
                      onTap: () =>
                          context.canPop() ? context.pop() : context.go('/main'),
                    ),
                    const SizedBox(width: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 7),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.45),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.bolt_rounded,
                              size: 15, color: AppTheme.primaryColor),
                          SizedBox(width: 4),
                          Text('AI 감지 중',
                              style: TextStyle(
                                  color: Colors.white, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          // 중앙 가이드 프레임
          Center(
            child: SizedBox(
              width: 260,
              height: 200,
              child: CustomPaint(
                painter: _GuideFramePainter(),
                child: const Center(
                  child: Text('안녕하세요',
                      style: TextStyle(
                          fontSize: 34,
                          fontWeight: FontWeight.w500,
                          color: Colors.white38)),
                ),
              ),
            ),
          ),
          // 안내 문구 + 하단 컨트롤
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_errorMessage != null) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.6),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(_errorMessage!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: Color(0xFFFFB4B4), fontSize: 13)),
                      ),
                      const SizedBox(height: 16),
                    ],
                    Text(
                        _cameraUnavailable
                            ? '카메라를 사용할 수 없어 촬영할 수 없습니다'
                            : '정면에서 흔들리지 않게 촬영해주세요',
                        style:
                            const TextStyle(color: Colors.white70, fontSize: 13)),
                    const SizedBox(height: 18),
                    GestureDetector(
                      onTap: _cameraUnavailable ? null : _captureAndSend,
                      child: Container(
                        width: 68,
                        height: 68,
                        decoration: BoxDecoration(
                          color: _cameraUnavailable
                              ? Colors.white24
                              : AppTheme.primaryColor,
                          shape: BoxShape.circle,
                          border:
                              Border.all(color: Colors.white, width: 4),
                        ),
                        child: const Icon(Icons.camera_alt_rounded,
                            color: Colors.white, size: 28),
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: TextButton(
                        onPressed: () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                                content: Text('갤러리에서 불러오기는 준비 중입니다.')),
                          );
                        },
                        style: TextButton.styleFrom(
                          backgroundColor: Colors.white.withValues(alpha: 0.12),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius:
                                  BorderRadius.circular(AppTheme.radiusMd)),
                        ),
                        child: const Text('갤러리',
                            style: TextStyle(
                                fontSize: 14, fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreview() {
    if (_cameraUnavailable) {
      return Container(
        color: const Color(0xFF0E1116),
        child: const Center(
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.camera_alt_outlined, size: 56, color: Colors.white24),
                SizedBox(height: 12),
                Text(
                  '카메라를 사용할 수 없습니다.\n'
                  '카메라가 없는 기기이거나 카메라 권한이 거부되었습니다.\n'
                  '설정에서 카메라 권한을 허용한 뒤 다시 시도해주세요.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white38, fontSize: 12),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (_controller == null || !_controller!.value.isInitialized) {
      return const ColoredBox(
        color: Color(0xFF0E1116),
        child: Center(child: CircularProgressIndicator(color: Colors.white)),
      );
    }

    return CameraPreview(_controller!);
  }
}

/// AI 분석 중 로딩 화면
class _AnalyzingView extends StatelessWidget {
  final String name;
  const _AnalyzingView({required this.name});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      color: AppTheme.mintSurface,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.bolt_rounded,
                            size: 15, color: AppTheme.primaryDark),
                        SizedBox(width: 4),
                        Text('AI 감지 중',
                            style: TextStyle(
                                color: AppTheme.primaryDark, fontSize: 12)),
                      ],
                    ),
                  ),
                ),
              ),
              const Spacer(flex: 2),
              Text(
                'AI가 $name님의 글씨를 전문적으로 분석하고 있어요!\n잠시만 기다려주세요!',
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    height: 1.5,
                    color: AppTheme.ink),
              ),
              const SizedBox(height: 40),
              const SizedBox(
                width: 120,
                height: 120,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 120,
                      height: 120,
                      child: CircularProgressIndicator(
                        strokeWidth: 5,
                        valueColor:
                            AlwaysStoppedAnimation(AppTheme.primaryColor),
                      ),
                    ),
                    Icon(Icons.edit_rounded,
                        size: 44, color: AppTheme.mint),
                  ],
                ),
              ),
              const Spacer(flex: 3),
            ],
          ),
        ),
      ),
    );
  }
}

class _CircleIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _CircleIconButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.45),
          shape: BoxShape.circle,
        ),
        child: Icon(icon, color: Colors.white, size: 20),
      ),
    );
  }
}

/// 촬영 가이드 프레임(모서리 브래킷)
class _GuideFramePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppTheme.primaryColor
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    const len = 26.0;
    // 좌상
    canvas.drawLine(const Offset(0, 0), const Offset(len, 0), paint);
    canvas.drawLine(const Offset(0, 0), const Offset(0, len), paint);
    // 우상
    canvas.drawLine(Offset(size.width, 0), Offset(size.width - len, 0), paint);
    canvas.drawLine(Offset(size.width, 0), Offset(size.width, len), paint);
    // 좌하
    canvas.drawLine(Offset(0, size.height), Offset(len, size.height), paint);
    canvas.drawLine(Offset(0, size.height), Offset(0, size.height - len), paint);
    // 우하
    canvas.drawLine(
        Offset(size.width, size.height), Offset(size.width - len, size.height), paint);
    canvas.drawLine(
        Offset(size.width, size.height), Offset(size.width, size.height - len), paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
