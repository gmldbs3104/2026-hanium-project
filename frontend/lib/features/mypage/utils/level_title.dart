/// 레벨 구간별 칭호. 레벨 산정 자체는 백엔드(dashboard_service.py:
/// `level = 1 + 전체 누적 세션 수 // 5`)가 계산해서 내려주고, 여기서는 그 숫자에
/// 붙일 이름만 프론트에서 정한다(요구사항 문서에 없는 프론트 자체 기능이라 팀 협의 후
/// 조정 가능 — 지금은 임시로 5단계).
class LevelTier {
  final int minLevel;
  final String title;
  const LevelTier(this.minLevel, this.title);
}

const levelTiers = [
  LevelTier(1, '손글씨 초보자'),
  LevelTier(11, '손글씨 연습생'),
  LevelTier(21, '손글씨 숙련자'),
  LevelTier(31, '손글씨 마스터'),
  LevelTier(50, '손글씨 장인'),
];

/// 세션 5회당 1레벨(백엔드 SESSIONS_PER_LEVEL과 동일한 값 — 진행률 계산용).
const sessionsPerLevel = 5;

String levelTitle(int level) {
  var title = levelTiers.first.title;
  for (final tier in levelTiers) {
    if (level >= tier.minLevel) {
      title = tier.title;
    } else {
      break;
    }
  }
  return title;
}

/// 다음 레벨까지 필요한 누적 세션 수(현재 세션 수 기준 잔여량, 0이면 이미 도달).
/// 백엔드 공식 level = 1 + totalSessions // sessionsPerLevel 의 역산.
int sessionsUntilNextLevel(int currentLevel, int totalSessions) {
  final threshold = currentLevel * sessionsPerLevel;
  return (threshold - totalSessions).clamp(0, sessionsPerLevel);
}
