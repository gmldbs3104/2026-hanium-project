import 'dart:convert';
import 'package:uuid/uuid.dart';

import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/models/bounding_box.dart';
import '../../../shared/models/feedback_item.dart';
import '../../../shared/models/session_save_result.dart';
import '../models/image_result.dart';
import '../models/image_roi.dart';
import '../models/detected_char.dart';
import '../models/image_detect_response.dart';
import '../models/image_feedback_response.dart';

/// 이미지 모드 전용 API 서비스 (SFR-003I ~ SFR-007 대응)
///
/// REQ-003I-6: 캔버스 모드의 파이프라인(SFR-003C 이후)과 로직을 공유하지 않아야 한다
/// → canvas_mode/services/canvas_api_service.dart 와 완전히 별개 파일/클래스
///
/// ★ 백엔드 연동 방법 ★
/// [AppConfig.useMockApi] 를 false로 바꾸면 아래 메서드들이 자동으로
/// 실제 ApiClient 호출로 전환됩니다.
class ImageApiService {
  /// 촬영된 이미지를 Base64로 인코딩해 서버로 전송
  /// (requirement Action ①: POST /api/v1/image/preprocess)
  ///
  /// [roi]: SFR-003I Inputs의 선택적 관심영역 좌표. null이면 전체 이미지를 대상으로 한다.
  static Future<ImagePreprocessResult> preprocess({
    required List<int> imageBytes,
    ImageRoi? roi,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockPreprocess(imageBytes);
    }

    final base64Image = base64Encode(imageBytes);
    final response = await ApiClient.post(
      AppConfig.imagePreprocessEndpoint,
      {
        'image': base64Image,
        'input_type': 'camera',
        // SFR-003I Inputs: 선택적 ROI 좌표 (원본 이미지 픽셀 기준). 있을 때만 포함.
        if (roi != null) 'roi': roi.toJson(),
      },
    );
    return ImagePreprocessResult.fromJson(response);
  }

  /// SFR-004I: 문자 영역 Bounding Box 탐지 결과 조회
  /// (requirement: POST /api/v1/image/{image_session_id}/detect)
  static Future<ImageDetectResponse> detect(String imageSessionId) async {
    if (AppConfig.useMockApi) {
      return _mockDetect(imageSessionId);
    }

    final response = await ApiClient.post(AppConfig.imageDetectEndpoint(imageSessionId), {});
    return ImageDetectResponse.fromJson(response);
  }

  /// SFR-007: 교정 피드백 조회
  /// (requirement: GET /api/v1/image/{image_session_id}/feedback)
  ///
  /// ⚠️ 현재 백엔드는 문자 단위가 아니라 target_id="global" 하나만 내려준다.
  static Future<ImageFeedbackResponse> feedback(String imageSessionId) async {
    if (AppConfig.useMockApi) {
      return _mockFeedback(imageSessionId);
    }

    final response = await ApiClient.get(AppConfig.imageFeedbackEndpoint(imageSessionId));
    return ImageFeedbackResponse.fromJson(response);
  }

  /// SFR-009: 학습 결과 저장 확인 (이미지 원본 저장 동의 여부 포함)
  /// (requirement: POST /api/v1/image/{image_session_id}/confirm, REQ-009-4)
  static Future<SessionSaveResult> confirm(
    String imageSessionId, {
    required bool saveImage,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockConfirm(imageSessionId, saveImage: saveImage);
    }

    final response = await ApiClient.post(
      AppConfig.imageConfirmEndpoint(imageSessionId),
      {'save_image': saveImage},
    );
    return SessionSaveResult.fromJson(response);
  }

  /// ===== Mock 구현 =====
  static Future<ImagePreprocessResult> _mockPreprocess(List<int> imageBytes) async {
    await Future.delayed(AppConfig.mockDelay);

    if (imageBytes.isEmpty) {
      throw ApiException('이미지 데이터가 비어 있습니다.');
    }

    return ImagePreprocessResult(
      imageSessionId: 'mock-image-session-${const Uuid().v4().substring(0, 8)}',
      qualityScore: 82,
      detectedSlantAngle: 2.5,
      width: 1200,
      height: 1600,
    );
  }

  /// preprocess()의 mock 이미지 크기(가정: 1200x1600)에 맞춘 문자 박스 4개
  static Future<ImageDetectResponse> _mockDetect(String imageSessionId) async {
    await Future.delayed(AppConfig.mockDelay);

    final charIds = ['char_001', 'char_002', 'char_003', 'char_004'];
    final detectedChars = List.generate(charIds.length, (i) {
      return DetectedChar(
        charId: charIds[i],
        boundingBox: BoundingBox(x: 100.0 + i * 220, y: 300, width: 160, height: 180),
      );
    });

    return ImageDetectResponse(
      imageSessionId: imageSessionId,
      detectedChars: detectedChars,
      totalDetected: detectedChars.length,
    );
  }

  /// 현재 백엔드 실제 구현과 동일하게 target_id="global" 하나만 반환하는 mock
  /// (문자별 색상 구분이 안 되는 현재 한계를 mock에서도 동일하게 재현)
  static Future<ImageFeedbackResponse> _mockFeedback(String imageSessionId) async {
    await Future.delayed(AppConfig.mockDelay);

    return ImageFeedbackResponse(
      imageSessionId: imageSessionId,
      mode: 'image',
      overallScore: 82,
      achievementMessage: '잘 쓰고 있습니다. 조금만 더 다듬으면 완벽해질 거예요.',
      feedbackItems: const [
        FeedbackItem(
          targetId: 'global',
          feedbackMessage: '글자 크기가 균일합니다!',
          severity: 'good',
        ),
        FeedbackItem(
          targetId: 'global',
          feedbackMessage: '글자 기울기가 일정하지 않습니다. 일관된 방향으로 써보세요.',
          severity: 'warning',
        ),
      ],
    );
  }

  /// SFR-009: confirm() 의 mock 구현 — 항상 저장 성공으로 응답한다.
  static Future<SessionSaveResult> _mockConfirm(
    String imageSessionId, {
    required bool saveImage,
  }) async {
    await Future.delayed(AppConfig.mockDelay);

    return SessionSaveResult(
      sessionId: imageSessionId,
      savedAt: DateTime.now(),
      mode: 'image',
      firestoreSynced: true,
      s3Uploaded: saveImage, // 동의한 경우에만 S3 업로드된 것으로 표시 (REQ-009-4)
    );
  }
}
