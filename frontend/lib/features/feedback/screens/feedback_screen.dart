import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderRepaintBoundary;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/app_theme.dart';
import '../../../core/target_score_provider.dart';
import '../../../shared/services/api_client.dart';
import '../../../shared/widgets/ui_kit.dart';
import '../../../shared/models/feedback_item.dart';
import '../../../shared/models/weak_habit.dart';
import '../../auth/providers/auth_controller.dart';
import '../../dashboard/providers/dashboard_refresh_provider.dart';
import '../utils/canvas_feedback_parser.dart';
import '../utils/image_download.dart';
import '../utils/severity_style.dart';
import '../../canvas_mode/models/stroke.dart';
import '../../canvas_mode/models/canvas_char_analysis.dart';
import '../../canvas_mode/services/canvas_api_service.dart';
import '../../canvas_mode/widgets/stroke_painter.dart';
import '../../image_mode/services/image_api_service.dart';
import '../../image_mode/models/image_analysis_response.dart';
import '../models/canvas_correction_overlay_item.dart';
import '../models/component_overlay_item.dart';
import '../models/image_bbox_overlay_item.dart';
import '../models/pending_session_save.dart';
import '../services/session_save_queue.dart';
import '../widgets/feedback_action_bar.dart';
import '../widgets/canvas_correction_overlay_view.dart';
import '../widgets/component_overlay_view.dart';
import '../widgets/image_bbox_overlay_view.dart';
import '../widgets/preservation_notice.dart';

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
/// [UI 리디자인] 목업 기준 2단 레이아웃:
///   상단  : 연습 종류 탭 + 진행률 (연습 화면에서 넘어온 컨텍스트가 있을 때)
///   좌측  : 필기 재현 + 교정 오버레이
///   우측 상단 : 현재 점수 카드 (목표 대비 진행바 + 추세 배지)
///   우측 하단 : AI 분석 "취약한 습관" 패널
/// 좁은 화면(< 720px)에서는 세로로 쌓아 스크롤한다.
///
/// SFR-009: 하단 "학습 기록 저장" 버튼을 탭하면 저장을 트리거한다 (requirement.md
/// SFR-007 Post-condition: "사용자가 피드백을 확인하면 SFR-009가 트리거된다").
/// 저장 요청이 네트워크 문제로 실패하면 로컬 큐에 쌓아두고, 다음에 이 화면을
/// 열 때(또는 "지금 재시도")마다 자동으로 다시 시도한다 (REQ-009-5).
class FeedbackScreen extends ConsumerStatefulWidget {
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

  /// true면 연한 글씨 보존 모드로 전처리됐다는 뜻 — 종이 뒷면 글씨(비침)가 지워지지
  /// 않고 남아 글자로 잡혔을 수 있다. 경고 문구만 띄운다(팀 결정 2026-08-12):
  /// 비침을 실제로 걸러내려면 탐지 확률값이 필요한데 지금 파이프라인엔 없다.
  /// 상세: DATA_FLOW.md §5-10 · DEVLOG 17막.
  final bool? preservationMode;

  // 연습 화면에서 넘어온 컨텍스트 (있으면 상단에 탭/진행률을 그대로 보여준다).
  // 없으면(null) 헤더를 생략한다 — 이미지 모드 등.
  final List<String>? practiceTabs;
  final int? practiceTabIndex;
  final int? practiceStep;
  final int? practiceTotal;

  // 헤더 탭/다음 글자에서 돌아갈 연습 화면 경로 (예: '/character-practice').
  final String? practiceRoute;

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
    this.preservationMode,
    this.practiceTabs,
    this.practiceTabIndex,
    this.practiceStep,
    this.practiceTotal,
    this.practiceRoute,
  });

  @override
  ConsumerState<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends ConsumerState<FeedbackScreen> {
  bool _isLoading = true;
  String? _errorMessage;

  // /feedback 응답에서만 받아오는 진짜 결과 (score, 메시지)
  int? _overallScore;
  String? _achievementMessage;

  /// /feedback의 **항목별 문구**(종합 1문장을 뺀 나머지 — 크기·기울기·줄 정렬·자간·행간).
  ///
  /// ⚠️ 이미지 모드는 이 값을 통째로 버리고 있었다(2026-09-02 발견). 그래서
  /// **6문장 중 종합 1문장만 화면에 나왔고**, 자간·행간처럼 박스를 안 치는 항목이
  /// 미흡해도 취약 습관 카드는 "훌륭해요"만 보여줬다(사용자 지적).
  List<FeedbackItem> _itemMessages = [];

  // AI 분석 "취약한 습관" + 점수 추세 (백엔드 신규 필드, 없으면 기본값)
  // ⚠️ 목표 점수는 응답이 아니라 사용자 설정(targetScoreProvider)을 사용한다.
  List<WeakHabit> _weakHabits = [];
  int? _scoreTrend;

  // 캔버스 모드 오버레이 항목
  List<CanvasCorrectionOverlayItem> _canvasItems = [];

  // 이미지 모드 오버레이 항목
  List<ImageBBoxOverlayItem> _imageItems = [];

  // /analyze-detail 응답(문자별 필압/속도/교정 플래그/복수 정본 안내) — char_id로 조회.
  // DATA_FLOW.md §7.3/§8-B·C·D: 예전엔 이 응답 자체를 파싱하지 않아 전부 버려졌다.
  Map<String, CanvasCharAnalysis> _canvasAnalysisByChar = {};

  // /analyze 응답(자간·행간 균등성 점수 포함) — DATA_FLOW.md §5-8
  ImageAnalysisResponse? _imageAnalysis;

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

  /// 상단 연습 컨텍스트 헤더(탭/진행률)를 그릴 수 있는지 여부.
  bool get _hasPracticeHeader =>
      widget.practiceTabs != null && widget.practiceTabs!.isNotEmpty;

  Future<void> _loadFeedback() async {
    try {
      if (_isCanvas) {
        await _loadCanvasFeedback();
      } else {
        await _loadImageFeedback();
      }
    } on ApiException catch (e) {
      debugPrint('[Feedback] _loadFeedback error: $e');
      setState(() => _errorMessage =
          e.serverMessage ?? '피드백을 불러오지 못했습니다. 다시 시도해주세요.');
    } catch (e, st) {
      debugPrint('[Feedback] _loadFeedback error: $e\n$st');
      setState(() => _errorMessage = '피드백을 불러오지 못했습니다. 다시 시도해주세요.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _loadCanvasFeedback() async {
    // SFR-004C: 문자 단위 bounding box
    final groupResponse = await CanvasApiService.group(widget.sessionId);
    // SFR-005C: 획순/자간/크기 분석 (인증 필요) — feedback()이 참조할 서버 캐시를 채운다.
    // 종합 점수는 여전히 feedback()에서만 받지만, 이 응답에만 실리는 문자별
    // 필압/속도/교정 플래그/복수 정본 안내는 여기서 받아 상세 바텀시트에 쓴다.
    final idToken = await ref.read(authControllerProvider.notifier).getCurrentIdToken();
    final analysisResponse =
        await CanvasApiService.analyzeDetail(widget.sessionId, idToken: idToken);
    // SFR-007: 문자별 severity + 메시지 + 최종 종합 점수 (진짜 점수는 여기서만 나옴)
    final feedbackResponse = await CanvasApiService.feedback(widget.sessionId);

    setState(() {
      _canvasItems = CanvasCorrectionOverlayItem.merge(
        charGroups: groupResponse.charGroups,
        feedbackItems: feedbackResponse.feedbackItems,
      );
      _overallScore = feedbackResponse.overallScore;
      _achievementMessage = feedbackResponse.achievementMessage;
      _itemMessages = feedbackResponse.feedbackItems;
      _weakHabits = feedbackResponse.weakHabits;
      _scoreTrend = feedbackResponse.scoreTrend;
      _lowConfidenceCount = groupResponse.lowConfidenceCount;
      _canvasAnalysisByChar = analysisResponse.byCharId();
    });
  }

  Future<void> _loadImageFeedback() async {
    // SFR-004I: 문자 검출 bounding box
    final detectResponse = await ImageApiService.detect(widget.sessionId);
    // SFR-005I: 크기 균일성/기울기/줄 정렬 분석 (인증 필요) — feedback()이 참조할 서버 캐시를 채운다.
    // 종합 점수는 여전히 feedback()에서만 받지만, 이 응답에만 실리는 자간·행간
    // 균등성 점수는 여기서 받아 점수 카드에 함께 보여준다.
    final idToken = await ref.read(authControllerProvider.notifier).getCurrentIdToken();
    final analysisResponse =
        await ImageApiService.analyze(widget.sessionId, idToken: idToken);
    // SFR-007: 피드백 (현재는 target_id="global"만 옴 — 문서 참고) + 최종 종합 점수
    final feedbackResponse = await ImageApiService.feedback(widget.sessionId);

    setState(() {
      _imageItems = ImageBBoxOverlayItem.merge(
        detectedChars: detectResponse.detectedChars,
        // 색 판정은 /analyze가 글자마다 내려준다. /feedback의 항목별 문구는
        // 문서 전체(target_id="global")에 대한 것이라 박스와 짝짓지 않는다.
        charBoxes: analysisResponse.charBoxes,
      );
      _overallScore = feedbackResponse.overallScore;
      _achievementMessage = feedbackResponse.achievementMessage;
      _itemMessages = feedbackResponse.feedbackItems;
      _weakHabits = feedbackResponse.weakHabits;
      _scoreTrend = feedbackResponse.scoreTrend;
      _detectedCount = detectResponse.totalDetected;
      _imageAnalysis = analysisResponse;
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
        // 저장 완료 안내는 FeedbackActionBar의 초록 체크 문구로만 노출한다.
        // (하단 SnackBar까지 띄우면 "학습 기록을 저장했어요."가 중복돼 제거함)
        setState(() => _confirmed = true);
      }
    } on ApiException catch (e) {
      // REQ-009-5는 "네트워크 장애" 시에만 로컬 큐에 저장하도록 요구한다.
      // 연결 실패(statusCode == null)만 큐에 넣어 연결 복구 후 자동 재시도하고,
      // 서버가 응답한 4xx/5xx(statusCode != null)는 재시도해도 같은 이유로 실패하므로
      // 큐에 넣지 않고 즉시 실패로 안내한다 (무한 재시도 방지).
      if (e.statusCode == null) {
        await _enqueueForRetry();
      } else {
        _showSaveFailed(e.serverMessage ??
            '저장에 실패했습니다 (오류 ${e.statusCode}). 잠시 후 다시 시도해주세요.');
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
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('분석 결과'),
        // 캔버스/문장 연습 화면에서 context.go()로 넘어온 화면이라 시스템 back으로
        // 되돌아갈 곳이 없을 수 있다 — "학습 기록 저장"을 누르기 전에도 홈으로
        // 돌아갈 수 있어야 하므로 항상 홈 이동 버튼을 둔다.
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: '홈으로',
          onPressed: () {
            if (_confirmed) {
              ref.read(dashboardRefreshProvider.notifier).state++;
            }
            context.go('/home');
          },
        ),
        // 다운로드는 하단 FeedbackActionBar로 옮겼다 — 서버 저장과 나란히 놓아
        // "기기로 받기"와 "서버에 저장"이 구분되게 하기 위함.
        actions: [
          if (!_isLoading && _errorMessage == null)
            IconButton(
              tooltip: _showOverlay ? '오버레이 숨기기' : '오버레이 보이기',
              icon: Icon(_showOverlay ? Icons.visibility_rounded : Icons.visibility_off_rounded),
              onPressed: () => setState(() => _showOverlay = !_showOverlay),
            ),
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
        if (_hasPracticeHeader) _buildPracticeHeader(),
        Expanded(child: _buildResultArea(context)),
        const Divider(height: 1),
        FeedbackActionBar(
          isCanvas: _isCanvas,
          confirmed: _confirmed,
          isConfirming: _isConfirming,
          isDownloading: _isDownloading,
          saveImageConsent: _saveImageConsent,
          onConsentChanged: (v) => setState(() => _saveImageConsent = v),
          onConfirm: _onConfirm,
          onDownload: _downloadFeedbackImage,
          onGoHome: () {
            // 방금 세션 완료로 연속 출석일이 바뀌었을 수 있으니 홈 화면이 대시보드
            // 요약을 다시 불러오도록 신호를 보낸다 (dashboard_refresh_provider.dart).
            ref.read(dashboardRefreshProvider.notifier).state++;
            context.go('/home');
          },
        ),
      ],
    );
  }

  /// 결과 본문 — 넓으면 좌(캔버스)/우(점수·AI분석) 2단, 좁으면 세로 스택.
  Widget _buildResultArea(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 720;
        if (wide) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  flex: 3,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(child: _buildOverlayCard(context)),
                      // 비침 안내는 오버레이(네모가 그려진 곳) 바로 아래에 붙인다
                      ..._buildPreservationNotice(),
                    ],
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  flex: 2,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildScoreCard(context),
                      const SizedBox(height: 16),
                      Expanded(child: _buildWeakHabitCard(context, scrollable: true)),
                    ],
                  ),
                ),
              ],
            ),
          );
        }

        // 좁은 화면: 세로로 쌓아 스크롤
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(height: 300, child: _buildOverlayCard(context)),
              ..._buildPreservationNotice(),
              const SizedBox(height: 16),
              _buildScoreCard(context),
              const SizedBox(height: 16),
              _buildWeakHabitCard(context, scrollable: false),
            ],
          ),
        );
      },
    );
  }

  /// 헤더 탭을 눌러 해당 연습 탭(자음/모음/받침)으로 자유롭게 이동한다.
  /// (연습 화면 첫 글자부터 시작 — charIndex 0)
  void _goToTab(int tabIndex) {
    final route = widget.practiceRoute ?? '/character-practice';
    context.go(route, extra: {'tabIndex': tabIndex, 'charIndex': 0});
  }

  /// 진행률 옆 "다음 글자 →": 같은 탭의 다음 글자로 이동한다(마지막이면 처음으로 순환).
  void _goNextChar() {
    final step = widget.practiceStep;
    final total = widget.practiceTotal;
    if (step == null || total == null || total <= 0) return;
    final route = widget.practiceRoute ?? '/character-practice';
    final nextIndex = step % total; // step은 1-based 현재 위치 → 다음 0-based 인덱스
    context.go(route,
        extra: {'tabIndex': widget.practiceTabIndex ?? 0, 'charIndex': nextIndex});
  }

  /// 상단 연습 컨텍스트 헤더: 탭(탭하면 이동) + 진행률 + 다음 글자.
  Widget _buildPracticeHeader() {
    final tabs = widget.practiceTabs!;
    final index = widget.practiceTabIndex ?? 0;
    final step = widget.practiceStep;
    final total = widget.practiceTotal;
    final hasProgress = step != null && total != null && total > 0;
    final progress = hasProgress ? (step! / total!).clamp(0.0, 1.0) : null;

    return Container(
      color: Colors.white,
      child: Column(
        children: [
          // 탭 바 — 탭하면 해당 연습 탭으로 이동(자유 이동)
          Container(
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppTheme.line)),
            ),
            child: Row(
              children: List.generate(tabs.length, (i) {
                final selected = i == index;
                return Expanded(
                  child: InkWell(
                    onTap: () => _goToTab(i),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(
                        border: Border(
                          bottom: BorderSide(
                            color: selected ? AppTheme.primaryColor : Colors.transparent,
                            width: 2,
                          ),
                        ),
                      ),
                      child: Text(
                        tabs[i],
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                          color: selected ? AppTheme.primaryDark : AppTheme.inkMuted,
                        ),
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
          if (hasProgress) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
              child: Row(
                children: [
                  Text('진행률: $step/$total',
                      style: const TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
                  const Spacer(),
                  Text('${(progress! * 100).round()}%',
                      style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.primaryDark)),
                  const SizedBox(width: 12),
                  InkWell(
                    onTap: _goNextChar,
                    borderRadius: BorderRadius.circular(6),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                      // 마지막 글자면 "처음 자음/모음/받침으로", 아니면 "다음 글자 →"
                      // (단위는 현재 탭 라벨 첫 단어에서 가져온다: '자음 쓰기' → '자음')
                      child: Text(
                        step == total
                            ? '↺ 처음 ${tabs[index].split(' ').first}으로'
                            : '다음 글자 →',
                        style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.primaryDark),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 6,
                  backgroundColor: AppTheme.line,
                  valueColor: const AlwaysStoppedAnimation(AppTheme.primaryColor),
                ),
              ),
            ),
          ] else
            const SizedBox(height: 8),
        ],
      ),
    );
  }

  /// 좌측: 필기 재현 + 교정 오버레이를 카드에 담아 표시.
  Widget _buildOverlayCard(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppTheme.radiusMd),
      // 다운로드 시 이 RepaintBoundary 하위(배경 + 교정 오버레이)를 PNG로 캡처한다.
      child: RepaintBoundary(
        key: _overlayCaptureKey,
        child: Container(
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            border: Border.all(color: AppTheme.line),
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          ),
          clipBehavior: Clip.antiAlias,
          child: _isCanvas ? _buildCanvasOverlay() : _buildImageOverlay(),
        ),
      ),
    );
  }

  /// 보존 모드 사진에만 안내를 끼워 넣는다. 위젯 자체는
  /// [PreservationNotice] 참고(왜 걸러내지 않고 안내만 하는지 포함).
  List<Widget> _buildPreservationNotice() {
    if (widget.preservationMode != true) return const [];
    return const [SizedBox(height: 12), PreservationNotice()];
  }

  /// 우측 상단: 현재 점수 카드 (목표 대비 진행바 + 추세 배지).
  Widget _buildScoreCard(BuildContext context) {
    final score = _overallScore ?? 0;
    // 목표 점수는 사용자 설정값(설정 화면에서 변경) — 백엔드 응답이 아님.
    final target = ref.watch(targetScoreProvider);
    final safeTarget = target <= 0 ? 90 : target;
    final ratio = (score / safeTarget).clamp(0.0, 1.0);

    return HaneumCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('현재 점수',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppTheme.inkMuted)),
              const Spacer(),
              if (!_isCanvas && _imageAnalysis?.totalGrade != null) ...[
                _buildGradeBadge(_imageAnalysis!.totalGrade!),
                const SizedBox(width: 6),
              ],
              if (_scoreTrend != null) _buildTrendBadge(_scoreTrend!),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('$score',
                  style: const TextStyle(
                      fontSize: 40,
                      height: 1.0,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.primaryDark)),
              const Padding(
                padding: EdgeInsets.only(bottom: 6, left: 4),
                child: Text('점',
                    style: TextStyle(fontSize: 14, color: AppTheme.inkMuted)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: ratio,
              minHeight: 8,
              backgroundColor: AppTheme.line,
              valueColor: const AlwaysStoppedAnimation(AppTheme.primaryColor),
            ),
          ),
          const SizedBox(height: 6),
          Text('목표: $safeTarget점',
              style: const TextStyle(fontSize: 12, color: AppTheme.inkFaint)),
          if (_achievementMessage != null && _achievementMessage!.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(_achievementMessage!,
                style: const TextStyle(
                    fontSize: 12.5, height: 1.35, color: AppTheme.inkMuted)),
          ],
          if (!_isCanvas) ..._buildImageSubScores(),
        ],
      ),
    );
  }

  /// 이미지 모드 **세부 점수 5항목** + 기울기 방향 + 명료도 경고.
  ///
  /// 2026-09-02 — 종전에는 자간·행간 둘만 그려서, 화면에 실제로는 **2줄만** 떴다
  /// (행간은 3행 미만이면 미측정이라 자주 빠져 자간 하나만 남기도 했다). 정작
  /// 종합 점수를 좌우하는 크기·기울기·줄 정렬은 응답에 실려 오는데도 한 번도
  /// 안 보여줬다 — 점수가 왜 그렇게 나왔는지 화면에서 알 수 없었다.
  /// 이제 채점 항목 5개를 그대로 다 그린다(문구 6문장과 같은 항목·같은 순서).
  ///
  /// 측정 불가(글자/행 수 부족)면 null이라 그 줄은 '미측정'으로 표시한다 —
  /// 0점으로 그리면 재지도 않은 지표로 감점된 것처럼 읽힌다(DATA_FLOW §4-1).
  List<Widget> _buildImageSubScores() {
    final a = _imageAnalysis;
    if (a == null) return const [];
    final warnings = a.clarityWarnings;

    final rows = <(String, int?)>[
      ('크기 균일성', a.sizeUniformityScore),
      ('기울기 균일성', a.slantConsistencyScore),
      ('줄 정렬', a.lineAlignmentScore),
      ('자간 균등성', a.spacingUniformityScore),
      ('행간 균등성', a.lineSpacingUniformityScore),
    ];
    // 하나도 못 잰 사진이면(글자 수 부족 등) 구분선만 덩그러니 남기지 않는다.
    if (rows.every((r) => r.$2 == null) && warnings.isEmpty) return const [];

    return [
      const SizedBox(height: 12),
      const Divider(height: 1, color: AppTheme.line),
      const SizedBox(height: 10),
      for (final (i, r) in rows.indexed) ...[
        if (i > 0) const SizedBox(height: 6),
        _buildSubScoreRow(r.$1, r.$2),
      ],
      if (a.overallTilt != null) ...[
        const SizedBox(height: 6),
        _buildTiltRow(a.overallTilt!),
      ],
      if (warnings.isNotEmpty) ...[
        const SizedBox(height: 10),
        _buildClarityWarnings(warnings),
      ],
    ];
  }

  /// 항목 한 줄. [score]가 null이면 **'미측정'** — 0점이 아니다.
  Widget _buildSubScoreRow(String label, int? score) {
    final measured = score != null;
    return Row(
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        const Spacer(),
        Text(measured ? '$score점' : '미측정',
            style: TextStyle(
                fontSize: 12,
                fontWeight: measured ? FontWeight.w700 : FontWeight.w500,
                color: measured ? AppTheme.ink : AppTheme.inkFaint)),
      ],
    );
  }

  /// "우수"/"보통"/"불량" 종합 등급 배지 — 색은 좋음=민트, 보통=주황, 나쁨=빨강.
  Widget _buildGradeBadge(String grade) {
    final Color bg;
    final Color fg;
    switch (grade) {
      case '우수':
        bg = AppTheme.mintSurface;
        fg = AppTheme.primaryDark;
        break;
      case '불량':
        bg = const Color(0xFFFDECEC);
        fg = AppTheme.errorColor;
        break;
      default: // "보통" 등 그 외
        bg = AppTheme.amberBg;
        fg = AppTheme.amberText;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Text(grade,
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: fg)),
    );
  }

  /// 글줄 방향 — 점수가 아니라 "줄 정렬"을 어느 쪽으로 고쳐야 하는지 알려주는 줄.
  ///
  /// ⚠️ 서버가 보내는 값은 `"straight" | "falling" | "rising"`이다. 종전에는 여기서
  /// `leaning_right`/`leaning_left`를 찾고 있어 **어떤 사진을 넣어도 default로 빠져
  /// 늘 "반듯하게 썼어요"** 가 떴다(2026-09-02 발견). 값 이름이 한 번도 맞은 적이 없다.
  Widget _buildTiltRow(String tilt) {
    final (icon, label) = switch (tilt) {
      'falling' => (Icons.trending_down_rounded, '오른쪽으로 내려가요'),
      'rising' => (Icons.trending_up_rounded, '오른쪽으로 올라가요'),
      _ => (Icons.straighten_rounded, '반듯하게 썼어요'),
    };
    return Row(
      children: [
        const Text('전체 기울기',
            style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        const Spacer(),
        Icon(icon, size: 14, color: AppTheme.inkMuted),
        const SizedBox(width: 4),
        Text(label,
            style: const TextStyle(
                fontSize: 12, fontWeight: FontWeight.w600, color: AppTheme.ink)),
      ],
    );
  }

  /// 명료도 경고 목록(점수엔 반영 안 됨 — 촬영 품질 관련 안내만).
  Widget _buildClarityWarnings(List<String> warnings) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppTheme.amberBg,
        borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final w in warnings)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.info_outline_rounded,
                      size: 14, color: AppTheme.amberText),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(w,
                        style: const TextStyle(
                            fontSize: 11.5, color: AppTheme.amberText)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  /// 점수 추세 배지 (↗ +N / ↘ -N). trend가 0이면 변화 없음으로 중립 표시.
  Widget _buildTrendBadge(int trend) {
    final up = trend >= 0;
    final color = up ? AppTheme.primaryDark : AppTheme.errorColor;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.mintSurface,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(up ? Icons.trending_up_rounded : Icons.trending_down_rounded,
              size: 14, color: color),
          const SizedBox(width: 3),
          Text('${up ? '+' : ''}$trend',
              style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.w700, color: color)),
        ],
      ),
    );
  }

  /// 이미지 모드에서 걸린 사유별 글자 수. 많이 걸린 것부터 위에 온다.
  Map<String, int> _imageReasonCounts(List<ImageBBoxOverlayItem> reds) {
    final counts = <String, int>{};
    for (final c in reds) {
      for (final reason in c.failedItems) {
        counts[reason] = (counts[reason] ?? 0) + 1;
      }
    }
    final sorted = counts.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return {for (final e in sorted) e.key: e.value};
  }

  /// 우측 하단: AI 분석 "취약한 습관" 패널.
  ///
  /// ⚠️ [_weakHabits]는 백엔드 CanvasFeedbackResponse/ImageFeedbackResponse 스키마에
  /// 아직 `weak_habits` 필드 자체가 없어(schemas/canvas.py, schemas/image.py 확인)
  /// 항상 빈 리스트다 — 그래서 예전엔 이 카드가 항상 "준비 중"만 보여줬다.
  /// 대신 이미 화면 왼쪽 오버레이에 쓰고 있는 실제 문자별 피드백
  /// (_canvasItems/_imageItems의 severity+message)을 여기서도 같은 색으로
  /// 보여준다 — 캔버스 위 박스를 하나하나 탭하지 않아도 오른쪽에서 한눈에 보이도록.
  Widget _buildWeakHabitCard(BuildContext context, {required bool scrollable}) {
    // ⚠️ 캔버스는 **성분 박스 판정**을 기준으로 삼는다. 종전에는 글자 단위 severity
    // (종합 점수 80/50)로 걸렀는데, 박스 색은 **항목별 OR**이라 둘이 어긋났다 —
    // 종합 82점(=good)이면 성분이 빨개도 카드가 비고 "모든 글자가 기준을 잘
    // 지켰어요"까지 떴다(2026-09-01 사용자 지적). 빨간 박스엔 반드시 이유가 따라야 한다.
    final redComponents = _isCanvas
        ? ComponentOverlayItem.fromAnalyses(_canvasAnalysisByChar.values.toList())
            .where((c) => !c.ok)
            .toList()
        : const <ComponentOverlayItem>[];

    // 캔버스는 성분(초·중·종성) 단위, 이미지는 글자 단위지만 규칙은 같다 —
    // **서버가 항목별로 판정한 결과**만 모은다. 종합 점수로 다시 거르지 않는다
    // (그러면 한 항목을 크게 틀려도 다른 항목이 끌어올려 빠져나간다).
    // 캔버스는 위 redComponents 분기가 성분 단위로 이미 처리한다. 여기는 **이미지
    // 모드**의 글자 단위 목록이다. 규칙은 같다 — 서버가 항목별로 판정한 결과만
    // 모으고, 종합 점수로 다시 거르지 않는다(그러면 한 항목을 크게 틀려도 다른
    // 항목이 끌어올려 빠져나간다).
    final redChars = _isCanvas
        ? const <ImageBBoxOverlayItem>[]
        : _imageItems.where((i) => !i.ok).toList();
    final hasRedBoxes = redComponents.isNotEmpty || redChars.isNotEmpty;
    // 항목별 문구 중 **경고만** 추린다. 칭찬(good)은 점수 카드가 이미 숫자로
    // 보여주므로 취약 습관 카드에 또 쓰면 카드 이름과 어긋난다.
    //
    // ⚠️ **이미지 모드에서만** 쓴다. 캔버스의 feedback_items는 항목별이 아니라
    // **글자별**이고, severity가 그 글자의 **종합 점수**에서 나온다 — 그걸 여기
    // 섞으면 "종합 82점이라 good인데 성분 박스는 빨강"인 옛 불일치가 되살아난다
    // (2026-09-01에 고친 것). 캔버스는 redComponents가 이미 항목별 판정이다.
    final itemWarnings = _isCanvas
        ? const <FeedbackItem>[]
        : _itemMessages.where((f) => f.severity != 'good').toList();
    // 아무것도 못 잰 상태(글자 0자 등)와 "다 잘 썼다"를 구분한다 — 안 잰 것을
    // 칭찬으로 바꿔 읽으면 안 된다(DATA_FLOW §4-1).
    final measuredSomething = _itemMessages.isNotEmpty ||
        (_isCanvas ? _canvasItems.isNotEmpty : _imageItems.isNotEmpty);

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Icon(Icons.warning_amber_rounded, size: 18, color: AppTheme.amberText),
            const SizedBox(width: 6),
            const Text('AI 분석: 취약한 습관',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.ink)),
          ],
        ),
        const SizedBox(height: 14),
        if (_weakHabits.isNotEmpty) ...[
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _weakHabits
                .map((h) => HabitBadge(label: h.label, count: h.countLabel))
                .toList(),
          ),
          const SizedBox(height: 14),
          const Text('이 부분들을 신경써서 다시 써볼까요?',
              style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        ],
        if (redComponents.isNotEmpty) ...[
          // 성분마다 어느 항목이 걸렸는지 그대로 보여준다 — 빨간 박스를 일일이
          // 눌러보지 않아도 오른쪽에서 한눈에 읽히도록.
          ...redComponents.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.close_rounded,
                        size: 16, color: Color(0xFFFF3B30)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        '${c.role} "${c.jamo}" — ${c.failedItems.join(', ')}',
                        style: const TextStyle(
                            fontSize: 12.5, height: 1.4, color: AppTheme.ink),
                      ),
                    ),
                  ],
                ),
              )),
          const SizedBox(height: 4),
          const Text('빨간 표시가 고칠 곳이에요.',
              style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        ],
        if (redChars.isNotEmpty) ...[
          // 무엇이 걸렸는지 **사유별로 묶어** 몇 자인지 보여준다.
          //
          // 캔버스는 성분마다 자모('초성 "ㄱ"')를 붙일 수 있지만 이미지 모드에는
          // 붙일 이름이 없다 — char_id는 'char_3' 같은 내부 식별자라 화면에 쓰지
          // 않기로 했다. 그래서 글자마다 한 줄씩 뽑으면 **똑같은 문구가 그대로
          // 반복**된다(빨간 글자 3자면 "크기(너무 큼)" 세 줄). 어느 글자인지는
          // 사진 위의 빨간 박스가 이미 가리키고 있으므로, 여기서는 "무엇이 몇 자"만
          // 알려주는 게 읽기 쉽다.
          ..._imageReasonCounts(redChars).entries.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.close_rounded,
                        size: 16, color: Color(0xFFFF3B30)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        '${e.key} — ${e.value}자',
                        style: const TextStyle(
                            fontSize: 12.5, height: 1.4, color: AppTheme.ink),
                      ),
                    ),
                  ],
                ),
              )),
          const SizedBox(height: 4),
          const Text('빨간 표시가 고칠 곳이에요.',
              style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        ],

        // ── 항목별 경고 ────────────────────────────────────────────────
        // 빨간 박스와 **함께** 보여준다(둘 중 하나가 아니다). 자간·행간처럼 글자
        // 하나에 귀속되지 않는 항목은 박스를 안 치므로, 박스만 보고 판단하면
        // 80점 미만인 항목이 있는데도 "훌륭해요"가 뜬다(2026-09-02 사용자 지적).
        if (itemWarnings.isNotEmpty) ...[
          if (hasRedBoxes) const SizedBox(height: 12),
          ...itemWarnings.map((f) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.error_outline_rounded,
                        size: 16, color: AppTheme.amberText),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        f.feedbackMessage,
                        style: const TextStyle(
                            fontSize: 12.5, height: 1.4, color: AppTheme.ink),
                      ),
                    ),
                  ],
                ),
              )),
        ],

        // ── 다 통과했을 때만 칭찬 ──────────────────────────────────────
        // 박스도 깨끗하고 **항목별 경고도 없어야** 한다.
        if (!hasRedBoxes && itemWarnings.isEmpty)
          if (measuredSomething)
            const Text(
              '모든 항목이 기준을 잘 지켰어요! 훌륭해요 🎉',
              style: TextStyle(fontSize: 12.5, height: 1.4, color: AppTheme.inkMuted),
            )
          else
          const Text(
            'AI 취약 습관 분석을 준비 중이에요.\n잠시 후 다시 확인해 주세요.',
            style: TextStyle(fontSize: 12.5, height: 1.4, color: AppTheme.inkFaint),
          ),
      ],
    );

    return HaneumCard(
      child: scrollable
          ? SingleChildScrollView(child: body)
          : body,
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
            .showSnackBar(const SnackBar(content: Text('이미지를 기기에 받았어요.')));
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

    // 2026-09-01: 박스 단위를 음절 → **성분(초·중·종성)**으로 내렸다.
    // 채점 단위가 성분인데 박스가 음절이면 빨간 박스를 봐도 뭐가 문제인지 알 수 없다.
    final analyses = _canvasAnalysisByChar.values.toList();
    final componentItems = ComponentOverlayItem.fromAnalyses(analyses);
    // 문장은 성분 박스가 수십 개(실측 최대 45개)라 전부 칠하면 글씨가 안 보인다.
    // 잘 쓴 곳은 비우고 고칠 곳만 빨강으로 — 한 글자 연습은 최대 3개라 초록도 그린다.
    final redOnly = analyses.length > 1;

    return ComponentOverlayView(
      // ⚠️ 오버레이 박스는 CanvasCoordinateMapper가 원본 크기를 BoxFit.contain으로
      // 화면에 맞게 스케일링해서 그린다. 배경(StrokePainter)도 똑같은 스케일 기준을
      // 쓰지 않으면 획이 잘리거나 오버레이와 위치가 안 맞는다 — 그래서 원본 크기의
      // SizedBox로 감싼 뒤 FittedBox(contain)로 똑같이 축소한다.
      background: FittedBox(
        fit: BoxFit.contain,
        child: SizedBox(
          width: metadata.width.toDouble(),
          height: metadata.height.toDouble(),
          child: CustomPaint(
            // 격자(showGrid)는 필기 보조선이므로 결과 배경에는 넣지 않는다.
            painter: StrokePainter(
              strokes: widget.strokes!,
              strokeWidth: widget.strokeWidth ?? 4.0,
            ),
          ),
        ),
      ),
      sourceWidth: metadata.width.toDouble(),
      sourceHeight: metadata.height.toDouble(),
      items: componentItems,
      redOnly: redOnly,
      showOverlay: _showOverlay,
      onItemTap: (item) => _showFeedbackSheet(
        charId: item.charId,
        message: _componentMessage(item),
        canvasAnalysis: _canvasAnalysisByChar[item.charId],
      ),
    );
  }

  /// 성분 박스를 눌렀을 때 보여줄 문구.
  ///
  /// 어느 **항목**이 걸렸는지를 그대로 알려준다 — 서버가 항목을 따로 판정해
  /// `failedItems`에 담아 보내므로, 앱이 점수로 다시 추측하지 않는다.
  String _componentMessage(ComponentOverlayItem item) {
    final where = '${item.role} "${item.jamo}"';
    if (item.ok) return '$where — 잘 썼습니다.';
    return '$where — 고칠 곳: ${item.failedItems.join(', ')}';
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
        // 2026-09-01부터 글자마다 판정이 내려온다 — 종전의 '지원되지 않습니다'
        // 안내는 더 이상 필요 없다.
        message: item.message,
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

  void _showFeedbackSheet({
    required String charId,
    required String message,
    CanvasCharAnalysis? canvasAnalysis,
  }) {
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
            if (canvasAnalysis != null) ..._buildCanvasCharDetail(canvasAnalysis),
          ],
        ),
      ),
    );
  }

  /// 문자 상세 바텀시트 하단부: 교정 플래그 · 복수 정본 안내 · 필압/속도.
  /// DATA_FLOW.md §7.3/§8-B·C·D — 이전에는 파싱조차 안 됐던 값들.
  List<Widget> _buildCanvasCharDetail(CanvasCharAnalysis analysis) {
    final widgets = <Widget>[];

    // analyze-detail이 문자별로 내려주는 점수 — 파싱은 되고 있었지만 화면에는
    // 한 번도 그려지지 않았다(전체 점수는 /feedback에서만 표시됨).
    widgets.add(Row(
      children: [
        const Text('이 글자 점수',
            style: TextStyle(fontSize: 12, color: AppTheme.inkMuted)),
        const SizedBox(width: 6),
        // 잰 항목이 하나도 없으면 점수가 없다(null) — 0점으로 보여주면
        // "못 쟀다"가 "형편없다"로 뒤바뀐다.
        Text(analysis.overallScore == null
                ? '미측정'
                : '${analysis.overallScore}점',
            style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: AppTheme.primaryDark)),
      ],
    ));
    widgets.add(const SizedBox(height: 10));

    if (analysis.correctionFlags.isNotEmpty) {
      widgets.add(Wrap(
        spacing: 6,
        runSpacing: 6,
        children: analysis.correctionFlags
            .map((f) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: AppTheme.amberBg,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    CanvasCharAnalysis.flagLabel(f),
                    style: const TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.amberText),
                  ),
                ))
            .toList(),
      ));
      widgets.add(const SizedBox(height: 12));
    }

    final notes = analysis.strokeOrderResult?.notes ?? const [];
    if (notes.isNotEmpty) {
      widgets.add(Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: AppTheme.mintSurface,
          borderRadius: BorderRadius.circular(AppTheme.radiusSm),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: notes
              .map((n) => Text(n,
                  style: const TextStyle(
                      fontSize: 12, height: 1.4, color: AppTheme.primaryDark)))
              .toList(),
        ),
      ));
      widgets.add(const SizedBox(height: 12));
    }

    widgets.add(Row(
      children: [
        Icon(Icons.speed_rounded, size: 15, color: AppTheme.inkFaint),
        const SizedBox(width: 4),
        Text(
          '평균 속도 ${analysis.motion.meanSpeedPxPerMs.toStringAsFixed(2)}px/ms',
          style: const TextStyle(fontSize: 11.5, color: AppTheme.inkMuted),
        ),
      ],
    ));

    return widgets;
  }
}

/// 우측 "AI 분석" 패널의 문자 하나에 대한 피드백.
///
/// 캔버스 모드는 획순/자간/크기 세 문장이 공백으로 붙은 문자열 하나로 온다
/// (feedback_generator.py) — [parseCanvasFeedbackParts]로 다시 나눠서 각 문장을
/// 그 문장 고유의 색(적절=초록/문제=주황)으로 줄바꿈해 보여준다. 캔버스 위 박스에
/// 표시되는 char_id 같은 내부 식별자는 사용자에게 의미가 없어 보여주지 않는다.
/// 패턴이 안 맞으면(이미지 모드 등) 원문 메시지를 그 항목의 종합 severity 색으로
/// 한 줄에 보여준다.
class _FeedbackDetailRow extends StatelessWidget {
  final FeedbackItem feedback;
  const _FeedbackDetailRow({required this.feedback});

  @override
  Widget build(BuildContext context) {
    final parts = parseCanvasFeedbackParts(feedback.feedbackMessage);

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppTheme.scaffold,
        borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      ),
      child: parts.isNotEmpty
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var i = 0; i < parts.length; i++)
                  Padding(
                    // 문장이 끝날 때마다(각 부분 사이) 줄바꿈 + 들여쓰기로 구분한다.
                    padding: EdgeInsets.only(top: i == 0 ? 0 : 8, left: 4),
                    child: _SeverityLine(text: parts[i].text, severity: parts[i].severity),
                  ),
              ],
            )
          : _SeverityLine(
              text: feedback.feedbackMessage,
              severity: feedbackSeverityFromString(feedback.severity),
            ),
    );
  }
}

/// severity 색 원형 배지 + 아이콘 + 텍스트 한 줄 (SeverityStyle 공용 규칙 사용).
class _SeverityLine extends StatelessWidget {
  final String text;
  final FeedbackSeverity severity;
  const _SeverityLine({required this.text, required this.severity});

  @override
  Widget build(BuildContext context) {
    final color = SeverityStyle.color(severity);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 16,
          height: 16,
          margin: const EdgeInsets.only(top: 1),
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          child: Icon(SeverityStyle.icon(severity), size: 10, color: Colors.white),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(text,
              style: TextStyle(fontSize: 12.5, color: color, fontWeight: FontWeight.w600)),
        ),
      ],
    );
  }
}
