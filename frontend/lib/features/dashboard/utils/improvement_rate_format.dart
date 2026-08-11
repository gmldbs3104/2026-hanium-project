/// 향상률(period_summary.improvement_rate) 표시 규칙:
/// 음수(하락)면 숫자를 보여주지 않고 '-'만 표시하고, 0 이상일 때만 실제 값을 %로 보여준다.
String formatImprovementRate(double rate) {
  if (rate < 0) return '-';
  if (rate == 0) return '0%';
  return '+${rate.round()}%';
}
