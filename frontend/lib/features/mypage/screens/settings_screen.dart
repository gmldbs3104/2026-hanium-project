import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/app_theme.dart';
import '../../auth/providers/auth_controller.dart';

/// 상세환경설정 — 계정/필기 환경/사운드 설정 (필기·사운드는 로컬 UI 상태).
/// 회원탈퇴는 기존 AuthController.deleteAccount()를 그대로 호출한다(백엔드 연동 유지).
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  double _guideOpacity = 0.5;
  int _boardTheme = 0; // 0 무지, 1 격자, 2 줄글, 3 원고지
  double _fontSize = 18;
  bool _vibration = true;
  bool _buttonSound = true;
  bool _ambientSound = false;

  static const _boardThemes = ['무지', '격자', '줄글', '원고지'];

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
            title: '계정',
            child: Column(
              children: [
                _RowItem(
                    icon: Icons.link_rounded,
                    iconBg: AppTheme.mintSurface,
                    iconColor: AppTheme.primaryDark,
                    title: '소셜 계정 연동',
                    onTap: () {}),
                const Divider(height: 1, color: AppTheme.line),
                _RowItem(
                    icon: Icons.delete_outline_rounded,
                    iconBg: const Color(0xFFFDECD8),
                    iconColor: AppTheme.amberText,
                    title: '데이터 초기화',
                    subtitle: '모든 학습 기록 삭제',
                    onTap: () {}),
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
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SliderRow(
                  label: '가이드 글자 투명도',
                  valueLabel: '${(_guideOpacity * 100).round()}%',
                  value: _guideOpacity,
                  min: 0,
                  max: 1,
                  minLabel: '투명',
                  maxLabel: '진함',
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
                    return GestureDetector(
                      onTap: () => setState(() => _boardTheme = i),
                      child: Container(
                        width: 90,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color:
                              selected ? AppTheme.mint : const Color(0xFFEFF1F4),
                          borderRadius:
                              BorderRadius.circular(AppTheme.radiusSm),
                        ),
                        child: Text(_boardThemes[i],
                            style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color:
                                    selected ? Colors.white : AppTheme.inkMuted)),
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
                  minLabel: '작게',
                  maxLabel: '크게',
                  onChanged: (v) => setState(() => _fontSize = v),
                ),
                const SizedBox(height: 12),
                Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEFF1F4),
                      borderRadius: BorderRadius.circular(AppTheme.radiusSm),
                    ),
                    child: Text('미리보기 텍스트',
                        style: TextStyle(
                            fontSize: _fontSize, color: AppTheme.ink)),
                  ),
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
  final Widget child;
  const _Card({required this.title, this.titleIcon, required this.child});

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
  final VoidCallback onTap;
  const _RowItem({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.titleColor,
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
  final String minLabel;
  final String maxLabel;
  final ValueChanged<double> onChanged;
  const _SliderRow({
    required this.label,
    required this.valueLabel,
    required this.value,
    required this.min,
    required this.max,
    required this.minLabel,
    required this.maxLabel,
    required this.onChanged,
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
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            activeTrackColor: AppTheme.primaryColor,
            inactiveTrackColor: AppTheme.line,
            thumbColor: AppTheme.primaryColor,
            overlayColor: AppTheme.primaryColor.withValues(alpha: 0.15),
            trackHeight: 4,
          ),
          child: Slider(
              value: value, min: min, max: max, onChanged: onChanged),
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
