"""
seed_font_standards.py

이미지 모드(SFR-005I) 표준 서체 DB 시딩 스크립트.
한글 음절 11,172자 × 명조체(myeongjo) 기준 크기/비율 데이터를 생성한다.

데이터 설계:
  - standard_height : 100 (정규화 기준값, 모든 문자 동일)
  - standard_width  : 중성(모음) 유형별 차등
      세로 모음 (ㅏ/ㅓ/ㅣ 계열): 75  → 초성+모음이 좌우 배치 → 좁음
      복합 모음 (ㅘ/ㅝ 등)      : 85  → 중간
      가로 모음 (ㅗ/ㅜ/ㅡ 계열) : 95  → 초성+모음이 상하 배치 → 넓음
  - aspect_ratio    : standard_width / standard_height

실행 방법 (backend/ 디렉토리에서 venv 활성화 후):
  python -m app.db.seed_font_standards
"""

import asyncio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db.session import AsyncSessionLocal
from app.models.font_standard import FontStandard

HANGUL_START = 0xAC00
TOTAL = 11172
BATCH_SIZE = 500
DEFAULT_FONT_ID = "myeongjo"

# 중성별 표준 너비 (stroke_standards와 동일 기준 적용)
# 인덱스 순서: ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ
JUNGSEONG_WIDTHS: list[int] = [
    75, 75, 75, 75,  # ㅏ ㅐ ㅑ ㅒ  (세로 모음)
    75, 75, 75, 75,  # ㅓ ㅔ ㅕ ㅖ  (세로 모음)
    95, 85, 85, 85,  # ㅗ ㅘ ㅙ ㅚ
    95, 95, 85, 85,  # ㅛ ㅜ ㅝ ㅞ
    85, 95, 95, 85,  # ㅟ ㅠ ㅡ ㅢ
    75,              # ㅣ           (세로 모음)
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
    _, jung, _ = _decompose(char)
    width = JUNGSEONG_WIDTHS[jung]
    height = 100
    return {
        "char": char,
        "font_id": DEFAULT_FONT_ID,
        "standard_height": height,
        "standard_width": width,
        "aspect_ratio": round(width / height, 4),
    }


async def seed_all():
    entries = [_build_entry(chr(HANGUL_START + i)) for i in range(TOTAL)]

    async with AsyncSessionLocal() as db:
        for start in range(0, TOTAL, BATCH_SIZE):
            batch = entries[start: start + BATCH_SIZE]
            stmt = pg_insert(FontStandard).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["char", "font_id"],
                set_={
                    "standard_height": stmt.excluded.standard_height,
                    "standard_width": stmt.excluded.standard_width,
                    "aspect_ratio": stmt.excluded.aspect_ratio,
                },
            )
            await db.execute(stmt)
            await db.commit()
            done = min(start + BATCH_SIZE, TOTAL)
            print(f"  {done:>6}/{TOTAL} ({done * 100 // TOTAL}%)")

    print(f"완료: {TOTAL}자 × '{DEFAULT_FONT_ID}' 시딩 완료")


if __name__ == "__main__":
    asyncio.run(seed_all())
