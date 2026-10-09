from backend.app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

# NullPool: no connection reuse across requests. Serverless invocations (Vercel)
# can outlive Neon's idle-connection culling, and pooled connections then fail
# on the next warm invocation; a fresh connection per request avoids that.
engine = create_engine(settings.sync_database_url, poolclass=NullPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
