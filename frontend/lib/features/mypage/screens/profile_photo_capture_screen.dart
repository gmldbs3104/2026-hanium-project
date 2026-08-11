import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../../../core/app_theme.dart';

/// 프로필 사진 촬영 화면.
///
/// image_mode/screens/image_capture_screen.dart와 같은 camera 패키지를 재사용한다
/// (새 의존성을 추가하지 않기 위해 갤러리 선택 대신 촬영만 지원). 촬영한 바이트를
/// `Navigator.pop(context, bytes)`로 돌려주고, 호출부(profile_edit_screen.dart)가
/// ProfileOverrideNotifier.setPhoto()로 로컬에 저장한다.
class ProfilePhotoCaptureScreen extends StatefulWidget {
  const ProfilePhotoCaptureScreen({super.key});

  @override
  State<ProfilePhotoCaptureScreen> createState() => _ProfilePhotoCaptureScreenState();
}

class _ProfilePhotoCaptureScreenState extends State<ProfilePhotoCaptureScreen> {
  CameraController? _controller;
  bool _isCapturing = false;
  bool _cameraUnavailable = false;
  String? _errorMessage;

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
      // 셀피 용도이므로 전면 카메라가 있으면 우선 사용.
      final camera = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      _controller = CameraController(camera, ResolutionPreset.medium);
      await _controller!.initialize();
      if (mounted) setState(() {});
    } catch (e) {
      setState(() => _cameraUnavailable = true);
    }
  }

  Future<void> _capture() async {
    if (_controller == null || _isCapturing) return;
    setState(() {
      _isCapturing = true;
      _errorMessage = null;
    });
    try {
      final file = await _controller!.takePicture();
      final Uint8List bytes = await file.readAsBytes();
      if (mounted) Navigator.pop(context, bytes);
    } catch (e) {
      if (mounted) setState(() => _errorMessage = '촬영에 실패했습니다. 다시 시도해주세요.');
    } finally {
      if (mounted) setState(() => _isCapturing = false);
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
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        leading: const BackButton(),
        title: const Text('프로필 사진 촬영'),
      ),
      body: SafeArea(
        child: _cameraUnavailable
            ? const Center(
                child: Text('카메라를 사용할 수 없습니다.',
                    style: TextStyle(color: Colors.white70)),
              )
            : _controller == null || !_controller!.value.isInitialized
                ? const Center(child: CircularProgressIndicator(color: Colors.white))
                : Column(
                    children: [
                      Expanded(child: Center(child: CameraPreview(_controller!))),
                      if (_errorMessage != null)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(_errorMessage!,
                              style: const TextStyle(color: AppTheme.errorColor)),
                        ),
                      Padding(
                        padding: const EdgeInsets.all(20),
                        child: GestureDetector(
                          onTap: _isCapturing ? null : _capture,
                          child: Container(
                            width: 68,
                            height: 68,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: Colors.white,
                              border: Border.all(color: AppTheme.mint, width: 3),
                            ),
                            child: _isCapturing
                                ? const Padding(
                                    padding: EdgeInsets.all(18),
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : null,
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }
}
