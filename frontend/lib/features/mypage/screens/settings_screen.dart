import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/app_theme.dart';
import '../../../core/target_score_provider.dart';
import '../../../shared/services/api_client.dart';
import '../../auth/providers/auth_controller.dart';
import '../../auth/providers/auth_state.dart';
import '../providers/handwriting_env_provider.dart';
import '../services/settings_api_service.dart';

/// AuthProviderType → 화면에 보여줄 한글 이름 (auth_state.dart의 provider 문자열 기준).
String _providerLabel(String provider) {
  switch (provider) {
    case 'google':
      return '구글';
    case 'kakao':
      return '카카오';
    case 'apple':
      return '애플';
    default:
      return provider;
  }
}

/// 상세환경설정 — 계정/필기 환경/사운드 설정 (필기·사운드는 로컬 UI 상태).
/// 회원탈퇴는 기존 AuthController.deleteAccount()를 그대로 호출한다(백엔드 연동 유지).
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  double _guideOpacity = handwritingEnvDefault.guideOpacity;
  int _boardTheme = handwritingEnvDefault.boardTheme; // 0 무지, 1 격자, 2 줄글, 3 원고지
  double _fontSize = 18;
  bool _vibration = true;
  bool _buttonSound = true;
  bool _ambientSound = false;
  bool _isResettingData = false;

  static const _boardThemes = ['무지', '격자', '줄글', '원고지'];

  @override
  void initState() {
    super.initState();
    // 마지막으로 "저장"한 값을 이어서 보여준다 (handwriting_env_provider.dart).
    final env = ref.read(handwritingEnvProvider);
    _guideOpacity = env.guideOpacity;
    _boardTheme = env.boardTheme;
  }

  /// mypage_upgrade.md 3.4-2: 저장 시 handwritingEnvProvider에 반영한다.
  /// ⚠️ 실제 연습 화면(canvas_input_screen.dart)에 적용하는 건 보류 — 상의 필요.
  void _saveHandwritingEnv() {
    ref.read(handwritingEnvProvider.notifier).state =
        HandwritingEnv(guideOpacity: _guideOpacity, boardTheme: _boardTheme);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('필기 환경 설정이 저장되었습니다. (연습 화면 적용은 준비 중이에요)')),
    );
  }

  /// mypage_upgrade.md 3.4-1: 서버에 쌓인 세션·점수 이력 전체 삭제(계정은 유지).
  /// ⚠️ SettingsApiService.resetHistory()가 부르는 백엔드 엔드포인트는 아직 없다 —
  /// 지금은 호출하면 실패(연결 오류/404)로 안내된다. 백엔드에 엔드포인트가 생기면
  /// 바로 동작한다.
  Future<void> _confirmResetData() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('데이터 초기화'),
        content: const Text('모든 학습 기록이 사라집니다. 정말로 초기화하시겠습니까?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(c, true),
            style: TextButton.styleFrom(foregroundColor: AppTheme.errorColor),
            child: const Text('초기화'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _isResettingData = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final idToken =
          await ref.read(authControllerProvider.notifier).getCurrentIdToken();
      await SettingsApiService.resetHistory(idToken: idToken);
      messenger.showSnackBar(const SnackBar(content: Text('모든 학습 기록이 초기화되었습니다.')));
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(
          content: Text(e.serverMessage ?? '초기화에 실패했습니다. 잠시 후 다시 시도해주세요.')));
    } catch (e) {
      messenger.showSnackBar(const SnackBar(content: Text('초기화에 실패했습니다. 잠시 후 다시 시도해주세요.')));
    } finally {
      if (mounted) setState(() => _isResettingData = false);
    }
  }

  Future<void> _confirmDeleteAccount() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('회원탈퇴'),
        content: const Text(
          '계정을 삭제하면 학습 기록과 저장된 이미지를 포함한 모든 데이터가 삭제되며, '
          '이 작업은 되돌릴 수 없습니다.\n\n정말 탈퇴하시겠어요?',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false),
              child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(c, true),
            style: TextButton.styleFrom(foregroundColor: AppTheme.errorColor),
            child: const Text('탈퇴'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    final success =
        await ref.read(authControllerProvider.notifier).deleteAccount();
    messenger.showSnackBar(
      SnackBar(
        content: Text(success
            ? '계정이 삭제되었습니다.'
            : '계정 삭제에 실패했습니다. 잠시 후 다시 시도해주세요.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final targetScore = ref.watch(targetScoreProvider);
    final authState = ref.watch(authControllerProvider);
    final providerLabel =
        authState is AuthAuthenticated ? _providerLabel(authState.user.provider) : null;
    return Scaffold(
      backgroundColor: AppTheme.scaffold,
      appBar: AppBar(
        leading: const BackButton(),
        title: const Text('상세환경설정'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _Card(
            title: '학습 목표',
            titleIcon: Icons.flag_rounded,
            child: _SliderRow(
              label: '목표 점수',
              valueLabel: '$targetScore점',
              value: targetScore.toDouble(),
              min: 50,
              max: 100,
              divisions: 10,
              minLabel: '50점',
              maxLabel: '100점',
              defaultValue: 90,
              onChanged: (v) =>
                  ref.read(targetScoreProvider.notifier).state = v.round(),
            ),
          ),
          const SizedBox(height: 16),
          _Card(
            title: '계정',
            child: Column(
              children: [
                _RowItem(
                    icon: Icons.link_rounded,
                    iconBg: AppTheme.mintSurface,
                    iconColor: AppTheme.primaryDark,
                    title: '소셜 계정 연동',
                    subtitle: providerLabel ?? '알 수 없음',
                    showChevron: false),
                const Divider(height: 1, color: AppTheme.line),
                _RowItem(
                    icon: Icons.delete_outline_rounded,
                    iconBg: const Color(0xFFFDECD8),
                    iconColor: AppTheme.amberText,
                    title: '데이터 초기화',
                    subtitle: _isResettingData ? '초기화하는 중...' : '모든 학습 기록 삭제',
                    onTap: _isResettingData ? null : _confirmResetData),
                const Divider(height: 1, color: AppTheme.line),
                _RowItem(
                    icon: Icons.person_off_rounded,
                    iconBg: const Color(0xFFFDECEC),
                    iconColor: AppTheme.errorColor,
                    title: '회원탈퇴',
                    titleColor: AppTheme.errorColor,
                    onTap: _confirmDeleteAccount),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _Card(
            title: '필기 환경 설정',
            trailing: TextButton(
              onPressed: _saveHandwritingEnv,
              child: const Text('저장',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SliderRow(
                  label: '가이드 글자 투명도',
                  valueLabel: '${(_guideOpacity * 100).round()}%',
                  value: _guideOpacity,
                  min: 0,
                  max: 1,
                  divisions: 10,
                  minLabel: '투명',
                  maxLabel: '진함',
                  defaultValue: handwritingEnvDefault.guideOpacity,
                  onChanged: (v) => setState(() => _guideOpacity = v),
                ),
                const SizedBox(height: 16),
                const Text('그림판 테마',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.ink)),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: List.generate(_boardThemes.length, (i) {
                    final selected = _boardTheme == i;
                    final isDefault = i == handwritingEnvDefault.boardTheme;
                    return GestureDetector(
                      onTap: () => setState(() => _boardTheme = i),
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: [
                          Container(
                            width: 90,
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: selected
                                  ? AppTheme.mint
                                  : const Color(0xFFEFF1F4),
                              borderRadius:
                                  BorderRadius.circular(AppTheme.radiusSm),
                            ),
                            child: Text(_boardThemes[i],
                                style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: selected
                                        ? Colors.white
                                        : AppTheme.inkMuted)),
                          ),
                          if (isDefault)
                            Positioned(
                              top: -6,
                              right: -6,
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 5, vertical: 2),
                                decoration: BoxDecoration(
                                  color: AppTheme.inkMuted,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: const Text('기본',
                                    style: TextStyle(
                                        fontSize: 9,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w700)),
                              ),
                            ),
                        ],
                      ),
                    );
                  }),
                ),
                const SizedBox(height: 18),
                _SliderRow(
                  label: '전체 글씨 크기 조절',
                  valueLabel: '${_fontSize.round()}px',
                  value: _fontSize,
                  min: 12,
                  max: 28,
                  divisions: 8,
                  minLabel: '작게',
                  maxLabel: '크게',
                  defaultValue: 18,
                  onChanged: (v) => setState(() => _fontSize = v),
                ),
                const SizedBox(height: 12),
                _HandwritingPreview(
                  opacity: _guideOpacity,
                  boardTheme: _boardTheme,
                  fontSize: _fontSize,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _Card(
            title: '사운드',
            titleIcon: Icons.volume_up_rounded,
            child: Column(
              children: [
                _SwitchRow(
                  title: '진동',
                  subtitle: '터치 피드백 진동',
                  value: _vibration,
                  onChanged: (v) => setState(() => _vibration = v),
                ),
                _SwitchRow(
                  title: '버튼',
                  subtitle: '버튼 클릭 효과음',
                  value: _buttonSound,
                  onChanged: (v) => setState(() => _buttonSound = v),
                ),
                _SwitchRow(
                  title: '환경음',
                  subtitle: '집중 모드 배경음',
                  value: _ambientSound,
                  onChanged: (v) => setState(() => _ambientSound = v),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Center(
            child: Text('앱 버전  1.0.0',
                style: TextStyle(fontSize: 12, color: AppTheme.inkFaint)),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final String title;
  final IconData? titleIcon;
  // 제목 줄 우측에 놓는 위젯 (예: 필기 환경 설정의 "저장" 버튼).
  final Widget? trailing;
  final Widget child;
  const _Card(
      {required this.title, this.titleIcon, this.trailing, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: AppTheme.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (titleIcon != null) ...[
                Icon(titleIcon, size: 18, color: AppTheme.ink),
                const SizedBox(width: 6),
              ],
              Text(title,
                  style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.ink)),
              if (trailing != null) ...[
                const Spacer(),
                trailing!,
              ],
            ],
          ),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

class _RowItem extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String? subtitle;
  final Color? titleColor;
  final VoidCallback? onTap;
  final bool showChevron;
  const _RowItem({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    this.onTap,
    this.subtitle,
    this.titleColor,
    this.showChevron = true,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration:
                  BoxDecoration(color: iconBg, shape: BoxShape.circle),
              child: Icon(icon, size: 18, color: iconColor),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: titleColor ?? AppTheme.ink)),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(subtitle!,
                        style: const TextStyle(
                            fontSize: 12, color: AppTheme.inkMuted)),
                  ],
                ],
              ),
            ),
            if (showChevron)
              const Icon(Icons.chevron_right_rounded,
                  color: AppTheme.inkFaint, size: 20),
          ],
        ),
      ),
    );
  }
}

class _SliderRow extends StatelessWidget {
  final String label;
  final String valueLabel;
  final double value;
  final double min;
  final double max;
  final int? divisions;
  final String minLabel;
  final String maxLabel;
  final ValueChanged<double> onChanged;
  // 기본값 위치에 "기본" 마커를 표시한다(있을 때만). 트랙 위 대략적인 위치라
  // 픽셀 단위로 정확하진 않지만 어디가 기본값인지 한눈에 보여주는 용도로 충분하다.
  final double? defaultValue;
  const _SliderRow({
    required this.label,
    required this.valueLabel,
    required this.value,
    required this.min,
    required this.max,
    required this.minLabel,
    required this.maxLabel,
    required this.onChanged,
    this.divisions,
    this.defaultValue,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.ink)),
            Text(valueLabel,
                style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: AppTheme.primaryDark)),
          ],
        ),
        if (defaultValue != null)
          LayoutBuilder(builder: (context, constraints) {
            final fraction =
                ((defaultValue! - min) / (max - min)).clamp(0.0, 1.0);
            return Align(
              alignment: Alignment(fraction * 2 - 1, 0),
              child: const Opacity(
                opacity: 0.6,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.check_circle, size: 11, color: AppTheme.inkMuted),
                    SizedBox(width: 2),
                    Text('기본',
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.inkMuted)),
                  ],
                ),
              ),
            );
          }),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            activeTrackColor: AppTheme.primaryColor,
            inactiveTrackColor: AppTheme.line,
            thumbColor: AppTheme.primaryColor,
            overlayColor: AppTheme.primaryColor.withValues(alpha: 0.15),
            trackHeight: 4,
          ),
          child: Slider(
              value: value,
              min: min,
              max: max,
              divisions: divisions,
              onChanged: onChanged),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(minLabel,
                style: const TextStyle(fontSize: 11, color: AppTheme.inkFaint)),
            Text(maxLabel,
                style: const TextStyle(fontSize: 11, color: AppTheme.inkFaint)),
          ],
        ),
      ],
    );
  }
}

/// 필기 환경 설정 미리보기 — 가이드 글자 투명도·그림판 테마·글씨 크기를 실시간 반영한다
/// (mypage_upgrade.md 3.4-2). 프론트 로컬 상태만으로 그리므로 백엔드와 무관하다.
class _HandwritingPreview extends StatelessWidget {
  final double opacity;
  final int boardTheme; // 0 무지, 1 격자, 2 줄글, 3 원고지
  final double fontSize;
  const _HandwritingPreview({
    required this.opacity,
    required this.boardTheme,
    required this.fontSize,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      child: Container(
        height: 110,
        width: double.infinity,
        color: const Color(0xFFEFF1F4),
        child: Stack(
          alignment: Alignment.center,
          children: [
            Positioned.fill(
              child: CustomPaint(painter: _BoardBackgroundPainter(boardTheme)),
            ),
            Text(
              '미리보기 텍스트',
              style: TextStyle(
                fontSize: fontSize,
                color: AppTheme.ink.withValues(alpha: opacity),
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BoardBackgroundPainter extends CustomPainter {
  final int theme;
  const _BoardBackgroundPainter(this.theme);

  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = AppTheme.line
      ..strokeWidth = 1;

    switch (theme) {
      case 1: // 격자
        const step = 16.0;
        for (double x = step; x < size.width; x += step) {
          canvas.drawLine(Offset(x, 0), Offset(x, size.height), linePaint);
        }
        for (double y = step; y < size.height; y += step) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), linePaint);
        }
        break;
      case 2: // 줄글
        const step = 22.0;
        for (double y = step; y < size.height; y += step) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), linePaint);
        }
        break;
      case 3: // 원고지
        const step = 28.0;
        final boldPaint = Paint()
          ..color = AppTheme.inkFaint
          ..strokeWidth = 1.2;
        for (double x = 0; x <= size.width; x += step) {
          canvas.drawLine(Offset(x, 0), Offset(x, size.height), boldPaint);
        }
        for (double y = 0; y <= size.height; y += step) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), boldPaint);
        }
        break;
      default: // 무지 — 배경만, 선 없음
        break;
    }
  }

  @override
  bool shouldRepaint(covariant _BoardBackgroundPainter oldDelegate) =>
      oldDelegate.theme != theme;
}

class _SwitchRow extends StatelessWidget {
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  const _SwitchRow({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: AppTheme.ink)),
                const SizedBox(height: 2),
                Text(subtitle,
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.inkMuted)),
              ],
            ),
          ),
          Switch(
            value: value,
            onChanged: onChanged,
            activeTrackColor: AppTheme.primaryColor,
          ),
        ],
      ),
    );
  }
}
