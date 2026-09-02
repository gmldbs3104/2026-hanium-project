import 'package:flutter/material.dart' show Rect;
import 'package:uuid/uuid.dart';

import '../../../core/app_config.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/models/bounding_box.dart';
import '../../../shared/models/feedback_item.dart';
import '../../../shared/models/session_save_result.dart';
import '../../../shared/models/weak_habit.dart';
import '../models/stroke.dart';
import '../models/char_group.dart';
import '../models/canvas_group_response.dart';
import '../models/canvas_feedback_response.dart';
import '../models/canvas_char_analysis.dart';

/// 캔버스 모드 전용 API 서비스 (SFR-003C ~ SFR-007 대응)
///
/// REQ-003C-6: 이미지 모드의 전처리 파이프라인(SFR-003I)을 거치지 않아야 한다
/// → 그래서 이 서비스는 image_mode 쪽 서비스와 코드를 전혀 공유하지 않습니다.
///
/// ★ 백엔드 연동 방법 ★
/// [AppConfig.useMockApi] 를 false로 바꾸면 아래 메서드들이 자동으로
/// 실제 ApiClient 호출로 전환됩니다.
class CanvasApiService {
  /// 획 데이터를 서버로 전송하고 session_id를 받아옴 (아직 점수 계산 전 단계)
  /// (requirement Action ④: POST /api/v1/canvas/analyze, PNG는 전송하지 않음)
  ///
  /// [targetText]는 백엔드가 받아서 사용한다 (2026-08-11 연결 완료, DATA_FLOW.md §8-A).
  /// `/canvas/analyze`가 세션 캐시에 `target_text`를 저장해두면,
  /// `/canvas/{id}/analyze-detail`이 `ai.canvas.canvas_quality_analyzer.analyze_canvas_writing()`을
  /// 호출할 때 그대로 넘어가 위치+모양 기하 비교(`analyze_stroke_order_by_position`)로
  /// 순서 오류까지 잡는다. 예전처럼 DB(StrokeStandard, 완성형 음절만 있음)를 거치지
  /// 않으므로, 자모 단독(ㄱ/ㅏ 등)이 여전히 채점 안 되는 것은 DB 부재가 아니라
  /// `decompose_syllable()`이 완성형 음절 1글자만 분해할 수 있기 때문 — 이 경우
  /// 획순 채점만 생략되고(크기/자간은 정상 채점) 서버가 에러를 내지는 않는다.
  ///
  /// 현재 캔버스 연습 화면(canvas_input_screen.dart)은 한 번에 한 글자만 쓰게
  /// 하므로 [targetText]는 보통 길이 1인 문자열(예: "ㄱ", "각")이다.
  ///
  /// [charPositions]는 안내 문구(배경에 그려진 따라쓰기 가이드)에서 글자별로 계산한
  /// 렌더링 좌표({char, index, x, y, width, height})다. 백엔드 스키마
  /// (CanvasAnalyzeRequest)가 아직 이 필드를 정의하지 않아 현재는 그대로 무시되지만,
  /// pydantic 기본 동작상 알 수 없는 필드가 있어도 요청은 정상 처리된다.
  /// [guideBox]는 화면에 그려준 획순 가이드 영역(획 좌표와 같은 좌표계)이다.
  /// 서버의 **크기 채점 기준**이라, 안 보내면 글자가 하나뿐인 연습에서 크기가
  /// 미측정으로 남는다(비교할 옆 글자가 없기 때문). strokeGuideBox()로 만들 것.
  static Future<CanvasAnalyzeResult> analyze({
    required List<Stroke> strokes,
    required CanvasMetadata metadata,
    String? targetText,
    List<Map<String, dynamic>>? charPositions,
    Rect? guideBox,
  }) async {
    if (AppConfig.useMockApi) {
      return _mockAnalyze(strokes, metadata);
    }

    final response = await ApiClient.post(
      AppConfig.canvasAnalyzeEndpoint,
      {
        'strokes': strokes.map((s) => s.toJson()).toList(),
        'metadata': metadata.toJson(),
        if (targetText != null) 'target_text': targetText,
        if (charPositions != null) 'char_positions': charPositions,
        if (guideBox != null)
          'guide_box': {
            'x': guideBox.left,
            'y': guideBox.top,
            'width': guideBox.width,
            'height': guideBox.height,
          },
      },
    );
    return CanvasAnalyzeResult.fromJson(response);
  }

  /// SFR-004C: 획 그룹핑 및 문자 단위 분할 결과 조회
  /// (requirement: POST /api/v1/canvas/{canvas_session_id}/group)
  static Future<CanvasGroupResponse> group(String canvasSessionId) async {
    if (AppConfig.useMockApi) {
      return _mockGroup(canvasSessionId);
    }

    final response = await ApiClient.post(
      AppConfig.canvasGroupEndpoint(canvasSessionId),
      {},
    );
    return CanvasGroupResponse.fromJson(response);
  }

  /// SFR-005C: 획순/자간/크기 분석 트리거 (인증 필요)
  /// 이 호출이 서버 캐시에 분석 결과를 채워야 feedback()이 동작한다.
  /// 종합 점수/성취 메시지는 여전히 feedback()에서만 받지만(백엔드 스키마 참고),
  /// 이 응답에만 실리는 문자별 필압/속도 프로필·교정 플래그·복수 정본 안내
  /// (DATA_FLOW.md §7.3/§8-B·C·D)는 여기서 파싱해 반환한다 — 화면(피드백 화면의
  /// 문자별 상세 바텀시트)에서 char_id로 조회해서 쓴다.
  /// (requirement: POST /api/v1/canvas/{canvas_session_id}/analyze-detail)
  static Future<CanvasAnalysisResponse> analyzeDetail(
    String canvasSessionId, {
    String? idToken,
  }) async {
    if (AppConfig.useMockApi) return _mockAnalyzeDetail(canvasSessionId);

    final response = await ApiClient.post(
      AppConfig.canvasAnalyzeDetailEndpoint(canvasSessionId),
      {},
      authToken: idToken,
    );
    return CanvasAnalysisResponse.fromJson(response);
  }

  /// SFR-007: 교정 피드백 조회 (문자별 severity + 메시지 + 최종 종합 점수)
  /// ⚠️ 캔버스 모드의 "진짜" 점수/성취 메시지는 오직 여기서만 나옵니다.
  /// (analyze()/group() 응답에는 점수가 없습니다 — 백엔드 스키마 참고)
  /// (requirement: GET /api/v1/canvas/{canvas_session_id}/feedback)
  static Future<CanvasFeedbackResponse> feedback(String canvasSessionId) async {
    if (AppConfig.useMockApi) {
      return _mockFeedback(canvasSessionId);
    }

    final response = await ApiClient.get(AppConfig.canvasFeedbackEndpoint(canvasSessionId));
    return CanvasFeedbackResponse.fromJson(response);
  }

  /// SFR-009: 학습 결과 저장 확인
  /// 사용자가 피드백 화면에서 "확인"을 탭하면 호출한다.
  /// (requirement: POST /api/v1/canvas/{canvas_session_id}/confirm)
  static Future<SessionSaveResult> confirm(String canvasSessionId) async {
    if (AppConfig.useMockApi) {
      return _mockConfirm(canvasSessionId);
    }

    final response = await ApiClient.post(AppConfig.canvasConfirmEndpoint(canvasSessionId), {});
    return SessionSaveResult.fromJson(response);
  }

  /// ===== Mock 구현 =====
  static Future<CanvasAnalyzeResult> _mockAnalyze(
    List<Stroke> strokes,
    CanvasMetadata metadata,
  ) async {
    await Future.delayed(AppConfig.mockDelay);

    if (strokes.isEmpty) {
      throw ApiException('분석할 획 데이터가 없습니다.');
    }

    return CanvasAnalyzeResult(
      canvasSessionId: 'mock-canvas-session-${const Uuid().v4().substring(0, 8)}',
      strokeCount: strokes.length,
      status: 'received',
    );
  }

  /// 화면 크기와 무관하게, 실제 캔버스 위에 자연스럽게 흩어져 보이도록
  /// 200x50 크기의 문자 박스 4개를 가로로 나열한 mock 데이터
  static Future<CanvasGroupResponse> _mockGroup(String canvasSessionId) async {
    await Future.delayed(AppConfig.mockDelay);

    final charIds = ['char_001', 'char_002', 'char_003', 'char_004'];
    final charGroups = List.generate(charIds.length, (i) {
      return CharGroup(
        charId: charIds[i],
        boundingBox: BoundingBox(x: 40.0 + i * 90, y: 120, width: 70, height: 80),
        strokeCount: 2 + i % 3,
        confidence: 0.9 - (i * 0.05),
        lowConfidence: i == charIds.length - 1, // 마지막 글자만 저신뢰도 mock
      );
    });

    return CanvasGroupResponse(
      canvasSessionId: canvasSessionId,
      charGroups: charGroups,
      lowConfidenceCount: charGroups.where((g) => g.lowConfidence).length,
    );
  }

  /// _mockGroup()의 char_id와 매칭되는 mock 상세 분석 (필압/속도/교정 플래그/획순 노트)
  static Future<CanvasAnalysisResponse> _mockAnalyzeDetail(
    String canvasSessionId,
  ) async {
    await Future.delayed(AppConfig.mockDelay);

    final charIds = ['char_001', 'char_002', 'char_003', 'char_004'];
    final flags = [
      <String>[],
      ['spacing_too_wide'],
      ['stroke_order_error'],
      ['size_small'],
    ];
    final results = List.generate(charIds.length, (i) {
      return CanvasCharAnalysis(
        charId: charIds[i],
        strokeOrderResult: i == 2
            ? const StrokeOrderResult(
                errorCount: 2,
                likelyWrongCharacter: false,
                corrections: ['1번째로 그린 획은 표준 순서상 2번째 위치에 그려야 합니다.'],
                notes: [],
              )
            : null,
        directionResult: null,
        tiltResult: null,
        balanceResult: null,
        componentBoxes: null,
        spacingDeviation: i == 1 ? 8.0 : 0.0,
        sizeDeviation: i == 3 ? -15.0 : 0.0,
        sizeFillRatio: null,
        itemScores: const {},
        motion: WritingMotionProfile(
          meanSpeedPxPerMs: 0.3 + i * 0.02,
        ),
        overallScore: 90 - i * 8,
        correctionFlags: flags[i],
      );
    });

    return CanvasAnalysisResponse(
      canvasSessionId: canvasSessionId,
      results: results,
    );
  }

  /// _mockGroup()의 char_id와 매칭되는 mock 피드백
  /// (실제 백엔드처럼 char_id별로 다른 severity를 부여해 오버레이 색상 테스트가 가능하도록 구성)
  static Future<CanvasFeedbackResponse> _mockFeedback(String canvasSessionId) async {
    await Future.delayed(AppConfig.mockDelay);

    final feedbackItems = [
      const FeedbackItem(
        targetId: 'char_001',
        feedbackMessage: '획순이 정확합니다. 자간이 적절합니다. 글자 크기가 적절합니다.',
        severity: 'good',
      ),
      const FeedbackItem(
        targetId: 'char_002',
        feedbackMessage: '자간이 표준보다 8.0px 넓습니다. 글자를 더 가깝게 써보세요.',
        severity: 'warning',
      ),
      const FeedbackItem(
        targetId: 'char_003',
        feedbackMessage: '획순에 2개의 오류가 있습니다. 표준 획순을 다시 확인해보세요.',
        severity: 'error',
      ),
      const FeedbackItem(
        targetId: 'char_004',
        feedbackMessage: '글자가 표준보다 15.0% 작습니다.',
        severity: 'warning',
      ),
    ];

    return CanvasFeedbackResponse(
      canvasSessionId: canvasSessionId,
      mode: 'canvas',
      overallScore: 78,
      achievementMessage: '좋아요! 조금만 더 연습하면 완벽해질 거예요.',
      feedbackItems: feedbackItems,
      // 백엔드 연동 예정 필드 — 목업 데모용 샘플 (backend가 weak_habits/target_score/
      // score_trend를 내려주면 이 값들이 실제 응답으로 대체된다).
      weakHabits: const [
        WeakHabit(label: '선 이탈', count: 3, severity: 'warning'),
        WeakHabit(label: '좌상향 기울기 심함', count: 2, severity: 'warning'),
        WeakHabit(label: '밸런스 불균형', count: 6, severity: 'error'),
      ],
      targetScore: 90,
      scoreTrend: 5,
    );
  }

  /// SFR-009: confirm() 의 mock 구현 — 항상 저장 성공으로 응답한다.
  /// (오프라인 재시도 큐 동작을 직접 테스트하고 싶으면 이 메서드에서
  ///  일시적으로 `throw ApiException('mock 네트워크 오류');` 로 바꿔보면 된다)
  static Future<SessionSaveResult> _mockConfirm(String canvasSessionId) async {
    await Future.delayed(AppConfig.mockDelay);

    return SessionSaveResult(
      sessionId: canvasSessionId,
      savedAt: DateTime.now(),
      mode: 'canvas',
      firestoreSynced: true,
      s3Uploaded: false, // 캔버스 모드는 이미지 저장 대상이 없음
    );
  }
}
