"""persist spacing/line-spacing scores and canvas speed/correction flags

응답에는 실리는데 저장이 안 돼 사라지던 값들을 쌓기 시작한다
(DATA_FLOW.md §5-8 · §8-B · §8-C).

- image_analysis_results: 자간·행간 균등성 점수
  AI는 5지표를 채점하는데 DB엔 3개뿐이라 대시보드 "더 연습이 필요한 항목"에
  자간·행간이 후보로도 오르지 않았다.
- canvas_analysis_results: 속도 프로필 · 교정 표시
  필압(pressure_profile)은 일부러 뺐다 — 프론트가 1.0을 하드코딩해서 보내
  전부 같은 값이라 쌓아도 볼 것이 없다.

전부 nullable이다. 기존 행은 NULL로 남고, 집계는 NULL을 제외하므로
과거 데이터가 0점으로 오염되지 않는다(§4-2와 같은 원칙).

Revision ID: b3f1c27a9d40
Revises: 8cc78a9d44f7
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1c27a9d40'
down_revision: Union[str, None] = '8cc78a9d44f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('image_analysis_results',
                  sa.Column('spacing_uniformity_score', sa.Integer(), nullable=True))
    op.add_column('image_analysis_results',
                  sa.Column('line_spacing_uniformity_score', sa.Integer(), nullable=True))
    op.add_column('canvas_analysis_results',
                  sa.Column('speed_profile', sa.JSON(), nullable=True))
    op.add_column('canvas_analysis_results',
                  sa.Column('correction_flags', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('canvas_analysis_results', 'correction_flags')
    op.drop_column('canvas_analysis_results', 'speed_profile')
    op.drop_column('image_analysis_results', 'line_spacing_uniformity_score')
    op.drop_column('image_analysis_results', 'spacing_uniformity_score')
