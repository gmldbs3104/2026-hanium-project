import 'dart:math' as math;

import 'package:flutter/material.dart';

/// 획순 가이드 한 획: 획 경로(em 0..1 좌표) + 순서 번호를 그릴 위치.
///
/// 좌표계는 "글자 박스" 기준 0..1 (y는 아래로 증가). 실제 픽셀 매핑은
/// StrokeOrderGuidePainter가 명조체 글자와 같은 박스에 맞춰 수행한다.
/// (획 경로는 명조체 글자의 실제 획 위에 얹히도록 형태를 따라 정의한다.)
class GuideStroke {
  final List<Offset> points; // 획 경로 (그리는 방향 순서대로)
  final Offset labelPos;     // 순서 번호(①②③…)를 그릴 위치
  const GuideStroke(this.points, this.labelPos);
}

Offset _o(double x, double y) => Offset(x, y);

/// 자모 원형 — 각 자모를 자기 0..1 박스 안에서 "획 순서대로" 정의.
/// (명조체 글자 획 위에 얹히도록 형태를 따라 그린다. 음절은 이 원형들을
///  영역에 배치해 조합한다.)
final Map<String, List<List<Offset>>> _jamo = {
  // 자음
  // ㄱ: ①(윗 가로획, 오른쪽) → ②(내림 획, 아래로) 2획. (가로획을 먼저 긋고 내려온다)
  'ㄱ': [
    [_o(.16, .22), _o(.82, .22)],
    [_o(.82, .22), _o(.6, .86)],
  ],
  'ㄴ': [
    [_o(.26, .14), _o(.26, .82)],
    [_o(.26, .82), _o(.82, .82)],
  ],
  'ㄷ': [
    [_o(.2, .2), _o(.82, .2)],
    [_o(.2, .22), _o(.2, .82), _o(.82, .82)],
  ],
  'ㄹ': [
    [_o(.2, .16), _o(.8, .16), _o(.8, .46)],
    [_o(.2, .46), _o(.8, .46)],
    [_o(.2, .46), _o(.2, .84), _o(.8, .84)],
  ],
  'ㅁ': [
    [_o(.22, .18), _o(.22, .84)],
    [_o(.22, .18), _o(.8, .18), _o(.8, .84)],
    [_o(.22, .84), _o(.8, .84)],
  ],
  'ㅂ': [
    [_o(.24, .16), _o(.24, .86)],
    [_o(.78, .16), _o(.78, .86)],
    [_o(.24, .52), _o(.78, .52)],
    [_o(.24, .86), _o(.78, .86)],
  ],
  'ㅅ': [
    [_o(.5, .16), _o(.2, .86)],
    [_o(.5, .4), _o(.82, .86)],
  ],
  // 모음
  'ㅏ': [
    [_o(.44, .12), _o(.44, .88)],
    [_o(.44, .5), _o(.78, .5)],
  ],
  'ㅑ': [
    [_o(.44, .12), _o(.44, .88)],
    [_o(.44, .38), _o(.78, .38)],
    [_o(.44, .64), _o(.78, .64)],
  ],
  'ㅓ': [
    [_o(.2, .5), _o(.56, .5)],
    [_o(.56, .12), _o(.56, .88)],
  ],
  'ㅕ': [
    [_o(.2, .38), _o(.56, .38)],
    [_o(.2, .64), _o(.56, .64)],
    [_o(.56, .12), _o(.56, .88)],
  ],
  'ㅗ': [
    [_o(.5, .24), _o(.5, .58)],
    [_o(.18, .58), _o(.82, .58)],
  ],
};

/// ㅇ(이응)은 원이라 점열로 생성한다.
List<Offset> _circle() {
  final pts = <Offset>[];
  const n = 24;
  for (var i = 0; i <= n; i++) {
    final a = -math.pi / 2 + 2 * math.pi * i / n; // 위에서 시작해 시계방향
    pts.add(Offset(.5 + .36 * math.cos(a), .5 + .36 * math.sin(a)));
  }
  return pts;
}

/// 받침 음절: [초성, 종성] (모두 중성 ㅏ). 획순 = 초성 → 중성ㅏ → 종성.
const Map<String, List<String>> _cvc = {
  '각': ['ㄱ', 'ㄱ'],
  '간': ['ㄱ', 'ㄴ'],
  '달': ['ㄷ', 'ㄹ'],
  '밤': ['ㅂ', 'ㅁ'],
  '상': ['ㅅ', 'ㅇ'],
};

List<List<Offset>> _placed(List<List<Offset>> prim, Rect r) {
  return prim
      .map((s) => s
          .map((p) => Offset(r.left + p.dx * r.width, r.top + p.dy * r.height))
          .toList())
      .toList();
}

List<List<Offset>> _strokesOf(String jamo) =>
    jamo == 'ㅇ' ? [_circle()] : (_jamo[jamo] ?? const []);

/// 단일 자모(자음/모음 탭)를 명조체 글자와 같은 크기로 배치.
List<List<Offset>> _single(String ch) =>
    _placed(_strokesOf(ch), const Rect.fromLTWH(0.2, 0.16, 0.6, 0.68));

/// 받침 음절 조합:
///  - 초성: 좌상단
///  - 중성 ㅏ: 우측(아래쪽은 종성 자리를 위해 비워 둠)
///  - 종성(받침): 하단 중앙 → 초성·중성과 자연스럽게 어울리도록.
/// (명조체 합자 글리프의 초성/중성/종성 위치에 맞춰 정한 영역이다.)
List<List<Offset>> _syllable(String initial, String finalC) {
  final out = <List<Offset>>[];
  out.addAll(_placed(_strokesOf(initial), const Rect.fromLTWH(0.10, 0.14, 0.34, 0.40)));
  out.addAll(_placed(_strokesOf('ㅏ'), const Rect.fromLTWH(0.52, 0.12, 0.36, 0.50)));
  out.addAll(_placed(_strokesOf(finalC), const Rect.fromLTWH(0.18, 0.60, 0.46, 0.30)));
  return out;
}

/// 순서 번호는 획 시작점에서 "획이 진행하는 방향으로 살짝 들어간 지점"에 둔다.
/// → 번호가 실제 획(명조체 글자의 획) 위에 얹힌다.
///   시작점이 겹치는 획들도 진행 방향이 달라 번호가 서로 포개지지 않는다.
Offset _labelPos(List<Offset> stroke) {
  final s0 = stroke.first;
  if (stroke.length < 2) return s0;
  final s1 = stroke[1];
  final dx = s1.dx - s0.dx, dy = s1.dy - s0.dy;
  final len = math.sqrt(dx * dx + dy * dy);
  if (len < 0.001) return s0;
  final d = math.min(0.11, len * 0.4); // 획 안쪽으로 들어가는 거리(획 위에 얹히도록)
  return Offset(s0.dx + dx / len * d, s0.dy + dy / len * d);
}

/// 주어진 글자('ㄱ','ㅏ','각' 등)의 획순 가이드를 반환한다.
/// 데이터가 없으면 빈 리스트(가이드 미표시).
List<GuideStroke> strokeOrderFor(String ch) {
  List<List<Offset>> raw;
  if (_cvc.containsKey(ch)) {
    final j = _cvc[ch]!;
    raw = _syllable(j[0], j[1]);
  } else {
    raw = _single(ch);
  }
  if (raw.isEmpty) return const [];
  return raw.map((s) => GuideStroke(s, _labelPos(s))).toList();
}
