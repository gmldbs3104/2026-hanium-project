"""
2단계 학습 전략의 1단계 — 폰트/규칙 기반 합성 손글씨 stroke 데이터 생성.

표준 획순(stroke_standards.py)은 "정답이 무엇인지"는 알려주지만 좌표 시퀀스가
없어서 그 자체로는 학습에 못 쓴다. 이 모듈은 각 자모의 대략적인 획 모양을
정규화 좌표로 정의하고, 음절 조합 배치 규칙(초성/중성/종성 위치)에 따라 배치한
뒤, 사람이 쓰듯 노이즈(떨림/속도 변화/살짝 어긋난 시작점)와 자연스러운 시간
간격을 섞어서 실제 stroke 데이터와 같은 형식
({stroke_id, points:[{x,y,pressure,timestamp}]})으로 대량 생성한다.

목적: 실제 사용자 필기 데이터가 없어도 SFR-004C/005C 모델의 1차 pretrain이
가능하게 하는 것. 실제 사람 필기의 다양성(개인 습관, 손떨림 등)까지는 담지
못하므로, 나중에 실 데이터로 2단계 fine-tune하는 것을 전제로 한다.

정확도 노트: 자모 모양은 정확한 서체 재현이 아니라 "대략 그렇게 생긴 직선/코너
근사"이다. 목적이 실제 폰트를 흉내내는 게 아니라 학습에 쓸 그럴듯한 좌표
시퀀스를 만드는 것이라 이 정도 근사로 충분하다고 판단.
"""
import math
import random
from typing import Dict, List, Tuple

from stroke_standards import (
    CHOSUNG, JUNGSUNG, JONGSUNG,
    _DOUBLE_CONSONANT_BASE, _COMPOUND_VOWEL_PARTS, _JONGSUNG_CLUSTER_PARTS,
    decompose_syllable,
)

Point = Tuple[float, float]
Path = List[Point]  # 하나의 획 = 정규화 [0,1]x[0,1] 좌표계의 폴리라인


def _circle_path(cx: float, cy: float, r: float, n: int = 10) -> Path:
    return [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n + 1)
    ]


# ── 기본 자음 14개의 획 모양 (정규화 좌표, 개수는 stroke_standards.py와 일치) ──
_BASE_CONSONANT_PATHS: Dict[str, List[Path]] = {
    "ㄱ": [[(0.15, 0.15), (0.85, 0.15), (0.85, 0.6)]],
    "ㄴ": [[(0.15, 0.15), (0.15, 0.85), (0.85, 0.85)]],
    "ㄷ": [
        [(0.15, 0.15), (0.85, 0.15)],
        [(0.15, 0.15), (0.15, 0.85), (0.85, 0.85)],
    ],
    "ㄹ": [
        [(0.15, 0.15), (0.85, 0.15)],
        [(0.85, 0.15), (0.15, 0.5), (0.85, 0.5)],
        [(0.15, 0.5), (0.15, 0.85), (0.85, 0.85)],
    ],
    "ㅁ": [
        [(0.15, 0.15), (0.15, 0.85)],
        [(0.15, 0.15), (0.5, 0.15)],
        [(0.5, 0.15), (0.85, 0.15), (0.85, 0.85)],
        [(0.15, 0.85), (0.85, 0.85)],
    ],
    "ㅂ": [
        [(0.15, 0.15), (0.15, 0.85)],
        [(0.85, 0.15), (0.85, 0.85)],
        [(0.15, 0.4), (0.85, 0.4)],
        [(0.15, 0.7), (0.85, 0.7)],
    ],
    "ㅅ": [
        [(0.5, 0.1), (0.2, 0.6)],
        [(0.5, 0.1), (0.8, 0.9)],
    ],
    "ㅇ": [_circle_path(0.5, 0.5, 0.35)],
    "ㅈ": [
        [(0.15, 0.25), (0.85, 0.25)],
        [(0.2, 0.85), (0.5, 0.25), (0.8, 0.85)],
    ],
    "ㅊ": [
        [(0.5, 0.05), (0.5, 0.2)],
        [(0.15, 0.3), (0.85, 0.3)],
        [(0.2, 0.9), (0.5, 0.3), (0.8, 0.9)],
    ],
    "ㅋ": [
        [(0.15, 0.15), (0.85, 0.15), (0.85, 0.6)],
        [(0.4, 0.35), (0.7, 0.35)],
    ],
    "ㅌ": [
        [(0.15, 0.15), (0.85, 0.15)],
        [(0.15, 0.5), (0.85, 0.5)],
        [(0.15, 0.15), (0.15, 0.85), (0.85, 0.85)],
    ],
    "ㅍ": [
        [(0.15, 0.15), (0.85, 0.15)],
        [(0.2, 0.3), (0.2, 0.85)],
        [(0.8, 0.3), (0.8, 0.85)],
        [(0.15, 0.85), (0.85, 0.85)],
    ],
    "ㅎ": [
        [(0.5, 0.05), (0.5, 0.18)],
        [(0.15, 0.32), (0.85, 0.32)],
        _circle_path(0.5, 0.65, 0.22),
    ],
}

# ── 기본 모음 10개의 획 모양 ──────────────────────────────────────────────
_BASE_VOWEL_PATHS: Dict[str, List[Path]] = {
    "ㅣ": [[(0.5, 0.1), (0.5, 0.9)]],
    "ㅡ": [[(0.1, 0.5), (0.9, 0.5)]],
    "ㅏ": [[(0.35, 0.1), (0.35, 0.9)], [(0.35, 0.5), (0.7, 0.5)]],
    "ㅑ": [[(0.35, 0.1), (0.35, 0.9)], [(0.35, 0.4), (0.7, 0.4)], [(0.35, 0.62), (0.7, 0.62)]],
    "ㅓ": [[(0.65, 0.1), (0.65, 0.9)], [(0.3, 0.5), (0.65, 0.5)]],
    "ㅕ": [[(0.65, 0.1), (0.65, 0.9)], [(0.3, 0.4), (0.65, 0.4)], [(0.3, 0.62), (0.65, 0.62)]],
    "ㅗ": [[(0.1, 0.35), (0.9, 0.35)], [(0.5, 0.35), (0.5, 0.7)]],
    "ㅛ": [[(0.1, 0.35), (0.9, 0.35)], [(0.35, 0.35), (0.35, 0.7)], [(0.65, 0.35), (0.65, 0.7)]],
    "ㅜ": [[(0.5, 0.3), (0.5, 0.65)], [(0.1, 0.65), (0.9, 0.65)]],
    "ㅠ": [[(0.35, 0.3), (0.35, 0.65)], [(0.65, 0.3), (0.65, 0.65)], [(0.1, 0.65), (0.9, 0.65)]],
}

# 세로형(vertical, 초성|중성 좌우 배치) vs 가로형(horizontal, 초성/중성 상하 배치)
_VERTICAL_VOWELS = {"ㅏ", "ㅑ", "ㅓ", "ㅕ", "ㅣ", "ㅐ", "ㅒ", "ㅔ", "ㅖ"}
_HORIZONTAL_VOWELS = {"ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅡ"}
# 나머지(ㅘㅙㅚㅝㅞㅟㅢ)는 복합형으로 처리


def _consonant_paths(jamo: str) -> List[Path]:
    if jamo in _DOUBLE_CONSONANT_BASE:
        base = _BASE_CONSONANT_PATHS[_DOUBLE_CONSONANT_BASE[jamo]]
        # 왼쪽 절반/오른쪽 절반에 같은 모양을 축소 배치해 "쌍자음" 느낌만 근사
        left  = [[(x * 0.4, y) for x, y in p] for p in base]
        right = [[(x * 0.4 + 0.5, y) for x, y in p] for p in base]
        return left + right
    if jamo in _JONGSUNG_CLUSTER_PARTS:
        paths: List[Path] = []
        for part in _JONGSUNG_CLUSTER_PARTS[jamo]:
            paths.extend(_consonant_paths(part))
        return paths
    return _BASE_CONSONANT_PATHS[jamo]


def _vowel_paths(jamo: str) -> List[Path]:
    if jamo in _COMPOUND_VOWEL_PARTS:
        paths: List[Path] = []
        for part in _COMPOUND_VOWEL_PARTS[jamo]:
            paths.extend(_vowel_paths(part))
        return paths
    return _BASE_VOWEL_PATHS[jamo]


def _vowel_layout_type(jamo: str) -> str:
    if jamo in _VERTICAL_VOWELS:
        return "vertical"
    if jamo in _HORIZONTAL_VOWELS:
        return "horizontal"
    return "compound"


def _transform(path: Path, box: Tuple[float, float, float, float]) -> Path:
    """정규화 [0,1]x[0,1] 좌표의 path를 box=(x0,y0,x1,y1) 영역으로 옮긴다."""
    x0, y0, x1, y1 = box
    return [(x0 + x * (x1 - x0), y0 + y * (y1 - y0)) for x, y in path]


def _syllable_layout(cho: str, jung: str, jong: str) -> List[Tuple[str, List[Path]]]:
    """
    (초성,중성,종성) → [(jamo_label, 배치된 path 목록), ...] (초성→중성→종성 순).
    한글 모아쓰기 배치 규칙(세로형/가로형/복합형)의 단순화 버전.
    """
    has_jong = bool(jong)
    body_bottom = 0.62 if has_jong else 1.0
    layout = _vowel_layout_type(jung)

    parts: List[Tuple[str, List[Path]]] = []

    if layout == "vertical":
        cho_box  = (0.05, 0.03, 0.55, body_bottom - 0.03)
        jung_box = (0.55, 0.03, 0.95, body_bottom - 0.03)
    elif layout == "horizontal":
        cho_box  = (0.1, 0.03, 0.9, body_bottom * 0.45)
        jung_box = (0.1, body_bottom * 0.5, 0.9, body_bottom - 0.02)
    else:  # compound: 초성 좌상단 + 중성이 아래+오른쪽을 감싸는 형태를 단순화
        cho_box  = (0.08, 0.03, 0.5, body_bottom * 0.5)
        jung_box = (0.08, body_bottom * 0.45, 0.95, body_bottom - 0.02)

    parts.append((cho, [_transform(p, cho_box) for p in _consonant_paths(cho)]))
    parts.append((jung, [_transform(p, jung_box) for p in _vowel_paths(jung)]))

    if has_jong:
        jong_box = (0.08, body_bottom + 0.03, 0.92, 0.97)
        parts.append((jong, [_transform(p, jong_box) for p in _consonant_paths(jong)]))

    return parts


def _path_to_points(
    path: Path,
    origin: Tuple[float, float],
    scale: float,
    start_time: int,
    jitter: float,
    speed_variation: float,
    points_per_segment: int = 6,
) -> Tuple[List[Dict], int]:
    """
    정규화 path(음절 box까지 이미 반영된 좌표)를 실제 캔버스 좌표의 stroke point
    시퀀스로 변환. jitter(픽셀 단위 떨림), speed_variation(구간별 소요시간 편차)로
    사람이 그린 것처럼 노이즈를 섞는다.
    """
    points: List[Dict] = []
    t = start_time
    ox, oy = origin

    for seg_i in range(len(path) - 1):
        x0, y0 = path[seg_i]
        x1, y1 = path[seg_i + 1]
        seg_time = max(15, int(random.gauss(40, 40 * speed_variation)))
        for i in range(points_per_segment):
            frac = i / (points_per_segment - 1) if points_per_segment > 1 else 0.0
            x_norm = x0 + (x1 - x0) * frac
            y_norm = y0 + (y1 - y0) * frac
            # jitter는 픽셀 단위 노이즈이므로 반드시 스케일을 곱한 "뒤"에 더해야 한다.
            # (정규화 좌표에 먼저 더하면 scale배만큼 증폭되어 글자가 완전히 깨짐)
            x_px = ox + x_norm * scale + random.gauss(0, jitter)
            y_px = oy + y_norm * scale + random.gauss(0, jitter)
            points.append({
                "x": round(x_px, 2),
                "y": round(y_px, 2),
                "pressure": round(min(1.0, max(0.3, random.gauss(0.8, 0.1))), 2),
                "timestamp": t,
            })
            if i < points_per_segment - 1:
                t += seg_time // points_per_segment
        t += seg_time // points_per_segment

    return points, t


def generate_synthetic_strokes(
    char: str,
    origin: Tuple[float, float] = (0.0, 0.0),
    scale: float = 150.0,
    start_time: int = 0,
    jitter: float = 2.0,
    speed_variation: float = 0.3,
    inter_stroke_gap_ms: Tuple[int, int] = (60, 180),
) -> Tuple[List[Dict], int]:
    """
    완성형 한글 음절 1글자 → 합성 stroke 리스트.

    Returns
    -------
    (strokes, next_start_time) — strokes는 stroke_grouping.py가 기대하는
    {stroke_id, points:[{x,y,pressure,timestamp}]} 형식. next_start_time은
    다음 글자를 이어 생성할 때 쓸 시작 timestamp.
    """
    decomposed = decompose_syllable(char)
    if decomposed is None:
        return [], start_time

    cho, jung, jong = decomposed
    layout = _syllable_layout(cho, jung, jong)

    strokes: List[Dict] = []
    t = start_time
    stroke_idx = 0
    for jamo_label, paths in layout:
        for path in paths:
            points, t_end = _path_to_points(
                path, origin, scale, t, jitter, speed_variation,
            )
            strokes.append({
                "stroke_id": f"syn_{char}_{stroke_idx}",
                "points": points,
                "_jamo": jamo_label,  # 디버그/검증용 — 실 인터페이스 스펙엔 없는 부가 필드
            })
            stroke_idx += 1
            t = t_end + random.randint(*inter_stroke_gap_ms)

    return strokes, t


def generate_synthetic_line(
    text: str,
    origin: Tuple[float, float] = (20.0, 20.0),
    char_scale: float = 120.0,
    char_gap: float = 40.0,
    start_time: int = 0,
    inter_char_gap_ms: Tuple[int, int] = (400, 900),
    **kwargs,
) -> List[Dict]:
    """
    여러 글자로 된 문자열 → 가로로 나열된 합성 stroke 시퀀스.
    글자 사이엔 stroke_grouping.py의 그룹 경계 임계값보다 확실히 크게 시간/공간
    간격을 둬서, 그룹핑 로직이 글자 단위로 올바르게 분리하는지 검증할 수 있다.
    """
    all_strokes: List[Dict] = []
    x = origin[0]
    t = start_time
    for char in text:
        strokes, t_end = generate_synthetic_strokes(
            char, origin=(x, origin[1]), scale=char_scale, start_time=t, **kwargs,
        )
        all_strokes.extend(strokes)
        x += char_scale + char_gap
        t = t_end + random.randint(*inter_char_gap_ms)
    return all_strokes
