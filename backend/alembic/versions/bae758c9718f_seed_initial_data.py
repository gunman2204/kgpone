"""Seed Initial Data

Revision ID: bae758c9718f
Revises: eec9234cdffd
Create Date: 2026-06-18 00:11:25.928015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bae758c9718f'
down_revision: Union[str, Sequence[str], None] = 'eec9234cdffd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.sql import table, column
import uuid
from datetime import datetime, timezone

def upgrade() -> None:
    users_table = table('users',
        column('id', sa.UUID),
        column('email', sa.String),
        column('hashed_password', sa.String),
        column('full_name', sa.String),
        column('role', sa.String),
        column('is_active', sa.Boolean),
        column('is_verified', sa.Boolean),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )
    
    departments_table = table('departments',
        column('id', sa.UUID),
        column('code', sa.String),
        column('name', sa.String),
        column('created_at', sa.DateTime)
    )
    
    courses_table = table('courses',
        column('id', sa.UUID),
        column('department_id', sa.UUID),
        column('code', sa.String),
        column('title', sa.String),
        column('description', sa.Text),
        column('credits', sa.Integer),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    course_offerings_table = table('course_offerings',
        column('id', sa.UUID),
        column('course_id', sa.UUID),
        column('year', sa.Integer),
        column('semester', sa.String)
    )
    
    admin_id = uuid.uuid4()
    dept_id = uuid.uuid4()
    course_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    
    op.bulk_insert(users_table, [
        {
            'id': admin_id,
            'email': 'admin@kgpone.edu',
            'hashed_password': '$argon2id$v=19$m=65536,t=3,p=4$QMsnBworcw/lopPRoYhOzw$H4Le0F4d1YSdtHNH+WIGrbKqC9N/wCgbkYA2O+EtUHA',
            'full_name': 'System Admin',
            'role': 'ADMIN',
            'is_active': True,
            'is_verified': True,
            'created_at': now,
            'updated_at': now
        }
    ])
    
    op.bulk_insert(departments_table, [
        {
            'id': dept_id,
            'code': 'CS',
            'name': 'Computer Science and Engineering',
            'created_at': now
        }
    ])
    
    op.bulk_insert(courses_table, [
        {
            'id': course_id,
            'department_id': dept_id,
            'code': 'CS10001',
            'title': 'Programming and Data Structures',
            'description': 'Introduction to C programming and basic data structures',
            'credits': 4,
            'created_at': now,
            'updated_at': now
        }
    ])
    
    op.bulk_insert(course_offerings_table, [
        {
            'id': offering_id,
            'course_id': course_id,
            'year': 2026,
            'semester': 'AUTUMN'
        }
    ])

def downgrade() -> None:
    op.execute("DELETE FROM course_offerings WHERE year = 2026 AND semester = 'AUTUMN'")
    op.execute("DELETE FROM courses WHERE code = 'CS10001'")
    op.execute("DELETE FROM departments WHERE code = 'CS'")
    op.execute("DELETE FROM users WHERE email = 'admin@kgpone.edu'")
