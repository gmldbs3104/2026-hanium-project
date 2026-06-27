import 'package:uuid/uuid.dart';

import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../models/stroke.dart';

/// 캔버스 모드 전용 API 서비스 (SFR-003C 대응)
///
/// REQ-003C-6: 이미지 모드의 전처리 파이프라인(SFR-003I)을 거치지 않아야 한다
/// → 그래서 이 서비스는 image_mode 쪽 서비스와 코드를 전혀 공유하지 않습니다.
///
/// ★ 백엔드 연동 방법 ★
/// [AppConfig.useMockApi] 를 false로 바꾸면 아래 analyze() 메서드가
/// 자동으로 실제 ApiClient.post() 호출로 전환됩니다.
/// (이 파일의 다른 코드는 손댈 필요 없음)
class CanvasApiService {
  /// 획 데이터를 서버로 전송하고 분석 결과를 받아옴
  /// (requirement Action ④: POST /api/v1/canvas/analyze, PNG는 전송하지 않음)
  static Future<CanvasAnalyzeResult> analyze({
    required List<Stroke> strokes,
    required CanvasMetadata metadata,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockAnalyze(strokes, metadata);
    }

    final response = await ApiClient.post(
      AppConfig.canvasAnalyzeEndpoint,
      {
        'strokes': strokes.map((s) => s.toJson()).toList(),
        'canvas_metadata': metadata.toJson(),
      },
    );
    return CanvasAnalyzeResult.fromJson(response);
  }

  /// ===== Mock 구현 =====
  /// 실제 서버 없이도 화면 흐름(로딩 → 결과 → 피드백 화면 이동)을 테스트하기 위함
  static Future<CanvasAnalyzeResult> _mockAnalyze(
    List<Stroke> strokes,
    CanvasMetadata metadata,
  ) async {
    await Future.delayed(AppConfig.mockDelay);

    // 획이 하나도 없으면 에러 케이스도 흐름상 테스트 가능하도록 처리
    if (strokes.isEmpty) {
      throw ApiException('분석할 획 데이터가 없습니다.');
    }

    return CanvasAnalyzeResult(
      canvasSessionId: 'mock-canvas-session-${const Uuid().v4().substring(0, 8)}',
      overallScore: 78, // mock 고정값 - 실제 연동 시 서버 응답으로 대체됨
    );
  }
}
