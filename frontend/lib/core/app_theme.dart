import 'package:flutter/material.dart';

/// 앱 전역 테마 (SFR-007 Inputs: light / dark 지원)
class AppTheme {
  AppTheme._();

  static const Color primaryColor = Color(0xFF4361EE);
  static const Color canvasModeColor = Color(0xFF4361EE);
  static const Color imageModeColor = Color(0xFFEF6C00);
  static const Color errorColor = Color(0xFFE53935);
  static const Color successColor = Color(0xFF2E7D32);
  static const Color warningColor = Color(0xFFF9A825);

  static ThemeData get lightTheme => _build(Brightness.light);
  static ThemeData get darkTheme => _build(Brightness.dark);

  /// light/dark 공통 골격. 밝기만 바꿔 ColorScheme를 시드에서 생성한다.
  static ThemeData _build(Brightness brightness) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: primaryColor,
      brightness: brightness,
    );
    final isDark = brightness == Brightness.dark;

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        filled: true,
        fillColor:
            isDark ? colorScheme.surfaceContainerHighest : Colors.grey.shade50,
      ),
    );
  }
}
