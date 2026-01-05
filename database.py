import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# Read from environment variable (REQUIRED for deployment)
DATABASE_URL = os.getenv("postgresql://postgres:q-LN5VfKQmP?ka2@db.isfdhktoalmzbbtjfvil.supabase.co:5432/postgres")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Create tables only once (safe for Supabase)
Base.metadata.create_all(bind=engine)
