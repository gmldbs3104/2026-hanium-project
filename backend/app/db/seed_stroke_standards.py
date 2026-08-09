"""
seed_stroke_standards.py

한글 음절 11,172자 전체에 대한 표준 획순 DB 시딩 스크립트.
각 음절을 초성/중성/종성으로 분해 후 자모별 획순 시퀀스를 합산한다.

획 레이블 종류 (AI_MODEL_INTERFACE.md 스펙 기준):
  horizontal       가로획 (→)
  vertical         세로획 (↓)
  dot              점획
  diagonal-left    좌하향 사선 (↙)
  diagonal-right   우하향 사선 (↘)
  curve            원/곡선획 (ㅇ 등)

실행 방법 (backend/ 디렉토리에서 venv 활성화 후):
  python -m app.db.seed_stroke_standards
"""

import asyncio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db.session import AsyncSessionLocal
from app.models.stroke_standard import StrokeStandard

HANGUL_START = 0xAC00
TOTAL = 11172
BATCH_SIZE = 500

# ────────────────────────────────────────────────────────────────
# 초성 획순 (19개, index 0~18)
# 순서: ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ
# ────────────────────────────────────────────────────────────────
CHOSEONG_STROKES: list[list[str]] = [
    ["horizontal", "vertical"],                                                                    # 0  ㄱ 2획
    ["horizontal", "vertical", "horizontal", "vertical"],                                          # 1  ㄲ 4획
    ["vertical", "horizontal"],                                                                    # 2  ㄴ 2획
    ["horizontal", "vertical", "horizontal"],                                                      # 3  ㄷ 3획
    ["horizontal", "vertical", "horizontal", "horizontal", "vertical", "horizontal"],              # 4  ㄸ 6획
    ["horizontal", "vertical", "horizontal", "vertical", "horizontal"],                           # 5  ㄹ 5획
    ["vertical", "horizontal", "vertical", "horizontal"],                                          # 6  ㅁ 4획
    ["vertical", "vertical", "horizontal", "horizontal"],                                          # 7  ㅂ 4획
    ["vertical", "vertical", "horizontal", "horizontal", "vertical", "vertical", "horizontal", "horizontal"],  # 8  ㅃ 8획
    ["diagonal-left", "diagonal-right"],                                                           # 9  ㅅ 2획
    ["diagonal-left", "diagonal-right", "diagonal-left", "diagonal-right"],                       # 10 ㅆ 4획
    ["curve"],                                                                                     # 11 ㅇ 1획
    ["horizontal", "diagonal-left", "diagonal-right"],                                            # 12 ㅈ 3획
    ["horizontal", "diagonal-left", "diagonal-right", "horizontal", "diagonal-left", "diagonal-right"],  # 13 ㅉ 6획
    ["dot", "horizontal", "diagonal-left", "diagonal-right"],                                     # 14 ㅊ 4획
    ["horizontal", "vertical", "horizontal"],                                                      # 15 ㅋ 3획
    ["horizontal", "horizontal", "vertical", "horizontal"],                                        # 16 ㅌ 4획
    ["vertical", "horizontal", "horizontal", "vertical"],                                          # 17 ㅍ 4획
    ["dot", "horizontal", "curve"],                                                                # 18 ㅎ 3획
]

# ────────────────────────────────────────────────────────────────
# 중성 획순 (21개, index 0~20)
# 순서: ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ
# ────────────────────────────────────────────────────────────────
JUNGSEONG_STROKES: list[list[str]] = [
    ["vertical", "horizontal"],                                                   # 0  ㅏ 2획
    ["vertical", "horizontal", "vertical"],                                       # 1  ㅐ 3획
    ["vertical", "horizontal", "horizontal"],                                     # 2  ㅑ 3획
    ["vertical", "horizontal", "horizontal", "vertical"],                         # 3  ㅒ 4획
    ["horizontal", "vertical"],                                                   # 4  ㅓ 2획
    ["horizontal", "vertical", "vertical"],                                       # 5  ㅔ 3획
    ["horizontal", "horizontal", "vertical"],                                     # 6  ㅕ 3획
    ["horizontal", "horizontal", "vertical", "vertical"],                         # 7  ㅖ 4획
    ["horizontal", "vertical"],                                                   # 8  ㅗ 2획
    ["horizontal", "vertical", "vertical", "horizontal"],                         # 9  ㅘ 4획 (ㅗ+ㅏ)
    ["horizontal", "vertical", "vertical", "horizontal", "vertical"],             # 10 ㅙ 5획 (ㅗ+ㅐ)
    ["horizontal", "vertical", "vertical"],                                       # 11 ㅚ 3획 (ㅗ+ㅣ)
    ["horizontal", "vertical", "vertical"],                                       # 12 ㅛ 3획
    ["horizontal", "vertical"],                                                   # 13 ㅜ 2획
    ["horizontal", "vertical", "horizontal", "vertical"],                         # 14 ㅝ 4획 (ㅜ+ㅓ)
    ["horizontal", "vertical", "horizontal", "vertical", "vertical"],             # 15 ㅞ 5획 (ㅜ+ㅔ)
    ["horizontal", "vertical", "vertical"],                                       # 16 ㅟ 3획 (ㅜ+ㅣ)
    ["horizontal", "vertical", "vertical"],                                       # 17 ㅠ 3획
    ["horizontal"],                                                               # 18 ㅡ 1획
    ["horizontal", "vertical"],                                                   # 19 ㅢ 2획
    ["vertical"],                                                                 # 20 ㅣ 1획
]

# 중성별 표준 너비 (세로 모음=75, 가로 모음=95, 복합 모음=85)
# 세로 모음(초성 왼+모음 오른 구조): ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅣ → 좁음
# 가로 모음(초성 위+모음 아래 구조): ㅗ ㅛ ㅜ ㅠ ㅡ → 넓음
# 복합 모음: 중간
JUNGSEONG_WIDTHS: list[int] = [
    75, 75, 75, 75,  # ㅏ ㅐ ㅑ ㅒ
    75, 75, 75, 75,  # ㅓ ㅔ ㅕ ㅖ
    95, 85, 85, 85,  # ㅗ ㅘ ㅙ ㅚ
    95, 95, 85, 85,  # ㅛ ㅜ ㅝ ㅞ
    85, 95, 95, 85,  # ㅟ ㅠ ㅡ ㅢ
    75,              # ㅣ
]

# ────────────────────────────────────────────────────────────────
# 종성 획순 (28개, index 0~27)
# index 0 = 받침 없음 (빈 리스트)
# 순서: '' ㄱ ㄲ ㄳ ㄴ ㄵ ㄶ ㄷ ㄹ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅁ ㅂ ㅄ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ
# ────────────────────────────────────────────────────────────────
_S: dict[str, list[str]] = {
    "ㄱ": ["horizontal", "vertical"],
    "ㄲ": ["horizontal", "vertical", "horizontal", "vertical"],
    "ㄴ": ["vertical", "horizontal"],
    "ㄷ": ["horizontal", "vertical", "horizontal"],
    "ㄹ": ["horizontal", "vertical", "horizontal", "vertical", "horizontal"],
    "ㅁ": ["vertical", "horizontal", "vertical", "horizontal"],
    "ㅂ": ["vertical", "vertical", "horizontal", "horizontal"],
    "ㅅ": ["diagonal-left", "diagonal-right"],
    "ㅆ": ["diagonal-left", "diagonal-right", "diagonal-left", "diagonal-right"],
    "ㅇ": ["curve"],
    "ㅈ": ["horizontal", "diagonal-left", "diagonal-right"],
    "ㅊ": ["dot", "horizontal", "diagonal-left", "diagonal-right"],
    "ㅋ": ["horizontal", "vertical", "horizontal"],
    "ㅌ": ["horizontal", "horizontal", "vertical", "horizontal"],
    "ㅍ": ["vertical", "horizontal", "horizontal", "vertical"],
    "ㅎ": ["dot", "horizontal", "curve"],
}

JONGSEONG_STROKES: list[list[str]] = [
    [],                                   # 0  없음
    _S["ㄱ"],                             # 1  ㄱ
    _S["ㄲ"],                             # 2  ㄲ
    _S["ㄱ"] + _S["ㅅ"],                  # 3  ㄳ
    _S["ㄴ"],                             # 4  ㄴ
    _S["ㄴ"] + _S["ㅈ"],                  # 5  ㄵ
    _S["ㄴ"] + _S["ㅎ"],                  # 6  ㄶ
    _S["ㄷ"],                             # 7  ㄷ
    _S["ㄹ"],                             # 8  ㄹ
    _S["ㄹ"] + _S["ㄱ"],                  # 9  ㄺ
    _S["ㄹ"] + _S["ㅁ"],                  # 10 ㄻ
    _S["ㄹ"] + _S["ㅂ"],                  # 11 ㄼ
    _S["ㄹ"] + _S["ㅅ"],                  # 12 ㄽ
    _S["ㄹ"] + _S["ㅌ"],                  # 13 ㄾ
    _S["ㄹ"] + _S["ㅍ"],                  # 14 ㄿ
    _S["ㄹ"] + _S["ㅎ"],                  # 15 ㅀ
    _S["ㅁ"],                             # 16 ㅁ
    _S["ㅂ"],                             # 17 ㅂ
    _S["ㅂ"] + _S["ㅅ"],                  # 18 ㅄ
    _S["ㅅ"],                             # 19 ㅅ
    _S["ㅆ"],                             # 20 ㅆ
    _S["ㅇ"],                             # 21 ㅇ
    _S["ㅈ"],                             # 22 ㅈ
    _S["ㅊ"],                             # 23 ㅊ
    _S["ㅋ"],                             # 24 ㅋ
    _S["ㅌ"],                             # 25 ㅌ
    _S["ㅍ"],                             # 26 ㅍ
    _S["ㅎ"],                             # 27 ㅎ
]


def _decompose(char: str) -> tuple[int, int, int]:
    """한글 음절 → (초성 index, 중성 index, 종성 index)"""
    code = ord(char) - HANGUL_START
    jong = code % 28
    code //= 28
    jung = code % 21
    cho = code // 21
    return cho, jung, jong


def _build_entry(char: str) -> dict:
    cho, jung, jong = _decompose(char)
    sequence = CHOSEONG_STROKES[cho] + JUNGSEONG_STROKES[jung] + JONGSEONG_STROKES[jong]
    return {
        "char": char,
        "expected_sequence": sequence,
        "standard_height": 100,
        "standard_width": JUNGSEONG_WIDTHS[jung],
        "standard_spacing": 20,
    }


async def seed_all():
    entries = [_build_entry(chr(HANGUL_START + i)) for i in range(TOTAL)]

    async with AsyncSessionLocal() as db:
        for start in range(0, TOTAL, BATCH_SIZE):
            batch = entries[start: start + BATCH_SIZE]
            stmt = pg_insert(StrokeStandard).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["char"],
                set_={
                    "expected_sequence": stmt.excluded.expected_sequence,
                    "standard_height": stmt.excluded.standard_height,
                    "standard_width": stmt.excluded.standard_width,
                    "standard_spacing": stmt.excluded.standard_spacing,
                },
            )
            await db.execute(stmt)
            await db.commit()
            done = min(start + BATCH_SIZE, TOTAL)
            print(f"  {done:>6}/{TOTAL} ({done * 100 // TOTAL}%)")

    print(f"완료: {TOTAL}자 시딩 완료")


if __name__ == "__main__":
    asyncio.run(seed_all())
