import asyncio
from app.db.session import AsyncSessionLocal
from app.models.stroke_standard import StrokeStandard


async def seed():
    async with AsyncSessionLocal() as db:
        sample = StrokeStandard(
            char="가",
            expected_sequence=["down", "right", "down-right"],
            standard_height=100,
            standard_width=80,
            standard_spacing=20,
        )
        db.add(sample)
        await db.commit()
    print("Seed 완료")


if __name__ == "__main__":
    asyncio.run(seed())