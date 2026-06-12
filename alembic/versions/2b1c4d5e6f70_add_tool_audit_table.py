"""Add tool_audit table (AGENT-mode tool execution audit trail)

Revision ID: 2b1c4d5e6f70
Revises: 114ec50a1212
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b1c4d5e6f70'
down_revision: Union[str, Sequence[str], None] = '114ec50a1212'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tool_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('emp_id', sa.Integer(), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_input', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('success', sa.String(length=10), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tool_audit_company_id', 'tool_audit', ['company_id'])
    op.create_index('ix_tool_audit_emp_id', 'tool_audit', ['emp_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tool_audit_emp_id', table_name='tool_audit')
    op.drop_index('ix_tool_audit_company_id', table_name='tool_audit')
    op.drop_table('tool_audit')
