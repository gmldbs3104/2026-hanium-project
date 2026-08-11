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
  /// ⚠️ [targetText] 는 **백엔드가 아직 안 받는 필드**다 (2026-08-11 기준).
  /// 현재 `/canvas/{id}/analyze-detail`(backend/app/api/v1/routes/handwriting.py)이
  /// 항상 `get_standard(db, char=None)`으로 호출돼서 표준 획순(expected_sequence)이
  /// 늘 빈 배열이 되고, 그 결과 실제로 몇 획을 쓰든 "획이 N개 더 많습니다"라는
  /// 의미 없는 메시지만 나온다 — 이게 "AI 분석 오류"의 원인이었다.
  ///
  /// 백엔드가 아래처럼 고쳐지는 걸 전제로 이 값을 미리 보낸다(현재는 백엔드가
  /// 모르는 필드라 pydantic이 조용히 무시함 — 부작용 없음):
  ///   1. `schemas/canvas.py`   CanvasAnalyzeRequest 에 `target_text: Optional[str] = None` 추가
  ///   2. `routes/handwriting.py` analyze_canvas() 가 세션 캐시에
  ///      `"target_text": payload.target_text` 로 같이 저장
  ///   3. `routes/handwriting.py` analyze_canvas_detail() 이 char_groups를 순회할 때
  ///      (char_groups는 필기 순서로 정렬됨) `target_text[idx]`를 그 글자로 보고
  ///      `get_standard(db, char=target_text[idx] if idx < len(target_text) else None)`
  ///      호출 — 지금처럼 `char=None` 고정 아님
  ///   4. `services/canvas_analysis.py` get_standard()는 완성형 음절(11,172자)만
  ///      DB(StrokeStandard)에 있고 단독 자모(ㄱ/ㅏ 등, '자음 쓰기'/'모음 쓰기' 탭)는
  ///      없으므로, DB 조회 전에 자모 전용 획순 테이블(초성/중성 stroke 정의 —
  ///      app/db/seed_stroke_standards.py의 CHOSEONG_STROKES/JUNGSEONG_STROKES와
  ///      동일 데이터)을 먼저 찾아보는 분기가 필요함
  ///
  /// 현재 캔버스 연습 화면(canvas_input_screen.dart)은 한 번에 한 글자만 쓰게
  /// 하므로 [targetText]는 보통 길이 1인 문자열(예: "ㄱ", "각")이다.
  static Future<CanvasAnalyzeResult> analyze({
    required List<Stroke> strokes,
    required CanvasMetadata metadata,
    String? targetText,
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
  /// 응답 자체는 화면에서 쓰지 않으므로(진짜 점수는 feedback()에서만 받음) 반환하지 않는다.
  /// (requirement: POST /api/v1/canvas/{canvas_session_id}/analyze-detail)
  static Future<void> analyzeDetail(String canvasSessionId, {String? idToken}) async {
    if (AppConfig.useMockApi) return;

    await ApiClient.post(
      AppConfig.canvasAnalyzeDetailEndpoint(canvasSessionId),
      {},
      authToken: idToken,
    );
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
