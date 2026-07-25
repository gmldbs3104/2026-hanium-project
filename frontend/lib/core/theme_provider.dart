import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 앱 테마 모드 (SFR-007 Inputs: light / dark).
///
/// 기본값은 시스템 설정을 따르며(ThemeMode.system), 사용자가 홈 화면의 테마 메뉴에서
/// 라이트/다크를 명시적으로 고를 수 있다.
///
/// ⚠️ 현재는 인메모리 상태 — 앱 재시작 시 시스템 기본으로 돌아간다.
///    선택 유지가 필요하면 shared_preferences로 영속화(추후).
final themeModeProvider = StateProvider<ThemeMode>((ref) => ThemeMode.system);
