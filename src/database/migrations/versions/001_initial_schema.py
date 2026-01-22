"""Initial schema: Create company and analysis tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-01-21 14:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create Companies table (Capitalized to match Model/Tests)
    op.create_table(
        'Companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('corp_code', sa.String(length=20), nullable=True),
        sa.Column('stock_code', sa.String(length=20), nullable=True),
        sa.Column('ceo_name', sa.String(length=100), nullable=True),
        sa.Column('founded_year', sa.Integer(), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('sector', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_name', name='uq_company_name'),
        sa.UniqueConstraint('corp_code', name='uq_corp_code'),
        sa.UniqueConstraint('stock_code', name='uq_stock_code'),
    )

    # 2. Create Analysis_Reports table
    op.create_table(
        'Analysis_Reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('rcept_no', sa.String(length=20), nullable=False),
        sa.Column('rcept_dt', sa.String(length=10), nullable=False),
        sa.Column('report_type', sa.String(length=50), nullable=False, server_default='annual'),
        sa.Column('basic_info', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='Raw_Loaded'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['Companies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rcept_no', name='uq_rcept_no'),
    )

    # 3. Create Source_Materials table
    op.create_table(
        'Source_Materials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('chunk_type', sa.String(length=20), nullable=False, server_default='text'),
        sa.Column('section_path', sa.Text(), nullable=False),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('raw_content', sa.Text(), nullable=False),
        sa.Column('table_metadata', sa.JSON(), nullable=True),
        sa.Column('embedding', Vector(dim=768), nullable=True),
        sa.Column('meta_info', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['report_id'], ['Analysis_Reports.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # 4. Create Generated_Reports table
    op.create_table(
        'Generated_Reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(length=100), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('report_content', sa.Text(), nullable=False),
        sa.Column('toc_text', sa.Text(), nullable=True),
        sa.Column('references_data', sa.JSON(), nullable=True),
        sa.Column('conversation_log', sa.JSON(), nullable=True),
        sa.Column('meta_info', sa.JSON(), nullable=True),
        sa.Column('model_name', sa.String(length=50), nullable=False, server_default='gpt-4o'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['Companies.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes
    op.create_index('ix_analysis_reports_company_id', 'Analysis_Reports', ['company_id'])
    op.create_index('ix_analysis_reports_status', 'Analysis_Reports', ['status'])
    op.create_index('ix_source_materials_report_id', 'Source_Materials', ['report_id'])
    op.create_index('ix_source_materials_chunk_type', 'Source_Materials', ['chunk_type'])
    op.create_index('ix_generated_reports_company_id', 'Generated_Reports', ['company_id'])
    op.create_index('ix_generated_reports_model_name', 'Generated_Reports', ['model_name'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_generated_reports_model_name', table_name='Generated_Reports')
    op.drop_index('ix_generated_reports_company_id', table_name='Generated_Reports')
    op.drop_index('ix_source_materials_chunk_type', table_name='Source_Materials')
    op.drop_index('ix_source_materials_report_id', table_name='Source_Materials')
    op.drop_index('ix_analysis_reports_status', table_name='Analysis_Reports')
    op.drop_index('ix_analysis_reports_company_id', table_name='Analysis_Reports')

    # Drop tables (Reverse order of creation)
    op.drop_table('Generated_Reports')
    op.drop_table('Source_Materials')
    op.drop_table('Analysis_Reports')
    op.drop_table('Companies')