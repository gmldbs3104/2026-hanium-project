"""
2단계 학습 전략의 1단계 — 폰트/규칙 기반 합성 손글씨 stroke 데이터 생성.

표준 획순(stroke_standards.py)은 "정답이 무엇인지"는 알려주지만 좌표 시퀀스가
없어서 그 자체로는 학습에 못 쓴다. 이 모듈은 각 자모의 대략적인 획 모양을
정규화 좌표로 정의하고, 음절 조합 배치 규칙(초성/중성/종성 위치)에 따라 배치한
뒤, 사람이 쓰듯 노이즈(떨림/속도 변화/살짝 어긋난 시작점)와 자연스러운 시간
간격을 섞어서 실제 stroke 데이터와 같은 형식
({stroke_id, points:[{x,y,timestamp}]})으로 대량 생성한다.

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

from .stroke_standards import (
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
    # ㄹ은 **ㄱ + ─ + ㄴ** 3획이다(교과서 필순). 종전 ②는 우상단에서 좌중단으로
    # 가로지르는 **사선**이었는데, ㄹ에는 사선이 없다. 획 모양이 어긋나니 기하 매칭이
    # 엉켜 제대로 써도 획순·획방향이 틀렸다고 나왔다(사용자 신고 2026-09-01).
    "ㄹ": [
        [(0.15, 0.15), (0.85, 0.15), (0.85, 0.5)],
        [(0.15, 0.5), (0.85, 0.5)],
        [(0.15, 0.5), (0.15, 0.85), (0.85, 0.85)],
    ],
    # ㅁ은 **3획**이다(초등 교과서 필순): 왼쪽 세로 → 위+오른쪽(ㄱ 모양) → 아래 가로.
    # 종전 4획은 위 가로를 둘로 쪼갠 것이라 프론트 가이드(3획)와 어긋났다(2026-09-01).
    "ㅁ": [
        [(0.15, 0.15), (0.15, 0.85)],
        [(0.15, 0.15), (0.85, 0.15), (0.85, 0.85)],
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
    # ㅓ·ㅕ는 짧은 가로획이 세로획 **왼쪽**에 있으므로 '왼쪽에서 오른쪽으로' 규칙에
    # 따라 **가로가 먼저**다(ㅏ·ㅑ는 오른쪽이라 세로가 먼저 — 위 두 줄). 종전에는
    # ㅏ와 똑같이 세로부터 그어 프론트 가이드와 순서가 뒤집혀 있었다(2026-09-01).
    "ㅓ": [[(0.3, 0.5), (0.65, 0.5)], [(0.65, 0.1), (0.65, 0.9)]],
    "ㅕ": [[(0.3, 0.4), (0.65, 0.4)], [(0.3, 0.62), (0.65, 0.62)], [(0.65, 0.1), (0.65, 0.9)]],
    # ⚠️ ㅗ·ㅜ·ㅛ·ㅠ는 2026-09-01까지 **모양이 통째로 뒤바뀌어** 있었다 — ㅗ 자리에
    # ㅜ 모양(막대가 위, 짧은획이 아래)이 들어 있었다. 짧은획은 ㅗ·ㅛ에서는 막대
    # **위**, ㅜ·ㅠ에서는 막대 **아래**다. 순서도 '위에서 아래로'를 따른다.
    "ㅗ": [[(0.5, 0.3), (0.5, 0.65)], [(0.1, 0.65), (0.9, 0.65)]],
    "ㅛ": [[(0.35, 0.3), (0.35, 0.65)], [(0.65, 0.3), (0.65, 0.65)], [(0.1, 0.65), (0.9, 0.65)]],
    "ㅜ": [[(0.1, 0.35), (0.9, 0.35)], [(0.5, 0.35), (0.5, 0.7)]],
    "ㅠ": [[(0.1, 0.35), (0.9, 0.35)], [(0.35, 0.35), (0.35, 0.7)], [(0.65, 0.35), (0.65, 0.7)]],
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


def _transform_all(paths: List[Path], box: Tuple[float, float, float, float]) -> List[Path]:
    """자모의 획 묶음을 box=(x0,y0,x1,y1)에 **꽉 차게** 옮긴다.

    ⚠️ 자모별로 함께 정규화해야 한다. 경로 하나씩 따로 펴면 획끼리의 상대 위치가
    깨진다(ㅏ의 짧은 가로획이 세로획만큼 커지는 식).

    왜 꽉 채우나 — 종전에는 [0,1] 좌표를 그대로 곱해 넣었는데, 정작 경로들이
    [0,1]을 다 안 쓴다(ㄱ은 y 0.15~0.60, 높이의 45%만). 그래서 "상자"와 "실제 잉크"가
    달랐고, 성분 비율 기준을 잉크로 잡으면 상자 값과 최대 57%까지 어긋났다
    (2026-09-01 실측). 꽉 채우면 **상자 = 잉크**가 되어 배치 정본 하나로 통일된다.
    """
    xs = [x for p in paths for x, _ in p]
    ys = [y for p in paths for _, y in p]
    sx0, sx1 = min(xs), max(xs)
    sy0, sy1 = min(ys), max(ys)
    sw = (sx1 - sx0) or 1.0
    sh = (sy1 - sy0) or 1.0
    x0, y0, x1, y1 = box
    return [[(x0 + (x - sx0) / sw * (x1 - x0),
              y0 + (y - sy0) / sh * (y1 - y0)) for x, y in p] for p in paths]


# ── 자모 배치 정본 (단일 출처) ─────────────────────────────────────────────
# ⚠️ 이 값들은 **채점 기준인 동시에 사용자가 보는 획순 가이드**다.
# 프론트 stroke_order_data.dart가 같은 자리를 그리며, 어긋나면 "가이드대로 썼는데
# 비율이 틀렸다"는 오판이 나온다. ai/tests/test_jamo_layout_contract.py가 고정한다.
#
# 📐 **수치 근거 (2026-09-01 실측)** — 사용자가 보고 따라 쓰는 것은 캔버스에 깔리는
# **명조체 그림자 글씨**다. 그래서 그 글리프를 브라우저에서 렌더링하고 픽셀을 훑어,
# 행/열 투영으로 초성·중성·종성 영역을 갈라 쟀다.
#   세로+종성 각·간·달·밤·상 / 세로 무종성 가·기·너 / 가로+종성 곡·국 / 가로 무종성 고·구
# 아래는 그 중앙값을 글자 잉크 상자 기준(x,y,w,h)으로 정리한 것이다.
#
# 종전 값은 획순 번호를 놓으려고 눈대중으로 잡은 사각형이라 실제 글리프와 최대
# 57%까지 어긋났고, 그림자대로 똑같이 써도 성분 비율 오류가 났다(사용자 지적).

# 글자 전체 잉크가 가이드 상자 안에서 차지하는 여백.
_INK_MARGIN = 0.06

#                          초성                          중성                          종성
_REGIONS = {
    ("vertical", True):    [(0.000, 0.123, 0.513, 0.479), (0.586, 0.000, 0.414, 0.573), (0.212, 0.628, 0.668, 0.372)],
    ("vertical", False):   [(0.000, 0.193, 0.535, 0.601), (0.578, 0.000, 0.422, 1.000)],
    ("horizontal", True):  [(0.142, 0.000, 0.704, 0.239), (0.000, 0.239, 1.000, 0.302), (0.139, 0.603, 0.648, 0.397)],
    ("horizontal", False): [(0.123, 0.000, 0.735, 0.361), (0.000, 0.361, 1.000, 0.639)],
}
# 복합모음(ㅘㅙㅚㅝㅞㅟㅢ)은 아직 안 쟀다 — 연습 세트에 없다. 가로형을 빌려 쓰되,
# 연습 글자가 늘면 같은 방법(글리프 렌더링 후 픽셀 측정)으로 재서 채울 것.
_REGIONS[("compound", True)] = _REGIONS[("horizontal", True)]
_REGIONS[("compound", False)] = _REGIONS[("horizontal", False)]

# 낱개 자모가 화면을 혼자 쓸 때의 상자.
_SINGLE_JAMO_BOX = (0.20, 0.16, 0.80, 0.84)

Box = Tuple[float, float, float, float]


def jamo_boxes(cho: str, jung: str, jong: str) -> List[Tuple[str, Box]]:
    """(초성,중성,종성) → [(자모, (x0,y0,x1,y1))] — 자모별 기대 상자, 초성→중성→종성 순.

    획순 가이드 생성과 성분 비율 채점이 **둘 다 이 함수**를 본다. 자모가 어디에
    있어야 하는지를 아는 곳은 여기 하나뿐이어야 한다.

    반환 좌표계는 **가이드 상자 [0,1]** 기준이다(_INK_MARGIN 여백 포함).
    """
    has_jong = bool(jong)
    rows = _REGIONS[(_vowel_layout_type(jung), has_jong)]
    jamos = [cho, jung] + ([jong] if has_jong else [])

    m = _INK_MARGIN
    span = 1.0 - 2 * m
    boxes: List[Tuple[str, Box]] = []
    for jamo, (x, y, w, h) in zip(jamos, rows):
        boxes.append((jamo, (round(m + x * span, 4), round(m + y * span, 4),
                             round(m + (x + w) * span, 4), round(m + (y + h) * span, 4))))
    return boxes


def single_jamo_box() -> Box:
    """낱개 자모 하나가 혼자 쓰는 상자. 나눠 쓸 다른 자모가 없다."""
    return _SINGLE_JAMO_BOX


def _syllable_layout(cho: str, jung: str, jong: str) -> List[Tuple[str, List[Path]]]:
    """
    (초성,중성,종성) → [(jamo_label, 배치된 path 목록), ...] (초성→중성→종성 순).
    자리는 jamo_boxes()가 정하고 여기서는 획 경로만 그 자리에 옮긴다.
    """
    parts: List[Tuple[str, List[Path]]] = []
    for i, (jamo, box) in enumerate(jamo_boxes(cho, jung, jong)):
        # 순서가 초성→중성→종성으로 고정이므로 1번만 모음이다.
        paths = _vowel_paths(jamo) if i == 1 else _consonant_paths(jamo)
        parts.append((jamo, _transform_all(paths, box)))
    return parts


def _single_jamo_layout(jamo: str, is_vowel: bool) -> List[Tuple[str, List[Path]]]:
    """
    낱개 자모(ㄱ·ㅏ 등) 하나가 화면 전체를 혼자 쓸 때의 배치.
    음절 안에서 다른 자모와 자리를 나눠 쓰지 않으므로 단독 상자를 그대로 쓴다.
    """
    box = single_jamo_box()
    paths = _vowel_paths(jamo) if is_vowel else _consonant_paths(jamo)
    return [(jamo, _transform_all(paths, box))]


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
    {stroke_id, points:[{x,y,timestamp}]} 형식. next_start_time은
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
