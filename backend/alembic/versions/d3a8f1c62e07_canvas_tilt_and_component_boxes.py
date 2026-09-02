"""캔버스 성분 박스 + 기울기 판정 저장

2026-09-01 박스 재설계(사용자 결정). 박스 단위를 음절 → **성분(초·중·종성)**으로 내리면서
화면이 그릴 박스와 그 색 판정을 서버가 만들어 내려준다. 대시보드가 항목별로 집계하려면
기울기도 DB에 남아야 한다.

`tilt_result`가 따로 있는 이유: ㅣ·ㅡ처럼 한쪽 변이 0에 가까운 자모는 성분비율의
종횡비로 재면 10도만 기울어도 442배로 폭발한다(실측). 각도로 직접 재는 별도 항목이다.

Revision ID: d3a8f1c62e07
Revises: c7d2e4a91f38
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "d3a8f1c62e07"
down_revision = "c7d2e4a91f38"
branch_labels = None
depends_on = None

_TABLE = "canvas_analysis_results"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("tilt_result", sa.JSON(), nullable=True))
    op.add_column(_TABLE, sa.Column("component_boxes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "component_boxes")
    op.drop_column(_TABLE, "tilt_result")
