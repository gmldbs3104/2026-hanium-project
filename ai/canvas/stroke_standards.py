"""
SFR-005C 표준 획순 데이터 — 한글 완성형 11,172자 전체 커버.

REQ-005C-5: "표준 획순 DB는 한글 11,172자(완성형) 전체의 획순 시퀀스를 포함해야 한다."
음절 11,172개를 낱개로 저장하는 대신, 완성형 음절이 (초성,중성,종성) 조합의 유니코드
산술 분해로 얻어진다는 점을 이용해 **자모 19+21+27개의 획순만 인코딩**하고 조합해서
전체 음절의 획순을 생성한다.

정확도에 대한 노트
------------------
각 자모의 라벨은 `"{자모}_{순번}"` 형식(예: "ㄱ_1", "ㅂ_2")으로, 실제 붓글씨체의
정밀한 획 방향(가로/세로/사선 등)까지는 구분하지 않고 **개수와 순서만 보장**한다.
지금 `lstm_analyze_stroke_order`의 실제 동작이 "stroke 개수 비교"뿐이라 개수·순서
정확도가 우선이고, 방향까지 세밀하게 필요해지면(LSTM 도입 시) 자모별 라벨을
"horizontal"/"vertical"/"dot" 같은 의미 있는 카테고리로 정밀화하면 된다.
"""
from typing import List

# ── 자모 목록 (유니코드 완성형 조합 순서 그대로) ──────────────────────────

CHOSUNG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")   # 19개
JUNGSUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")  # 21개
JONGSUNG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")  # 28개(받침 없음 포함)

# ── 자모별 표준 획수 (초등 국어 교과서 필순 기준 통용 값) ─────────────────
# 겹자음/겹모음은 구성 성분의 획수 합으로 계산.

_BASE_CONSONANT_STROKES = {
    "ㄱ": 1, "ㄴ": 1, "ㄷ": 2, "ㄹ": 3, "ㅁ": 4, "ㅂ": 4, "ㅅ": 2,
    "ㅇ": 1, "ㅈ": 2, "ㅊ": 3, "ㅋ": 2, "ㅌ": 3, "ㅍ": 4, "ㅎ": 3,
}
_DOUBLE_CONSONANT_BASE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}

_BASE_VOWEL_STROKES = {
    "ㅏ": 2, "ㅑ": 3, "ㅓ": 2, "ㅕ": 3, "ㅗ": 2, "ㅛ": 3,
    "ㅜ": 2, "ㅠ": 3, "ㅡ": 1, "ㅣ": 1,
}
# 복합모음 = 구성 단모음의 조합
_COMPOUND_VOWEL_PARTS = {
    "ㅐ": ["ㅏ", "ㅣ"], "ㅒ": ["ㅑ", "ㅣ"], "ㅔ": ["ㅓ", "ㅣ"], "ㅖ": ["ㅕ", "ㅣ"],
    "ㅘ": ["ㅗ", "ㅏ"], "ㅙ": ["ㅗ", "ㅐ"], "ㅚ": ["ㅗ", "ㅣ"],
    "ㅝ": ["ㅜ", "ㅓ"], "ㅞ": ["ㅜ", "ㅔ"], "ㅟ": ["ㅜ", "ㅣ"],
    "ㅢ": ["ㅡ", "ㅣ"],
}

_JONGSUNG_CLUSTER_PARTS = {
    "ㄳ": ["ㄱ", "ㅅ"], "ㄵ": ["ㄴ", "ㅈ"], "ㄶ": ["ㄴ", "ㅎ"],
    "ㄺ": ["ㄹ", "ㄱ"], "ㄻ": ["ㄹ", "ㅁ"], "ㄼ": ["ㄹ", "ㅂ"], "ㄽ": ["ㄹ", "ㅅ"],
    "ㄾ": ["ㄹ", "ㅌ"], "ㄿ": ["ㄹ", "ㅍ"], "ㅀ": ["ㄹ", "ㅎ"], "ㅄ": ["ㅂ", "ㅅ"],
}


# ── 획순 복수 정본 (IMPLEMENTATION_PLAN 2.1 / NORM_STROKE_RESEARCH §2) ──────
# 한글 필순은 어문 규범상 미규정이라 단일 정답을 강제할 근거가 없다. 논쟁이 흔하고
# 근거가 명확한 자모에 한해, 표준(canonical) 대비 '대안 순열'을 감점 없이 허용한다.
# 순열은 각 자모의 표준 획 순서 인덱스(synthetic_stroke_generator._BASE_CONSONANT_PATHS
# 경로 순서)에 대한 재배열이다.
#
#   ㅌ: canonical = [위가로(0), 가운데가로(1), ㄴ자(2)]. 논쟁점은 '가운데 가로획을
#       2번째 vs 마지막'(NORM_STROKE_RESEARCH §2) → 대안 [0,2,1] = 가운데 가로를 마지막에.
#   ※ ㅋ·ㅂ·ㄹ·ㅅ·ㅎ 등은 교과서 실물 근거가 확보되면 여기에 한 줄씩 추가한다(§3 미결).
ALTERNATIVE_STROKE_ORDERS = {
    "ㅌ": [[0, 2, 1]],
}

# 대안 순서를 감점 없이 수용할 때 함께 보여줄 '표준 필순' 안내 문구(안내 병기).
_STANDARD_ORDER_NOTES = {
    "ㅌ": "'ㅌ'을(를) 통용되는 순서로 썼습니다(감점 없음). "
          "표준 필순은 가운데 가로획을 위 가로획 다음(두 번째)에 씁니다.",
}


def standard_order_note(jamo: str) -> str:
    """대안 순서 수용 시 함께 안내할 표준 필순 문구. 별도 문구가 없으면 일반 문구."""
    return _STANDARD_ORDER_NOTES.get(
        jamo, f"'{jamo}'을(를) 통용되는 순서로 썼습니다(감점 없음)."
    )


def _consonant_sequence(jamo: str) -> List[str]:
    if jamo in _DOUBLE_CONSONANT_BASE:
        base = _DOUBLE_CONSONANT_BASE[jamo]
        n = _BASE_CONSONANT_STROKES[base]
        return [f"{jamo}_{i+1}" for i in range(n * 2)]
    if jamo in _JONGSUNG_CLUSTER_PARTS:
        seq = []
        for part in _JONGSUNG_CLUSTER_PARTS[jamo]:
            seq.extend(_consonant_sequence(part))
        return [f"{jamo}_{i+1}" for i in range(len(seq))]
    n = _BASE_CONSONANT_STROKES[jamo]
    return [f"{jamo}_{i+1}" for i in range(n)]


def _vowel_stroke_count(jamo: str) -> int:
    """ㅙ("ㅗ"+"ㅐ")처럼 구성 성분 자체가 복합모음인 경우까지 재귀적으로 처리."""
    if jamo in _BASE_VOWEL_STROKES:
        return _BASE_VOWEL_STROKES[jamo]
    return sum(_vowel_stroke_count(p) for p in _COMPOUND_VOWEL_PARTS[jamo])


def _vowel_sequence(jamo: str) -> List[str]:
    n = _vowel_stroke_count(jamo)
    return [f"{jamo}_{i+1}" for i in range(n)]


# 자모별 획순 라벨 시퀀스 사전 계산 (모듈 로드 시 1회)
_CHOSUNG_SEQ  = {j: _consonant_sequence(j) for j in CHOSUNG}
_JUNGSUNG_SEQ = {j: _vowel_sequence(j) for j in JUNGSUNG}
_JONGSUNG_SEQ = {j: (_consonant_sequence(j) if j else []) for j in JONGSUNG}


def decompose_syllable(char: str):
    """
    완성형 한글 음절 1글자 → (초성, 중성, 종성) 튜플.
    유니코드 조합형이 아닌 문자(자모 단독, 영문, 숫자 등)면 None.
    """
    code = ord(char) - 0xAC00
    if not (0 <= code < 19 * 21 * 28):
        return None
    cho = code // (21 * 28)
    jung = (code % (21 * 28)) // 28
    jong = code % 28
    return CHOSUNG[cho], JUNGSUNG[jung], JONGSUNG[jong]


def get_expected_sequence(char: str) -> List[str]:
    """
    SFR-005C 표준 획순 조회 — 완성형 음절 1글자에 대한 획순 라벨 리스트.
    초성 → 중성 → 종성 순서로 각 자모의 획을 이어붙인다.

    한글이 아니거나 조합형이 아니면 빈 리스트 반환.
    """
    decomposed = decompose_syllable(char)
    if decomposed is None:
        return []
    cho, jung, jong = decomposed
    return _CHOSUNG_SEQ[cho] + _JUNGSUNG_SEQ[jung] + _JONGSUNG_SEQ[jong]


# ------------------------------------------------------------------
# SFR-005C 인터페이스 함수 (AI_MODEL_INTERFACE.md 섹션 2)
# ------------------------------------------------------------------

def lstm_analyze_stroke_order(strokes: List[dict], expected_sequence: List[str]) -> dict:
    """
    AI_MODEL_INTERFACE.md 섹션 2 규격 함수.

    현재: stroke 개수 비교만 수행 (문서화된 placeholder 동작).
    교체 목표: 각 stroke의 방향 벡터 시퀀스 → LSTM → 획 레이블 분류
              (실 사용자 필기 stroke 학습 데이터 확보 전까지는 학습 불가능).
    """
    actual_count = len(strokes)
    expected_count = len(expected_sequence)

    # 실제 stroke 순서를 알 수 없으므로(LSTM 미도입) 현재는 stroke_id 순서를
    # 그대로 "actual_sequence"로 표기 — 정밀 레이블 분류는 LSTM 도입 후 교체.
    actual_sequence = [s.get("stroke_id", f"s{i}") for i, s in enumerate(strokes)]

    error_count = abs(actual_count - expected_count)
    corrections: List[str] = []
    if actual_count < expected_count:
        corrections.append(f"획이 {expected_count - actual_count}개 부족합니다.")
    elif actual_count > expected_count:
        corrections.append(f"획이 {actual_count - expected_count}개 더 많습니다.")

    return {
        "expected_sequence": expected_sequence,
        "actual_sequence":   actual_sequence,
        "error_count":       error_count,
        "corrections":       corrections,
    }
