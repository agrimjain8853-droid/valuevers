import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(
    DATABASE_URL,

    # 🔴 CRITICAL: fail fast instead of hanging
    connect_args={
        "connect_timeout": 5
    },

    # 🔴 Detect dead / stale connections
    pool_pre_ping=True,

    # 🔴 Recycle idle connections (important for Supabase pooler)
    pool_recycle=300,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


