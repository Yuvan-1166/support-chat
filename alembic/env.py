from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# Import settings, models, and the pre-configured engine from the application.
# This guarantees that migrations use exactly the same DATABASE_URL, SSL
# settings, and connect_args as the running API — no duplication.
from app.core.config import get_settings
from app.db import Base, _build_connect_args
from app.db.models import *  # noqa: F401, F403 — ensure all models are registered

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to alembic.ini values)
# ---------------------------------------------------------------------------

config = context.config

# Push the app DATABASE_URL into alembic.ini so it takes precedence over any
# hard-coded value in the ini file.
_settings = get_settings()
if not _settings.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set.  Add it to your .env file before running "
        "Alembic migrations."
    )
config.set_main_option("sqlalchemy.url", _settings.DATABASE_URL)

# Set up Python logging from alembic.ini (optional, kept for alembic tooling).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Provide the metadata so alembic autogenerate can diff against existing tables.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — emit SQL to stdout without a live connection
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Useful for generating a SQL script to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect and apply migrations directly
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations in 'online' mode against the live database.

    We create a *new* engine here using NullPool so connections are released
    immediately after the migration run (not held in a pool).  This mirrors
    the app engine settings (SSL, connect_args) so the migration connection
    is authenticated identically.
    """
    from sqlalchemy import create_engine

    connect_args = _build_connect_args(_settings.DATABASE_URL, _settings.DB_SSL_CA)

    connectable = create_engine(
        _settings.DATABASE_URL,
        connect_args=connect_args,
        poolclass=pool.NullPool,  # No pool — release connection after migration
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Compare server defaults so autogenerate catches DEFAULT changes
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

