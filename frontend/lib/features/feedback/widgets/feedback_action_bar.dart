import 'package:flutter/material.dart';

/// 피드백 화면 하단 액션 영역 (SFR-009 저장 + 기기 다운로드)
///
/// 문구 원칙: **"저장" = 서버로, "받기" = 내 기기로.**
/// 두 행위는 목적지가 다르므로 라벨에서 구분한다. 예전에는 하단 "확인 (결과 저장)"과
/// AppBar 다운로드 아이콘이 둘 다 '저장'처럼 읽혀 혼동을 일으켰다.
///
/// 상태를 갖지 않는다. API 호출과 상태 변경은 전부 FeedbackScreen에 남고,
/// 이 위젯은 전달받은 값을 그리고 탭을 콜백으로 넘기기만 한다.
class FeedbackActionBar extends StatelessWidget {
  /// 버튼 활성/비활성 검사를 위해 테스트가 잡을 수 있는 키.
  /// (OutlinedButton.icon은 private 서브클래스를 반환해 find.byType으로 잡히지 않는다)
  static const downloadButtonKey = Key('feedback_action_bar_download');
  static const saveButtonKey = Key('feedback_action_bar_save');
  static const homeButtonKey = Key('feedback_action_bar_home');
  static const consentCheckboxKey = Key('feedback_action_bar_consent');

  /// 캔버스 모드 여부. false(이미지 모드)일 때만 원본 사진 보관 동의를 노출한다 (REQ-009-4).
  final bool isCanvas;

  /// SFR-009 저장이 끝난 상태인지. true면 완료 레이아웃으로 바뀐다.
  final bool confirmed;

  final bool isConfirming;
  final bool isDownloading;
  final bool saveImageConsent;

  final ValueChanged<bool> onConsentChanged;
  final VoidCallback onConfirm;
  final VoidCallback onDownload;
  final VoidCallback onGoHome;

  const FeedbackActionBar({
    super.key,
    required this.isCanvas,
    required this.confirmed,
    required this.isConfirming,
    required this.isDownloading,
    required this.saveImageConsent,
    required this.onConsentChanged,
    required this.onConfirm,
    required this.onDownload,
    required this.onGoHome,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: confirmed ? _buildConfirmed(context) : _buildPending(context),
    );
  }

  /// 저장 완료 후. 동의 체크박스는 노출하지 않는다 — 저장 요청이 이미 끝나
  /// 동의를 바꿔도 반영할 경로가 없기 때문이다.
  Widget _buildConfirmed(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_rounded, color: Colors.green.shade600, size: 20),
            const SizedBox(width: 8),
            const Text('학습 기록을 저장했어요.'),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(child: _buildDownloadButton()),
            const SizedBox(width: 12),
            Expanded(
              child: TextButton(
                key: homeButtonKey,
                onPressed: onGoHome,
                child: const Text(
                  '홈으로',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// 저장 전. 다운로드(기기)와 저장(서버)을 나란히 두고, 주된 행동인 저장에
  /// 더 넓은 폭(flex 2:1)을 줘서 위계를 만든다.
  Widget _buildPending(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (!isCanvas)
          CheckboxListTile(
            key: consentCheckboxKey,
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            dense: true,
            value: saveImageConsent,
            onChanged: (v) => onConsentChanged(v ?? false),
            title: const Text(
              '촬영한 원본 사진도 서버에 보관',
              style: TextStyle(fontSize: 13),
            ),
            subtitle: const Text(
              '체크하지 않으면 분석 결과만 저장되고, 사진은 서버에 남지 않아요.',
              style: TextStyle(fontSize: 11),
            ),
          ),
        Row(
          children: [
            Expanded(flex: 1, child: _buildDownloadButton()),
            const SizedBox(width: 12),
            Expanded(flex: 2, child: _buildSaveButton()),
          ],
        ),
      ],
    );
  }

  Widget _buildDownloadButton() {
    return OutlinedButton.icon(
      key: downloadButtonKey,
      onPressed: isDownloading ? null : onDownload,
      icon: isDownloading
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.download_rounded, size: 18),
      label: const Text(
        '이미지 받기',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }

  Widget _buildSaveButton() {
    return FilledButton(
      key: saveButtonKey,
      onPressed: isConfirming ? null : onConfirm,
      child: isConfirming
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            )
          : const Text(
              '학습 기록 저장',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
    );
  }
}
