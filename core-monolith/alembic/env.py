import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import Base
from app.auth.models import User, RefreshToken, OTPCode 
from app.user.models import UserProfileORM, AddressORM  
from app.partner.models import PartnerORM  
from app.event.models import EventORM, TicketCategoryORM  # ✅ ADD THIS
from dotenv import load_dotenv
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_online() -> None:
    url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg", "postgresql")
    
    connectable = engine_from_config(
        {"sqlalchemy.url": url}, 
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

def run_migrations_offline() -> None:
    url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg", "postgresql")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()