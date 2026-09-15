"""add user-owned books and link thoughts

Revision ID: 20260915_0006
Revises: 20260827_0005
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0006"
down_revision: str | None = "20260827_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("normalized_title", sa.String(length=255), nullable=False),
        sa.Column("normalized_author", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "normalized_title", "normalized_author", name="uq_books_user_normalized_name"),
    )
    op.create_index("ix_books_user_id", "books", ["user_id"])
    op.add_column("thoughts", sa.Column("book_id", sa.Uuid(), nullable=True))
    op.create_index("ix_thoughts_book_id", "thoughts", ["book_id"])
    op.create_foreign_key("fk_thoughts_book_id_books", "thoughts", "books", ["book_id"], ["id"], ondelete="SET NULL")

    op.execute(
        """
        INSERT INTO books (id, user_id, title, author, normalized_title, normalized_author)
        SELECT gen_random_uuid(), user_id, book_title, book_author,
               lower(trim(regexp_replace(book_title, '\\s+', ' ', 'g'))),
               lower(trim(regexp_replace(book_author, '\\s+', ' ', 'g')))
        FROM thoughts
        WHERE book_title IS NOT NULL AND trim(book_title) <> ''
          AND book_author IS NOT NULL AND trim(book_author) <> ''
        GROUP BY user_id, book_title, book_author
        ON CONFLICT (user_id, normalized_title, normalized_author) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE thoughts AS thoughts
        SET book_id = books.id
        FROM books
        WHERE thoughts.user_id = books.user_id
          AND lower(trim(regexp_replace(thoughts.book_title, '\\s+', ' ', 'g'))) = books.normalized_title
          AND lower(trim(regexp_replace(thoughts.book_author, '\\s+', ' ', 'g'))) = books.normalized_author
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_thoughts_book_id_books", "thoughts", type_="foreignkey")
    op.drop_index("ix_thoughts_book_id", table_name="thoughts")
    op.drop_column("thoughts", "book_id")
    op.drop_index("ix_books_user_id", table_name="books")
    op.drop_table("books")
