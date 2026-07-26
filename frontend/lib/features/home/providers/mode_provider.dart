import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 분석 모드 (SFR-002 메인 화면 모드 분기)
enum AnalysisMode { canvas, image }

/// 현재 선택된 모드를 앱 상태에 저장 (Action ②: 선택된 모드 플래그를 상태 관리 레이어에 저장)
final selectedModeProvider = StateProvider<AnalysisMode?>((ref) => null);
