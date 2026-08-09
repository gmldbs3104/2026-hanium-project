import 'package:flutter/material.dart';

/// 앱 전역 테마 (SFR-007 Inputs: light / dark 지원)
///
/// 2026 한이음 UI 리디자인: 민트/틸 계열 팔레트로 통일.
/// (기존에 참조되던 상수 이름들[primaryColor/canvasModeColor/imageModeColor/
///  errorColor/successColor/warningColor]은 하위 호환을 위해 유지한다.)
class AppTheme {
  AppTheme._();

  // ── 브랜드 팔레트 (시안 기준) ─────────────────────────────────────────────
  /// 강조 틸(하단 네비 활성/그래프/카메라 버튼 등)
  static const Color primaryColor = Color(0xFF35C4B3);
  static const Color primaryDark = Color(0xFF23A896);

  /// 메인 액션 버튼(민트) — "지금 시작하기" 등
  static const Color mint = Color(0xFF7BD0B8);
  static const Color mintStrong = Color(0xFF6BC6AC);

  /// 비활성/연한 민트 — 비활성 "시작하기" 등
  static const Color mintPale = Color(0xFFCDEDE0);

  /// 카드/배너용 옅은 민트 배경
  static const Color mintSurface = Color(0xFFEAF7F2);
  static const Color bannerStart = Color(0xFFB4E6D6);
  static const Color bannerEnd = Color(0xFF8FD3BC);

  /// 소셜 로그인 색
  static const Color kakaoYellow = Color(0xFFFEE500);
  static const Color appleNavy = Color(0xFF15161F);

  /// 텍스트/보더 그레이 스케일
  static const Color ink = Color(0xFF1F2937);
  static const Color inkMuted = Color(0xFF6B7280);
  static const Color inkFaint = Color(0xFF9CA3AF);
  static const Color line = Color(0xFFE5E7EB);
  static const Color scaffold = Color(0xFFF6F7F9);

  /// 취약 습관 배지(앰버)
  static const Color amberBg = Color(0xFFFCEBD2);
  static const Color amberText = Color(0xFFE08A29);

  // ── 하위 호환용 별칭(기존 코드가 참조) ────────────────────────────────────
  static const Color canvasModeColor = primaryColor;
  static const Color imageModeColor = primaryColor;
  static const Color errorColor = Color(0xFFE5484D);
  static const Color successColor = Color(0xFF2E9E7B);
  static const Color warningColor = amberText;

  // ── 공통 라운드/그림자 토큰 ───────────────────────────────────────────────
  static const double radiusSm = 10;
  static const double radiusMd = 14;
  static const double radiusLg = 20;

  static List<BoxShadow> get cardShadow => const [
        BoxShadow(
          color: Color(0x0F101828),
          blurRadius: 16,
          offset: Offset(0, 6),
        ),
      ];

  static ThemeData get lightTheme => _build(Brightness.light);
  static ThemeData get darkTheme => _build(Brightness.dark);

  /// light/dark 공통 골격. 밝기만 바꿔 ColorScheme를 시드에서 생성한다.
  static ThemeData _build(Brightness brightness) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: primaryColor,
      brightness: brightness,
      primary: brightness == Brightness.light ? primaryColor : primaryColor,
    );
    final isDark = brightness == Brightness.dark;

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: isDark ? colorScheme.surface : Colors.white,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: isDark ? colorScheme.surface : Colors.white,
        foregroundColor: isDark ? colorScheme.onSurface : ink,
        titleTextStyle: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.bold,
          color: isDark ? colorScheme.onSurface : ink,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radiusMd),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
        ),
        filled: true,
        fillColor:
            isDark ? colorScheme.surfaceContainerHighest : Colors.grey.shade50,
      ),
    );
  }
}
