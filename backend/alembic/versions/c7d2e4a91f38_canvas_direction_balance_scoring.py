"""캔버스 채점 개편: 획방향·성분비율·크기배율 저장

2026-09-01 채점 체계 개편(사용자 결정)으로 항목이 3개(획순/자간/크기)에서
5개(획순/획방향/성분비율/크기/자간)로 늘었다. 새 두 항목은 대시보드가 항목별로
집계해야 하므로 응답에만 실으면 안 되고 DB에 남아야 한다.

size_fill_ratio는 '표준 자형 대비 크기 배율'(1.0 = 표준과 같은 크기)이다. 종전
size_deviation은 세션 내 중앙값 대비라 **글자가 하나면 늘 0**이었다 — 자음·모음과
한 글자 연습에서 크기 채점이 사실상 없던 것과 같아 절대 기준을 새로 넣는다.

필압 컬럼은 원래 없었으므로 이 마이그레이션에서 지울 것이 없다.

Revision ID: c7d2e4a91f38
Revises: b3f1c27a9d40
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d2e4a91f38"
down_revision = "b3f1c27a9d40"
branch_labels = None
depends_on = None

_TABLE = "canvas_analysis_results"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("direction_result", sa.JSON(), nullable=True))
    op.add_column(_TABLE, sa.Column("balance_result", sa.JSON(), nullable=True))
    op.add_column(_TABLE, sa.Column("size_fill_ratio", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "size_fill_ratio")
    op.drop_column(_TABLE, "balance_result")
    op.drop_column(_TABLE, "direction_result")
