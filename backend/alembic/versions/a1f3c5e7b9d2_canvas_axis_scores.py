"""캔버스 축 점수 저장

2026-10-08 채점 축 재설계. 글자마다 축 점수 {"획순","모양","짜임새","배치"}를 저장한다.
대시보드가 저장된 중간 결과로 점수를 다시 계산하던 코드를 없애기 위한 컬럼이다 —
모서리처럼 저장되지 않는 중간 결과가 있어 축 점수를 복원할 수 없다.

Revision ID: a1f3c5e7b9d2
Revises: d3a8f1c62e07
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "a1f3c5e7b9d2"
down_revision = "d3a8f1c62e07"
branch_labels = None
depends_on = None

_TABLE = "canvas_analysis_results"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("item_scores", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "item_scores")
