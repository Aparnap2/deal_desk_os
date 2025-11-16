"""Add policy management system

Revision ID: 20251116_002_add_policy_management
Revises: 20251116_001_add_sla_analytics_views
Create Date: 2025-11-16 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251116_002_add_policy_management'
down_revision = '20251116_001_add_sla_analytics_views'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create policy_templates table
    op.create_table('policy_templates',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('policy_type', sa.String(length=50), nullable=False),
        sa.Column('template_configuration', sa.JSON(), nullable=False),
        sa.Column('schema_definition', sa.JSON(), nullable=False),
        sa.Column('is_system_template', sa.Boolean(), nullable=False, default=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_policy_templates_policy_type'), 'policy_templates', ['policy_type'], unique=False)

    # Create policies table
    op.create_table('policies',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('policy_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, default='draft'),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('configuration', sa.JSON(), nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, default=0),
        sa.Column('created_by_id', sa.String(length=36), nullable=False),
        sa.Column('approved_by_id', sa.String(length=36), nullable=True),
        sa.Column('parent_policy_id', sa.String(length=36), nullable=True),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['parent_policy_id'], ['policies.id'], ),
        sa.ForeignKeyConstraint(['template_id'], ['policy_templates.id'], )
    )
    op.create_index(op.f('ix_policies_name'), 'policies', ['name'], unique=False)
    op.create_index(op.f('ix_policies_policy_type'), 'policies', ['policy_type'], unique=False)
    op.create_index(op.f('ix_policies_status'), 'policies', ['status'], unique=False)

    # Create policy_versions table
    op.create_table('policy_versions',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('configuration', sa.JSON(), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], )
    )

    # Create policy_change_logs table
    op.create_table('policy_change_logs',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=False),
        sa.Column('change_type', sa.String(length=20), nullable=False),
        sa.Column('old_configuration', sa.JSON(), nullable=True),
        sa.Column('new_configuration', sa.JSON(), nullable=True),
        sa.Column('change_summary', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('changed_by_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], )
    )

    # Create policy_validations table
    op.create_table('policy_validations',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=False),
        sa.Column('validation_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], )
    )

    # Create policy_conflicts table
    op.create_table('policy_conflicts',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('policy_1_id', sa.String(length=36), nullable=False),
        sa.Column('policy_2_id', sa.String(length=36), nullable=False),
        sa.Column('conflict_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('resolution_suggestion', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['policy_1_id'], ['policies.id'], ),
        sa.ForeignKeyConstraint(['policy_2_id'], ['policies.id'], ),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], )
    )

    # Create policy_simulations table
    op.create_table('policy_simulations',
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=False),
        sa.Column('simulation_type', sa.String(length=50), nullable=False),
        sa.Column('test_data', sa.JSON(), nullable=False),
        sa.Column('results', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], )
    )

    # Insert default policy templates
    op.execute("""
        INSERT INTO policy_templates (id, name, description, policy_type, template_configuration, schema_definition, is_system_template, created_by_id)
        VALUES
        ('pricing-template-1', 'Pricing Policy Template', 'Standard pricing guardrails configuration', 'pricing',
         '{"discount_guardrails": {"default_max_discount_percent": 25, "risk_overrides": {"low": 30, "medium": 20, "high": 10}, "requires_executive_approval_above": 20}, "payment_terms_guardrails": {"max_terms_days": 45, "requires_finance_review_above_days": 30}, "price_floor": {"currency": "USD", "min_amount": 5000}}',
         '{"type": "object", "properties": {"discount_guardrails": {"type": "object"}, "payment_terms_guardrails": {"type": "object"}, "price_floor": {"type": "object"}}, "required": ["discount_guardrails", "payment_terms_guardrails", "price_floor"]}',
         true, 'system-user'),
        ('discount-template-1', 'Discount Policy Template', 'Configure discount limits and approval thresholds', 'discount',
         '{"max_discount_percent": 25, "risk_overrides": {"low": 30, "medium": 20, "high": 10}, "requires_approval_above": 20}',
         '{"type": "object", "properties": {"max_discount_percent": {"type": "number", "minimum": 0, "maximum": 100}, "risk_overrides": {"type": "object"}, "requires_approval_above": {"type": "number"}}, "required": ["max_discount_percent", "risk_overrides"]}',
         true, 'system-user'),
        ('sla-template-1', 'SLA Policy Template', 'Configure SLA targets and response times', 'sla',
         '{"touch_rate_target": 0.95, "response_time_threshold": 24, "escalation_rules": {"level1_after": 48, "level2_after": 72}}',
         '{"type": "object", "properties": {"touch_rate_target": {"type": "number", "minimum": 0, "maximum": 1}, "response_time_threshold": {"type": "number"}, "escalation_rules": {"type": "object"}}}',
         true, 'system-user')
    """)


def downgrade() -> None:
    op.drop_table('policy_simulations')
    op.drop_table('policy_conflicts')
    op.drop_table('policy_validations')
    op.drop_table('policy_change_logs')
    op.drop_table('policy_versions')
    op.drop_index(op.f('ix_policies_status'), table_name='policies')
    op.drop_index(op.f('ix_policies_policy_type'), table_name='policies')
    op.drop_index(op.f('ix_policies_name'), table_name='policies')
    op.drop_table('policies')
    op.drop_index(op.f('ix_policy_templates_policy_type'), table_name='policy_templates')
    op.drop_table('policy_templates')