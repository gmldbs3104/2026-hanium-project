import 'package:uuid/uuid.dart';

import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/models/bounding_box.dart';
import '../../../shared/models/feedback_item.dart';
import '../../../shared/models/session_save_result.dart';
import '../../../shared/models/weak_habit.dart';
import '../models/image_result.dart';
import '../models/detected_char.dart';
import '../models/image_detect_response.dart';
import '../models/image_feedback_response.dart';
import '../models/image_analysis_response.dart';

/// 이미지 모드 전용 API 서비스 (SFR-003I ~ SFR-007 대응)
///
/// REQ-003I-6: 캔버스 모드의 파이프라인(SFR-003C 이후)과 로직을 공유하지 않아야 한다
/// → canvas_mode/services/canvas_api_service.dart 와 완전히 별개 파일/클래스
///
/// ★ 백엔드 연동 방법 ★
/// [AppConfig.useMockApi] 를 false로 바꾸면 아래 메서드들이 자동으로
/// 실제 ApiClient 호출로 전환됩니다.
class ImageApiService {
  /// 촬영된 이미지를 multipart/form-data로 서버에 업로드
  /// (requirement Action ①: POST /api/v1/image/preprocess, 백엔드는 필드명 `file`의
  /// multipart 업로드를 기대함 — backend/app/api/v1/routes/image.py 참고)
  static Future<ImagePreprocessResult> preprocess({
    required List<int> imageBytes,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockPreprocess(imageBytes);
    }

    final isPng = _isPngBytes(imageBytes);
    final response = await ApiClient.postMultipart(
      AppConfig.imagePreprocessEndpoint,
      imageBytes,
      fieldName: 'file',
      filename: isPng ? 'capture.png' : 'capture.jpg',
      contentType: isPng ? 'image/png' : 'image/jpeg',
    );
    return ImagePreprocessResult.fromJson(response);
  }

  static bool _isPngBytes(List<int> b) =>
      b.length >= 8 &&
      b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47 &&
      b[4] == 0x0D && b[5] == 0x0A && b[6] == 0x1A && b[7] == 0x0A;

  /// SFR-004I: 문자 영역 Bounding Box 탐지 결과 조회
  /// (requirement: POST /api/v1/image/{image_session_id}/detect)
  static Future<ImageDetectResponse> detect(String imageSessionId) async {
    if (AppConfig.useMockApi) {
      return _mockDetect(imageSessionId);
    }

    final response = await ApiClient.post(AppConfig.imageDetectEndpoint(imageSessionId), {});
    return ImageDetectResponse.fromJson(response);
  }

  /// SFR-005I: 크기 균일성/기울기/줄 정렬 분석 트리거 (인증 필요)
  /// 이 호출이 서버 캐시에 분석 결과를 채워야 feedback()이 동작한다.
  /// 종합 점수/성취 메시지는 여전히 feedback()에서만 받지만(백엔드 스키마 참고),
  /// 이 응답에만 실리는 자간·행간 균등성 점수(DATA_FLOW.md §5-8, AI는 5지표를
  /// 채점하지만 기존 계약엔 3개뿐이었다)는 여기서 파싱해 반환한다.
  /// (requirement: POST /api/v1/image/{image_session_id}/analyze)
  static Future<ImageAnalysisResponse> analyze(
    String imageSessionId, {
    String? idToken,
  }) async {
    if (AppConfig.useMockApi) return _mockAnalyze(imageSessionId);

    final response = await ApiClient.post(
      AppConfig.imageAnalyzeEndpoint(imageSessionId),
      {},
      authToken: idToken,
    );
    return ImageAnalysisResponse.fromJson(response);
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
      retakeRequired: false,
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

  /// _mockDetect()의 4자에 맞춘 mock 상세 분석 (자간·행간 균등성 점수 포함)
  static Future<ImageAnalysisResponse> _mockAnalyze(String imageSessionId) async {
    await Future.delayed(AppConfig.mockDelay);

    return ImageAnalysisResponse(
      imageSessionId: imageSessionId,
      sizeUniformityScore: 88,
      avgSlantAngle: 2.5,
      slantConsistencyScore: 74,
      lineAlignmentScore: 91,
      overallScore: 82,
      overallTilt: 'straight',
      totalGrade: '우수',
      clarityWarnings: const [],
      spacingUniformityScore: 79,
      lineSpacingUniformityScore: 85,
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
      // 백엔드 연동 예정 필드 — 목업 데모용 샘플
      weakHabits: const [
        WeakHabit(label: '크기 불균일', count: 4, severity: 'warning'),
        WeakHabit(label: '줄 정렬 흐트러짐', count: 3, severity: 'warning'),
      ],
      targetScore: 90,
      scoreTrend: 3,
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
